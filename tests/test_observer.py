import math
import queue
from dataclasses import replace
import pytest
from strategy_lab.market import Candle,parse_candle,contiguous
from strategy_lab.strategies import Settings,pivots,structure,detect
from strategy_lab.targets import OrderBlock,choose_target
from strategy_lab.store import Store,net_return
from strategy_lab.engine import Engine
from strategy_lab.models import agrees


def candle(i,o,h,l,c,confirmed=True):return Candle(i*300000,o,h,l,c,10,1000,confirmed)

@pytest.mark.parametrize('bad',[['0','100','99','95','100','1','1','1','1'],['1','100','101','99','100','1','1','1','1'],['0','nan','101','99','100','1','1','1','1']])
def test_bad_market_data(bad):
    with pytest.raises(ValueError):parse_candle(bad)


def test_confirmation_and_base_volume():
    c=parse_candle(['0','100','101','99','100','1000','2','200','0'])
    assert c.volume==2 and not c.confirmed and c.end==300000


def test_gap_detection():
    assert not contiguous([candle(0,100,101,99,100),candle(2,100,101,99,100)])

@pytest.mark.parametrize('side,block,entry,stop,expected',[('long',OrderBlock(101,102,'bearish',0),100,99,100.9495),('short',OrderBlock(98,99,'bullish',0),100,101,99.0495)])
def test_tp_is_before_nearest_opposing_zone_below_2r(side,block,entry,stop,expected):
    d=choose_target(entry=entry,stop=stop,side=side,blocks=[block],as_of=1,roundtrip_cost_pct=0)
    assert d.accepted and d.target==pytest.approx(expected) and d.gross_rr<2


def test_tp_selects_nearest_and_rejects_overlap():
    blocks=[OrderBlock(103,104,'bearish',0),OrderBlock(101,102,'bearish',0)]
    assert choose_target(entry=100,stop=98,side='long',blocks=blocks,as_of=1).target<101
    blocks.append(OrderBlock(99.9,100.1,'bearish',0))
    assert not choose_target(entry=100,stop=98,side='long',blocks=blocks,as_of=1).accepted


def test_future_and_invalid_blocks_are_ignored():
    blocks=[OrderBlock(101,102,'bearish',5),OrderBlock(101,102,'bearish',0,1)]
    assert choose_target(entry=100,stop=99,side='long',blocks=blocks,as_of=2).target==102


def test_pivots_require_right_confirmation():
    bars=[candle(i,100,hi,95,100) for i,hi in enumerate([101,102,110,103,104])]
    assert pivots(bars[:4])[0]==[]
    assert pivots(bars)[0]==[(2,110)]


def test_order_block_partial_touch_equal_and_wick_invalidation():
    # Bullish break above pivot 105 at bar 7; last bearish candle = bar 6 [97,102].
    raw=[(100,101,98,100),(100,103,99,102),(102,105,100,104),(103,104,99,100),(100,103,98,101),(101,104,99,102),(102,102,97,99),(100,108,99,107)]
    bars=[candle(i,*v) for i,v in enumerate(raw)]
    blocks=structure(bars)[0];active=[b for b in blocks if b.kind=='bullish' and b.invalidated_at is None]
    assert active
    block=active[-1]
    bars.append(candle(8,105,106,block.low,104))
    after=next(b for b in structure(bars)[0] if b.formed_at==block.formed_at and b.kind=='bullish')
    assert after.invalidated_at is None
    bars.append(candle(9,104,105,block.low-.01,100))
    after=next(b for b in structure(bars)[0] if b.formed_at==block.formed_at and b.kind=='bullish')
    assert after.invalidated_at==bars[-1].end


def test_detector_refuses_unclosed_or_gap():
    bars=[candle(i,100,101,99,100) for i in range(65)]
    assert detect(bars[:-1]+[replace(bars[-1],confirmed=False)])[0]==[]
    assert detect(bars[:30]+bars[31:])[0]==[]


def test_manual_journal_survives_restart_and_matching(tmp_path):
    path=tmp_path/'db.sqlite';db=Store(path)
    manual=db.open_trade('Alyssa manual','BTC-USDT','long',1000,100,99,102,'manual','manual')
    paper=db.open_trade('SMC Trendline','BTC-USDT','short',1100,100,101,98,'paper')
    assert paper and manual
    assert db.open_trade('Alyssa manual','BTC-USDT','long',1200,100,99,102,'duplicate','manual') is None
    db.close_trade(manual,101,2000,'manual close',.001);db.close();db=Store(path)
    row=next(x for x in db.trades() if x['id']==manual)
    assert net_return(row,101)==pytest.approx(.009)
    assert db.comparison('BTC-USDT',1000)['SMC Trendline']['id']==paper
    db.close()


def test_paper_ambiguous_stop_first_and_gap(tmp_path):
    path=tmp_path/'db';db=Store(path);engine=Engine(path,queue.Queue());engine.settings=Settings()
    id=db.open_trade('SMC Trendline','BTC-USDT','long',0,100,99,102,'paper')
    engine.paper_exits(db,'BTC-USDT',candle(1,100,103,98,101))
    assert db.trades()[0]['exit']==99
    id=db.open_trade('SMC Trendline','BTC-USDT','long',600000,100,99,102,'paper')
    engine.paper_exits(db,'BTC-USDT',candle(3,97,100,96,99))
    assert db.trades()[0]['exit']==97


def test_intrabar_entry_does_not_reuse_prior_extremes(tmp_path):
    path=tmp_path/'db';db=Store(path);engine=Engine(path,queue.Queue());engine.settings=Settings()
    db.open_trade('SMC Trendline','BTC-USDT','long',1000,100,99,102,'paper')
    engine.paper_exits(db,'BTC-USDT',candle(0,100,103,98,100))
    assert db.trades()[0]['closed'] is None


def test_stale_forecast_never_gates_entry():
    f={'asof':300000,'values':[102]}
    assert agrees(f,'long',100,300000)
    assert not agrees(f,'long',100,600000)
    assert not agrees(None,'long',100,300000)


def test_no_exchange_write_surface():
    from pathlib import Path
    import ast
    for path in (Path(__file__).resolve().parents[1]/'src'/'strategy_lab').glob('*.py'):
        src=path.read_text();tree=ast.parse(src)
        assert '/api/v1/trade' not in src and '/ws/private' not in src
        assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('post','put','patch','delete') and getattr(node.func.value,'id','') in ('requests','session','httpx') for node in ast.walk(tree))


def test_manual_partial_exit_and_audited_edit(tmp_path):
    db=Store(tmp_path/'db')
    id=db.open_trade('Alyssa manual','ETH-USDT','long',0,100,99,103,'user','manual',2)
    db.edit_manual(id,0,100,98,104,'corrected notes')
    db.partial_exit(id,102,1000,1,.001)
    row=db.trades()[0]
    assert row['closed'] is None and row['remaining']==1
    assert net_return(row,100)==pytest.approx(.0095)
    with pytest.raises(ValueError):db.edit_manual(id,0,100,98,104,'cannot alter after exit')
    db.partial_exit(id,98,2000,1,.001)
    row=db.trades()[0]
    assert row['closed']==2000 and row['exit']==100 and net_return(row,100)==pytest.approx(-.001)


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),float('-inf')])
def test_nonfinite_target_rejected(bad):
    with pytest.raises(ValueError):choose_target(entry=bad,stop=99,side='long',blocks=[],as_of=0)


def test_forecast_quality_uses_future_confirmed_bars_only():
    from strategy_lab.metrics import forecast_score
    f={'asof':300000,'values':[101,103]}
    bars=[candle(0,100,101,99,100),candle(1,100,103,99,102),candle(2,102,104,101,103,False)]
    score=forecast_score(f,bars)
    assert score['observed']==1 and score['mae']==1


def test_per_track_metrics_cost_drawdown_and_r(tmp_path):
    from strategy_lab.metrics import trade_metrics
    db=Store(tmp_path/'db')
    id=db.open_trade('A','BTC-USDT','long',0,100,99,102,'test')
    db.close_trade(id,102,1000,'win',.001)
    id=db.open_trade('A','BTC-USDT','long',2000,100,99,102,'test')
    db.close_trade(id,99,3000,'loss',.001)
    score=trade_metrics(db.trades(),{})
    assert score['closed']==2 and score['wins']==1
    assert score['net']==pytest.approx(.008)
    assert score['max_drawdown']==pytest.approx(.011)
    assert score['expectancy_r']==pytest.approx(.4)


def test_block_evidence_is_preserved():
    block=OrderBlock(101,102,'bearish',0)
    d=choose_target(entry=100,stop=99,side='long',blocks=[block],as_of=1)
    assert d.blocking_order_block==block and d.buffer_pct==.0005


def test_zone_registry_survives_rolling_context_restart_and_partial_touch(tmp_path):
    path=tmp_path/'db';db=Store(path);block=OrderBlock(99,101,'bullish',300000)
    zones=db.sync_zones('BTC-USDT',[block],[candle(2,102,103,100,102)],900000)
    assert zones[0].invalidated_at is None
    db.close();db=Store(path)
    zones=db.sync_zones('BTC-USDT',[],[candle(700,102,103,99,102)],210300000)
    assert zones[0].invalidated_at is None
    zones=db.sync_zones('BTC-USDT',[],[candle(701,102,103,98,102)],210600000)
    assert zones[0].invalidated_at==210600000
    zones=db.sync_zones('BTC-USDT',[block],[],210600001)
    assert zones[0].invalidated_at==210600000  # no resurrection


def test_rest_drops_malformed_forming_bar_but_keeps_closed_history(monkeypatch):
    import io,json
    import strategy_lab.market as market
    good=['0','100','101','99','100','1','1','100','1']
    malformed=['300000','98','105','102','101','1','1','100','0']
    monkeypatch.setattr(market,'get_json',lambda *a,**k:{'code':'0','data':[malformed,good]})
    bars=market.public_get('BTC-USDT')
    assert len(bars)==1 and bars[0].confirmed and bars[0].time==0
    malformed[-1]='1'
    with pytest.raises(ValueError):market.public_get('BTC-USDT')


@pytest.mark.parametrize('url',[
 'http://openapi.blofin.com/api/v1/market/candles',
 'https://elsewhere.example/api/v1/market/candles',
 'https://openapi.blofin.com/api/v1/trade/order',
 'https://user:secret@openapi.blofin.com/api/v1/market/candles',
 'https://openapi.blofin.com:444/api/v1/market/candles',
])
def test_native_transport_rejects_nonpublic_destinations(url):
    from strategy_lab.transport import validate_url
    with pytest.raises(ValueError):validate_url(url)


def test_transport_errors_are_readable_without_html_dump():
    from strategy_lab.transport import MarketHTTPError
    error=MarketHTTPError(403,b'<html><head><style>long CSS</style></head><body><p>Access denied.</p></body></html>')
    assert error.status==403 and 'Access denied.' in str(error)
    assert '<html>' not in str(error) and 'long CSS' not in str(error)


def test_public_subscription_cannot_send_order_or_login():
    from strategy_lab.transport import WindowsPublicSocket
    sock=object.__new__(WindowsPublicSocket)
    for value in ('{"op":"login","args":[]}', '{"op":"subscribe","args":[{"channel":"orders","instId":"BTC-USDT"}]}'):
        with pytest.raises(ValueError):sock.send(value)
