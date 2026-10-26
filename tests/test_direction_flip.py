import pytest
from strategy_lab.direction_flip import flip_plan,replay_flip

@pytest.mark.parametrize('side,stop,target,opposite,newstop,newtarget',[
 ('long',99,102,'short',101,98),('short',101,98,'long',99,102)])
def test_only_direction_changes(side,stop,target,opposite,newstop,newtarget):
 p=flip_plan(side,100,stop,target)
 assert p=={'side':opposite,'entry':100,'stop':newstop,'target':newtarget}
 assert abs(p['target']-p['entry'])/abs(p['stop']-p['entry'])==2
 p=flip_plan(side,100,stop,target,100.1)
 assert abs(p['stop']/p['entry']-1)==pytest.approx(.01)
 assert abs(p['target']/p['entry']-1)==pytest.approx(.02)

def test_original_loss_can_also_be_a_flipped_loss():
 t={'side':'long','entry':100,'stop':99,'target':102,'opened':1,'cost_pct':.0015}
 bars=[{'time':0,'open':100,'high':100.5,'low':99.5,'close':100},
       {'time':300000,'open':100,'high':101.1,'low':99.8,'close':101},
       {'time':600000,'open':101,'high':101.2,'low':98.9,'close':99}]
 r=replay_flip(t,bars)
 assert r['outcome']=='STOP' and r['net']==pytest.approx(-.0115)

def test_replay_does_not_use_original_exit_time():
 t={'side':'long','entry':100,'stop':99,'target':102,'opened':1,'cost_pct':.0015}
 bars=[{'time':0,'open':100,'high':100.5,'low':99.5,'close':100},
       {'time':300000,'open':100,'high':100.1,'low':98.9,'close':99},
       {'time':600000,'open':99,'high':99.5,'low':97.9,'close':98}]
 r=replay_flip(t,bars)
 assert r['outcome']=='TARGET' and r['closed']==900000
 assert r['net']==pytest.approx(.0185)

def test_entry_candle_and_gaps_are_not_invented():
 t={'side':'long','entry':100,'stop':99,'target':102,'opened':1000,'cost_pct':.0015}
 assert replay_flip(t,[{'time':0,'open':100,'high':101.2,'low':99,'close':100}])['outcome']=='ENTRY_BAR_UNCERTAIN'
 assert replay_flip(t,[{'time':300000,'open':100,'high':100,'low':100,'close':100}])['outcome']=='MISSING_BARS'

@pytest.mark.parametrize('symbol,track,side,expected_side,expected_track',[
 ('BTC-USDT','Fibonacci','long','short','Fibonacci [FLIP]'),
 ('BTC-USDT','Fibonacci','short','long','Fibonacci [FLIP]'),
 ('ETH-USDT','Fibonacci','short','short','Fibonacci'),
 ('ETH-USDT','Fibonacci','long','short','Fibonacci [FLIP]'),
 ('ETH-USDT','SMC EMA50','short','long','SMC EMA50 [FLIP]'),
 ('ETH-USDT','Fibonacci + SMC + both','short','long','Fibonacci + SMC + both [FLIP]'),
 ('SPY','Fibonacci','short','long','Fibonacci [FLIP]'),
])
def test_only_one_routed_entry_with_exact_eth_exception(tmp_path,symbol,track,side,expected_side,expected_track):
 from strategy_lab.engine import Engine
 from strategy_lab.store import Store
 import queue
 db=Store(tmp_path/'db');engine=Engine(tmp_path/'db',queue.Queue())
 stop,target=(99,102) if side=='long' else (101,98)
 quote={'bid':99.9,'ask':100,'price':100}
 engine.open_routed(db,track,symbol,side,100,stop,target,.0015,2.5,'fixture',quote,1000,1001,'quality-v2')
 rows=db.trades();assert len(rows)==1
 row=rows[0];assert row['track']==expected_track and row['side']==expected_side
 assert row['opened']==1001 and row['quantity']==2.5 and row['cost_pct']==.0015
 assert abs(row['stop']/row['entry']-1)==pytest.approx(.01)
 assert abs(row['target']/row['entry']-1)==pytest.approx(.02)
 if expected_track=='Fibonacci':assert (row['entry'],row['stop'],row['target'])==(100,101,98)
 before=dict(row)
 engine.open_routed(db,track,symbol,side,100,stop,target,.0015,2.5,'fixture',quote,1000,1001,'quality-v2')
 assert db.trades()==[before]
 assert db.db.execute('select state from entry_attempts').fetchone()[0]=='EXISTING_POSITION'


def test_all_open_positions_remain_visible_and_original_history_can_be_filtered():
 from strategy_lab.direction_flip import visible_active
 rows=[{'source':'paper','track':'SMC EMA50','symbol':'BTC-USDT','side':'long'},
       {'source':'paper','track':'SMC EMA50 [FLIP]','symbol':'BTC-USDT','side':'short'},
       {'source':'paper','track':'Fibonacci','symbol':'ETH-USDT','side':'short'},
       {'source':'paper','track':'Fibonacci','symbol':'ETH-USDT','side':'long'},
       {'source':'paper','track':'Fibonacci [FLIP]','symbol':'ETH-USDT','side':'long'},
       {'source':'paper','track':'Fibonacci [FLIP]','symbol':'ETH-USDT','side':'short'}]
 assert [visible_active(r) for r in rows]==[False,True,True,False,False,True]


def test_live_provider_report_keeps_failure_explicit(tmp_path,monkeypatch):
    import json
    import strategy_lab.network_probe as probe
    def fail():raise AssertionError('fixture: unconfirmed historical candle')
    monkeypatch.setattr(probe,'run',fail)
    path=tmp_path/'status.json';result=probe.report_status(path)
    assert result['status']=='BLOCKED'
    assert 'unconfirmed historical candle' in result['error']
    assert json.loads(path.read_text())['status']=='BLOCKED'
    monkeypatch.setattr(probe,'run',lambda:{'fixture':'passed transport'})
    assert probe.report_status(path)['status']=='PASSED'


def test_full_entry_pipeline_flips_once_and_keeps_eth_fibonacci_short(tmp_path,monkeypatch):
 import queue
 import strategy_lab.engine as module
 from strategy_lab.engine import Engine
 from strategy_lab.store import Store
 from strategy_lab.market import Candle
 from strategy_lab.strategies import Signal,Settings
 asof=1792807200000
 monkeypatch.setattr(module.time,'time',lambda:asof/1000+10)
 monkeypatch.setattr(module,'quote',lambda s:{'bid':100,'ask':100,'time':asof+10000})
 monkeypatch.setattr(module,'detect',lambda *a,**k:([],[],{}))
 engine=Engine(tmp_path/'db',queue.Queue());engine.settings=Settings(quality_policy=0)
 db=Store(tmp_path/'db')
 for symbol in ('BTC-USDT','ETH-USDT'):
  engine.bars[symbol]={asof-300000:Candle(asof-300000,100,101,99,100,10,1000)}
  engine.pending[(symbol,asof)]={'signals':[Signal('Fibonacci','short',asof,100,101,98,'fixture',2)],'entered':set()}
  engine.entries(db,symbol,asof);engine.entries(db,symbol,asof)
 rows=db.trades();assert len(rows)==2
 assert {(r['symbol'],r['track'],r['side']) for r in rows}=={('BTC-USDT','Fibonacci [FLIP]','long'),('ETH-USDT','Fibonacci','short')}
 assert len(list(db.db.execute('select * from entry_attempts')))==2


def test_existing_eth_short_record_is_not_modified_by_new_mode(tmp_path):
 import queue
 from strategy_lab.engine import Engine
 from strategy_lab.store import Store
 db=Store(tmp_path/'db');engine=Engine(tmp_path/'db',queue.Queue())
 old=db.open_trade('Fibonacci','ETH-USDT','short',100,2000,2020,1960,'existing',quantity=2,cost_pct=.0015,policy='quality-v2')
 before=next(r for r in db.trades() if r['id']==old)
 engine.open_routed(db,'Fibonacci','BTC-USDT','long',100,99,102,.0015,2.5,'new',{'bid':99.9,'ask':100},1000,1001,'quality-v2')
 assert next(r for r in db.trades() if r['id']==old)==before
 assert len(db.trades())==2
