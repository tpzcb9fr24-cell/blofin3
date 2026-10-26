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

def test_live_pair_copies_original_size_cost_time_and_audits_overlap(tmp_path):
 from strategy_lab.engine import Engine
 from strategy_lab.store import Store
 import queue
 db=Store(tmp_path/'db');engine=Engine(tmp_path/'db',queue.Queue())
 original=db.open_trade('Fibonacci','BTC-USDT','long',1000,100,99,102,'fixture',quantity=2.5,cost_pct=.0015,policy='quality-v2',setup_key='fixture')
 quote={'bid':99.9,'ask':100}
 engine.open_flip(db,original,quote,1000)
 flip=next(t for t in db.trades() if t['track'].endswith('[FLIP]'))
 assert flip['side']=='short' and flip['entry']==99.9
 assert flip['opened']==1000 and flip['quantity']==2.5 and flip['cost_pct']==.0015
 assert abs(flip['stop']/flip['entry']-1)==pytest.approx(.01)
 assert abs(flip['target']/flip['entry']-1)==pytest.approx(.02)
 assert flip['setup_key']=='fixture'
 engine.open_flip(db,original,quote,1000)
 assert len(db.trades())==2
 assert db.db.execute("select state from entry_attempts where track like '%[FLIP]'").fetchone()[0]=='EXISTING_POSITION'


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
