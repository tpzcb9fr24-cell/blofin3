import json
import queue
from dataclasses import replace
from datetime import datetime,timezone
import pytest
from strategy_lab.market import Candle,contiguous
from strategy_lab.instruments import next_bar,market_open,valid_bar,future_times
from strategy_lab.strategies import Settings,detect
from strategy_lab.targets import OrderBlock,choose_target
from strategy_lab.store import Store,net_return
from strategy_lab.risk import size_entry,account,structural_stop,trend_context,POLICY
from strategy_lab.metrics import trade_metrics,forecast_score
from strategy_lab import stocks

def ms(value):return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()*1000)
def bar(t,p=100):return Candle(t,p,p+1,p-1,p,10,1000)

def test_quality_skips_tiny_profit_before_block_without_moving_target():
    block=OrderBlock(100.21,101,'bearish',0)
    legacy=choose_target(entry=100,stop=99.25,side='long',blocks=[block],as_of=1)
    quality=choose_target(entry=100,stop=99.25,side='long',blocks=[block],as_of=1,min_net_rr=1)
    assert legacy.accepted and legacy.net_reward_pct>0
    assert not quality.accepted and quality.original_target==101.5
    assert quality.blocking_order_block==block
    enough=choose_target(entry=100,stop=99.25,side='long',blocks=[],as_of=1,min_net_rr=1)
    assert enough.accepted and enough.net_rr==pytest.approx(1.5)

@pytest.mark.parametrize('start,end',[
 ('2026-07-02T19:55:00','2026-07-06T13:30:00'), # Independence Day observed Friday
 ('2026-11-27T17:55:00','2026-11-30T14:30:00'), # early close + weekend
 ('2026-03-06T20:55:00','2026-03-09T13:30:00'), # DST transition
])
def test_etf_session_continuity_holidays_early_close_dst(start,end):
    a,b=ms(start),ms(end)
    assert next_bar('SPY',a)==b
    assert contiguous([bar(a),bar(b)],'QQQ')
    assert not contiguous([bar(a),bar(b)],'BTC-USDT')
    assert not contiguous([bar(b),bar(b+600000)],'SPY')
    assert valid_bar('SPY',b)
    assert market_open('QQQ',b)


def test_regular_market_close_does_not_accept_bar_start():
    close=ms('2026-11-27T18:00:00')
    assert not market_open('SPY',close)
    assert not valid_bar('SPY',close)
    assert not market_open('SPY',ms('2026-11-26T15:00:00'))


def test_future_scores_cross_sessions_without_fabricated_candles():
    times=future_times('SPY',ms('2026-11-27T17:55:00'),2)
    assert times==[ms('2026-11-30T14:30:00'),ms('2026-11-30T14:35:00')]
    f={'asof':ms('2026-11-27T18:00:00'),'values':[100,102],'target_times':times}
    assert forecast_score(f,[bar(times[0],101)])['mae']==1


def test_stock_schema_and_confirmation_without_key_or_fabricated_bars():
    now=ms('2026-10-23T14:36:00')
    payload={'meta':{'symbol':'SPY','currency':'USD','interval':'5min','exchange_timezone':'America/New_York'},'values':[
      {'datetime':'2026-10-23 14:30:00','open':'100','high':'102','low':'99','close':'101','volume':'20'},
      {'datetime':'2026-10-23 14:35:00','open':'101','high':'102','low':'100','close':'101','volume':'10'}]}
    bars=stocks.parse_history(payload,'SPY',now)
    assert bars[0].confirmed and not bars[1].confirmed
    assert bars[0].amount==2020 # explicitly labeled close*share-volume proxy
    assert len(bars)==2
    payload['meta']['symbol']='QQQ'
    with pytest.raises(stocks.DataUnavailable):stocks.parse_history(payload,'SPY',now)


def test_no_key_and_provider_error_fail_closed(monkeypatch):
    with pytest.raises(stocks.DataUnavailable):stocks.request('time_series','SPY','')
    with pytest.raises(ValueError):stocks.request('orders','SPY','data-key')
    with pytest.raises(ValueError):stocks.request('quote','AAPL','data-key')
    monkeypatch.setattr(stocks,'request',lambda *a,**k:{'symbol':'SPY','timestamp':1000,'close':'nan'})
    with pytest.raises(stocks.DataUnavailable):stocks.quote('SPY','data-key')


def test_stock_key_is_header_only_and_no_redirect(monkeypatch):
    seen={}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,n):return b'{"symbol":"SPY","close":"100","timestamp":1000}'
    class Opener:
        def open(self,req,timeout):seen['url']=req.full_url;seen['headers']=dict(req.header_items());return Response()
    monkeypatch.setattr(stocks,'build_opener',lambda *a:Opener())
    stocks.request('quote','SPY','secret-data-key')
    assert 'secret-data-key' not in seen['url']
    assert seen['headers']['Authorization']=='apikey secret-data-key'
    assert stocks._NoRedirect().redirect_request(None,None,None,None,None,None) is None


def test_risk_budget_and_correlated_etfs_and_no_leverage(tmp_path):
    db=Store(tmp_path/'db');cfg=Settings();now=ms('2026-10-23T14:30:00')
    qty,note=size_entry(db.trades(),'A','SPY','long',100,99,.0015,now,cfg)
    assert qty*1.15==pytest.approx(25)
    assert qty*100<=10000
    db.open_trade('A','SPY','long',now,100,99,102,'test',quantity=qty,cost_pct=.0015,policy=POLICY)
    q2,_=size_entry(db.trades(),'A','QQQ','long',100,99,.0015,now,cfg)
    assert q2*1.15==pytest.approx(25)
    db.open_trade('A','QQQ','long',now,100,99,102,'test',quantity=q2,cost_pct=.0015,policy=POLICY)
    assert size_entry(db.trades(),'A','SPY','short',100,101,.0015,now,cfg)[0] is None
    # A different strategy is an independent account, not summed into account A.
    assert size_entry(db.trades(),'B','SPY','long',100,99,.0015,now,cfg)[0]>0
    q,_=size_entry([],'A','BTC-USDT','long',100,99.999,0,now,cfg)
    assert q*100<=cfg.initial_equity


def test_daily_loss_blocks_new_entry_and_old_records_survive(tmp_path):
    db=Store(tmp_path/'db');cfg=Settings();now=ms('2026-10-23T14:30:00')
    legacy=db.open_trade('A','BTC-USDT','long',0,100,99,102,'old')
    db.close_trade(legacy,99,1000,'old loss',.0015)
    assert db.trades()[0]['policy']=='legacy-v1'
    assert account(db.trades(),'A',{},cfg)['equity']==10000
    t=db.open_trade('A','SPY','long',now,100,99,102,'quality',quantity=100,policy=POLICY)
    db.close_trade(t,99,now+1000,'loss',0)
    assert account(db.trades(),'A',{},cfg)['equity']==9900
    assert size_entry(db.trades(),'A','QQQ','long',100,99,.0015,now+2000,cfg)[0] is None
    assert size_entry(db.trades(),'A','QQQ','long',100,99,.0015,now+86400000,cfg)[0]>0


def test_dollars_per100_and_account_dollars_are_distinct(tmp_path):
    db=Store(tmp_path/'db');cfg=Settings()
    t=db.open_trade('A','SPY','long',0,100,99,102,'quality',quantity=10,policy=POLICY)
    db.close_trade(t,102,1000,'win',.0015)
    row=db.trades()[0]
    assert net_return(row,102)*100==pytest.approx(1.85)
    assert trade_metrics([row],{})['average_dollars_per_100']==pytest.approx(1.85)
    assert account([row],'A',{},cfg)['equity']==pytest.approx(10018.5)
    assert 100*(account([row],'A',{},cfg)['equity']/10000-1)==pytest.approx(.185)


def test_settings_reject_invalid_budget_order_and_nan():
    for cfg in (replace(Settings(),risk_fraction=.02),replace(Settings(),min_net_rr=float('nan')),replace(Settings(),quality_policy=2)):
        with pytest.raises(ValueError):cfg.validate()


def test_stop_is_structure_bound_and_max_distance_is_rejection():
    bars=[Candle(i*300000,100,100.1,99.9,100,10,1000) for i in range(80)]
    bars[-4]=Candle(76*300000,100,100.1,99.7,100,10,1000)
    stop=structural_stop(bars,'long',100,Settings())
    assert stop<99.7
    assert structural_stop(bars,'long',110,Settings()) is None
    assert not trend_context(bars,'long')['accepted']


def test_engine_etf_fills_are_indicative_fresh_and_risk_budgeted(tmp_path,monkeypatch):
    import strategy_lab.engine as engine_module
    import strategy_lab.risk as risk_module
    from strategy_lab.engine import Engine
    from strategy_lab.strategies import Signal
    now=ms('2026-10-23T14:35:10');monkeypatch.setattr(engine_module.time,'time',lambda:now/1000)
    monkeypatch.setattr(stocks,'load_key',lambda path:'fixture-data-only-key')
    monkeypatch.setattr(engine_module,'detect',lambda *a,**k:([],[],{}))
    monkeypatch.setattr(risk_module,'structural_stop',lambda *a:99)
    engine=Engine(tmp_path/'db',queue.Queue());engine.settings=Settings()
    engine.bars['SPY']={ms('2026-10-23T14:30:00'):bar(ms('2026-10-23T14:30:00'))}
    asof=ms('2026-10-23T14:35:00');signal=Signal('Fibonacci','long',asof,100,99,102,'fixture',2)
    engine.pending[('SPY',asof)]={'signals':[signal],'entered':set()}
    db=Store(tmp_path/'db')
    monkeypatch.setattr(stocks,'quote',lambda *a:{'price':100,'time':now-90001,'basis':'fixture'})
    engine.entries(db,'SPY',asof);assert db.trades()==[]
    engine.pending[('SPY',asof)]['entered'].clear()
    engine.quote_retry.clear()
    monkeypatch.setattr(stocks,'quote',lambda *a:{'price':100,'time':now-1000,'basis':'one-minute indicative fixture'})
    engine.entries(db,'SPY',asof)
    row=db.trades()[0]
    assert row['policy']==POLICY and row['source']=='paper' and row['symbol']=='SPY'
    assert row['quantity']*1.05==pytest.approx(25)
    assert 'indicative' in row['reason']


def test_open_paper_estimates_costs_and_flags_missing_mark(tmp_path):
    db=Store(tmp_path/'db');cfg=Settings()
    db.open_trade('A','QQQ','short',0,100,101,98,'quality',policy=POLICY,cost_pct=.0005)
    row=db.trades()[0]
    assert net_return(row,100)==pytest.approx(-.0005)
    assert account([row],'A',{},cfg)['unpriced_open']==1
    assert trade_metrics([row],{})['unpriced_open']==1
    assert account([row],'A',{'QQQ':99},cfg)['unpriced_open']==0


def test_legacy_database_migrates_without_rewriting_history(tmp_path):
    import sqlite3
    from strategy_lab.store import SCHEMA
    path=tmp_path/'old.db';db=sqlite3.connect(path);db.executescript(SCHEMA)
    db.execute("INSERT INTO trades(track,symbol,side,opened,entry,stop,target,source) VALUES('Fibonacci','BTC-USDT','long',1,100,99,102,'paper')")
    db.commit();db.close();store=Store(path)
    row=store.trades()[0]
    assert row['opened']==1 and row['entry']==100 and row['policy']=='legacy-v1'
    assert row['quantity']==1


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows user-bound protected storage')
def test_windows_key_roundtrip_and_no_plaintext(tmp_path,monkeypatch):
    monkeypatch.delenv('TWELVE_DATA_API_KEY',raising=False)
    path=tmp_path/'key';stocks.save_key(path,'test-data-key-never-production')
    assert b'test-data-key-never-production' not in path.read_bytes()
    assert stocks.load_key(path)=='test-data-key-never-production'


def test_model_gate_rechecks_observed_fill_not_old_signal_close(tmp_path,monkeypatch):
    import strategy_lab.engine as module
    from strategy_lab.engine import Engine
    from strategy_lab.strategies import Signal
    now=ms('2026-10-23T14:35:10');asof=ms('2026-10-23T14:35:00')
    monkeypatch.setattr(module.time,'time',lambda:now/1000)
    monkeypatch.setattr(module,'quote',lambda s:{'bid':103,'ask':103,'time':now})
    monkeypatch.setattr(module,'detect',lambda *a,**k:([],[],{}))
    engine=Engine(tmp_path/'db',queue.Queue());engine.settings=Settings(quality_policy=0)
    engine.bars['BTC-USDT']={asof-300000:bar(asof-300000)}
    engine.forecasts[('BTC-USDT','Kronos')]={'asof':asof,'values':[101]}
    signal=Signal('SMC EMA50','long',asof,100,99,102,'fixture',2)
    engine.pending[('BTC-USDT',asof)]={'signals':[signal],'entered':set()}
    db=Store(tmp_path/'db');engine.entries(db,'BTC-USDT',asof)
    assert sorted(r['track'] for r in db.trades())==['SMC EMA50 [FLIP]']


def test_etf_model_variants_share_a_cached_indicative_quote(tmp_path,monkeypatch):
    import strategy_lab.engine as module
    from strategy_lab.engine import Engine
    from strategy_lab.strategies import Signal
    now=ms('2026-10-23T14:35:10');asof=ms('2026-10-23T14:35:00')
    monkeypatch.setattr(module.time,'time',lambda:now/1000)
    monkeypatch.setattr(stocks,'load_key',lambda path:'fixture-key')
    monkeypatch.setattr(module,'detect',lambda *a,**k:([],[],{}))
    calls=[]
    def quote(*a):calls.append(1);return {'price':100,'time':asof,'basis':'fixture'}
    monkeypatch.setattr(stocks,'quote',quote)
    engine=Engine(tmp_path/'db',queue.Queue());engine.settings=Settings(quality_policy=0)
    engine.bars['SPY']={asof-300000:bar(asof-300000)}
    for name in ('Kronos','TimesFM'):engine.forecasts[('SPY',name)]={'asof':asof,'values':[101]}
    signal=Signal('SMC EMA50','long',asof,100,99,102,'fixture',2)
    engine.pending[('SPY',asof)]={'signals':[signal],'entered':set()}
    db=Store(tmp_path/'db');engine.entries(db,'SPY',asof)
    assert len(db.trades())==4
    assert len(calls)==1


def test_worker_keeps_draining_results_after_etf_poll(tmp_path,monkeypatch):
    import strategy_lab.engine as module
    from strategy_lab.engine import Engine
    engine=Engine(tmp_path/'db',queue.Queue())
    monkeypatch.setattr(module,'history',lambda symbol:[])
    monkeypatch.setattr(stocks,'load_key',lambda path:None)
    monkeypatch.setattr(engine,'update',lambda *a,**k:None)
    monkeypatch.setattr(engine,'entries',lambda *a:None)
    passes=[]
    def wait(seconds):
        passes.append(1)
        if len(passes)==1:
            engine.model_results.put(('BTC-USDT','Kronos',1,{'values':[100],'asof':1},None))
        else:engine.stop.set()
    monkeypatch.setattr(engine.stop,'wait',wait)
    engine.run()
    assert engine.forecasts[('BTC-USDT','Kronos')]['values']==[100]
    db=Store(tmp_path/'db')
    assert not db.db.execute("SELECT 1 FROM events WHERE kind='worker_error'").fetchone()
    db.close()
