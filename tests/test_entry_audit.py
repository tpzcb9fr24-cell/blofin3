import json
import queue
import pytest
from strategy_lab.engine import Engine
from strategy_lab.market import Candle
from strategy_lab.store import Store
from strategy_lab.strategies import Settings,Signal
from strategy_lab.diagnostics import decision_history

@pytest.fixture
def setup(tmp_path,monkeypatch):
    import strategy_lab.engine as module
    now=[1792807210.0];asof=1792807200000
    monkeypatch.setattr(module.time,'time',lambda:now[0])
    monkeypatch.setattr(module,'detect',lambda *a,**k:([],[],{}))
    engine=Engine(tmp_path/'db',queue.Queue());engine.settings=Settings(quality_policy=0)
    engine.bars['SOL-USDT']={asof-300000:Candle(asof-300000,100,101,99,100,10,1000)}
    engine.pending[('SOL-USDT',asof)]={'signals':[Signal('Fibonacci','short',asof,100,101,98,'fixture',2)],'entered':set()}
    db=Store(tmp_path/'db')
    return module,engine,db,now,asof

def test_transient_quote_failure_retries_and_opens_once(setup,monkeypatch):
    module,engine,db,now,asof=setup;calls=[]
    def quote(symbol):
        calls.append(1)
        if len(calls)==1:raise ConnectionError('temporary outage fixture')
        return {'bid':100,'ask':100,'time':int(now[0]*1000)}
    monkeypatch.setattr(module,'quote',quote)
    engine.entries(db,'SOL-USDT',asof)
    assert not db.trades()
    assert db.db.execute('select state from entry_attempts').fetchone()[0]=='WAITING_QUOTE'
    engine.entries(db,'SOL-USDT',asof);assert len(calls)==1
    now[0]+=5;engine.entries(db,'SOL-USDT',asof)
    engine.entries(db,'SOL-USDT',asof)
    assert len(db.trades())==1 and len(calls)==2
    row=db.db.execute("select state,attempts from entry_attempts where track='Fibonacci [FLIP]'").fetchone()
    assert tuple(row)==('OPENED',2)
    engine.flush_events(db)
    assert db.db.execute("select count(*) from events where kind='error'").fetchone()[0]==1
    db.close();reopen=Store(engine.path)
    assert reopen.db.execute('select state from entry_attempts').fetchone()[0]=='OPENED'
    reopen.close()

def test_expired_quote_does_not_retry_or_backfill(setup,monkeypatch):
    module,engine,db,now,asof=setup;calls=[]
    def quote(s):calls.append(1);raise TimeoutError('fixture')
    monkeypatch.setattr(module,'quote',quote)
    engine.entries(db,'SOL-USDT',asof);now[0]=asof/1000+91
    engine.entries(db,'SOL-USDT',asof)
    assert len(calls)==1 and not db.trades()
    assert db.db.execute('select state from entry_attempts').fetchone()[0]=='EXPIRED'

def test_http403_backoff_is_shared_across_tracks(setup,monkeypatch):
    module,engine,db,now,asof=setup;calls=[]
    class Denied(Exception):status=403
    def quote(s):calls.append(1);raise Denied('request denied fixture')
    monkeypatch.setattr(module,'quote',quote)
    engine.entries(db,'SOL-USDT',asof);now[0]+=59
    engine.entries(db,'SOL-USDT',asof);assert len(calls)==1
    now[0]+=1;engine.entries(db,'SOL-USDT',asof);assert len(calls)==2
    assert not db.trades()
    detail=json.loads(db.db.execute('select details from entry_attempts').fetchone()[0])
    assert detail['http_status']==403 and detail['retry_seconds']==60

def test_slow_quote_returning_after_deadline_never_fills(setup,monkeypatch):
    module,engine,db,now,asof=setup
    def quote(s):now[0]=asof/1000+91;return {'bid':100,'ask':100,'time':int(now[0]*1000)}
    monkeypatch.setattr(module,'quote',quote);engine.entries(db,'SOL-USDT',asof)
    assert not db.trades()
    assert db.db.execute('select state from entry_attempts').fetchone()[0]=='EXPIRED'

def test_target_rejection_is_durable(setup,monkeypatch):
    module,engine,db,now,asof=setup
    from strategy_lab.targets import OrderBlock
    engine.bars['SOL-USDT'][asof-300000]=Candle(asof-300000,100,101,100,100,10,1000)
    monkeypatch.setattr(module,'detect',lambda *a,**k:([],[OrderBlock(99.9,100.01,'bullish',asof-600000)],{}))
    monkeypatch.setattr(module,'quote',lambda s:{'bid':100,'ask':100,'time':int(now[0]*1000)})
    engine.entries(db,'SOL-USDT',asof)
    assert not db.trades()
    assert db.db.execute('select state from entry_attempts').fetchone()[0]=='REJECTED_TARGET'

def test_report_does_not_invent_historical_rejection(setup):
    module,engine,db,now,asof=setup
    db.save_decision('SOL-USDT',asof,{'signals':[{'strategy':'Fibonacci'}],'notes':{'checks':{'Fibonacci short':{'volume':True}},'quality_checks':[]}})
    report=decision_history(db,now=asof+1000)
    assert 'Base candidates 1' in report
    assert 'Signals without saved entry outcome: 1' in report and 'cause UNKNOWN' in report
    db.entry_attempt('SOL-USDT',asof,'Fibonacci [FLIP]','EXPIRED','fixture reason')
    report=decision_history(db,now=asof+1000)
    assert 'Signals without saved entry outcome: 0' in report
    assert 'EXPIRED' in report and 'fixture reason' in report


def test_waiting_model_is_recorded_once_and_expires(setup,monkeypatch):
    module,engine,db,now,asof=setup
    signal=engine.pending[('SOL-USDT',asof)]['signals'][0]
    engine.pending[('SOL-USDT',asof)]['signals']=[Signal('SMC EMA50',signal.side,asof,100,101,98,'fixture',2)]
    monkeypatch.setattr(module,'quote',lambda s:{'bid':100,'ask':100,'time':int(now[0]*1000)})
    engine.entries(db,'SOL-USDT',asof);engine.entries(db,'SOL-USDT',asof)
    waits=list(db.db.execute("select attempts from entry_attempts where state='WAITING_MODEL'"))
    assert len(waits)==3 and all(r[0]==1 for r in waits)
    now[0]=asof/1000+91;engine.entries(db,'SOL-USDT',asof)
    assert db.db.execute("select count(*) from entry_attempts where state='EXPIRED'").fetchone()[0]==3
    assert len(db.trades())==1

@pytest.mark.parametrize('outcome',['REJECTED_STOP','REJECTED_RISK'])
def test_stop_and_budget_rejections_persist(setup,monkeypatch,outcome):
    import strategy_lab.risk as risk
    module,engine,db,now,asof=setup
    engine.settings=Settings()
    monkeypatch.setattr(module,'quote',lambda s:{'bid':100,'ask':100,'time':int(now[0]*1000)})
    monkeypatch.setattr(risk,'structural_stop',lambda *a:None if outcome=='REJECTED_STOP' else 101)
    monkeypatch.setattr(risk,'size_entry',lambda *a:(None,'exposure limit fixture'))
    engine.entries(db,'SOL-USDT',asof)
    assert not db.trades()
    assert db.db.execute('select state from entry_attempts').fetchone()[0]==outcome
