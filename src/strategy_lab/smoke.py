import json
import time
from pathlib import Path
from .market import history, contiguous, CRYPTO_SYMBOLS as SYMBOLS
from .models import Models

def live_smoke():
    results={}
    for symbol in SYMBOLS:
        bars=history(symbol)
        closed=[c for c in bars if c.confirmed]
        assert len(closed)>=60 and contiguous(closed),symbol+' missing candle history'
        assert 0<=time.time()*1000-closed[-1].end<600000,symbol+' stale'
        results[symbol]={'bars':len(bars),'last_close':closed[-1].end,'price':bars[-1].close}
    Path('live-smoke.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results))

def model_smoke():
    models=Models();bars=[c for c in history('BTC-USDT') if c.confirmed]
    results={}
    for name in ('Kronos','TimesFM'):
        start=time.monotonic();forecast=models.predict(name,bars)
        assert len(forecast['values'])==6
        forecast['latency_seconds']=time.monotonic()-start
        results[name]=forecast
    # Genuine inference on clearly synthetic ETF input checks session-aware plumbing only.
    # It is never a substitute for live SPY/QQQ acceptance using a configured data key.
    from .instruments import future_times
    from .market import Candle
    from datetime import datetime,timezone
    start=int(datetime(2026,11,27,14,30,tzinfo=timezone.utc).timestamp()*1000)
    times=[start]+future_times('SPY',start,79)
    fixture=[Candle(t,500+i*.01,500.2+i*.01,499.8+i*.01,500.05+i*.01,1000,1000*(500.05+i*.01)) for i,t in enumerate(times)]
    results['ETF_synthetic_input_only']={name:models.predict(name,fixture,symbol='SPY') for name in ('Kronos','TimesFM')}
    results['ETF_live_acceptance']='BLOCKED: user-provided market-data key not configured on build runner'
    Path('model-smoke.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results))


def desktop_smoke():
    """Run the real UI and workers; verify live feeds, inference and persistence."""
    import tempfile
    from .app import App
    from .store import Store
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'acceptance.sqlite3';app=App(path,start=True)
        started=time.monotonic();failure=None
        try:
            while time.monotonic()-started<100:
                app.update();time.sleep(.05)
                if len(app.market)==3 and all(app.models.get((s,n),{}).get('forecast') for s in SYMBOLS for n in ('Kronos','TimesFM')):
                    break
            assert len(app.market)==3,'Not all live markets loaded'
            assert all(app.models.get((s,n),{}).get('forecast') for s in SYMBOLS for n in ('Kronos','TimesFM')),str({str(k):v['status'] for k,v in app.models.items()})
            before={s:bars[-1].close for s,bars in app.market.items()}
            received=dict(app.received)
            end=time.monotonic()+6
            while time.monotonic()<end:app.update();time.sleep(.05)
            assert any(app.received[s]>received[s] for s in SYMBOLS),'No advancing live updates'
            app.fields['Symbol'].set('BTC-USDT');app.prefill_quote();app.manual_open()
            assert any(t['source']=='manual' for t in app.store.trades())
            result={'platform':__import__('platform').platform(),'elapsed_s':time.monotonic()-started,
                    'live_symbols':list(app.market),'model_forecasts':{str(k):v['forecast'] for k,v in app.models.items()},
                    'manual_recorded':True,'live_updates_advanced':True}
            app.shutdown()
            # Let worker stop before deleting the test database on Windows.
            for thread in app.engine.threads:thread.join(timeout=20)
            store=Store(path);assert any(t['source']=='manual' for t in store.trades());store.close()
            result['journal_survived_restart']=True
            Path('desktop-smoke.json').write_text(json.dumps(result,indent=2))
        except Exception:
            try:app.shutdown()
            except Exception:pass
            raise


def offline_model_smoke():
    """Genuine local weights on explicitly synthetic inputs; zero market-data calls."""
    import math
    from .market import Candle
    from .instruments import future_times
    from datetime import datetime,timezone
    models=Models();results={'input_basis':'SYNTHETIC FIXTURES ONLY; NOT LIVE DATA',
                             'live_crypto_acceptance':'NOT TESTED by this offline check',
                             'live_ETF_acceptance':'NOT TESTED by this offline check'}
    crypto_start=int(datetime(2026,10,20,tzinfo=timezone.utc).timestamp()*1000)
    etf_start=int(datetime(2026,11,27,14,30,tzinfo=timezone.utc).timestamp()*1000)
    for symbol,start,base in [('BTC-USDT',crypto_start,80000),('SPY',etf_start,500)]:
        times=[start]+future_times(symbol,start,95)
        fixture=[]
        for i,t in enumerate(times):
            value=base*(1+.0002*i+.001*math.sin(i/5))
            fixture.append(Candle(t,value,value*1.002,value*.998,value*1.0001,1000,1000*value))
        results[symbol]={}
        for name in ('Kronos','TimesFM'):
            f=models.predict(name,fixture,symbol=symbol)
            assert len(f['values'])==6 and len(f['target_times'])==6
            results[symbol][name]=f
    Path('offline-model-smoke.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results))


def offline_desktop_smoke():
    """Installed GUI + real ledger/engine flip exits, synthetic prices, temporary DB only."""
    import tempfile
    import math
    from .app import App
    from .store import Store
    from .market import Candle
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'fixture-only.sqlite3';app=App(path,start=False)
        from .strategies import Settings
        app.engine.settings=Settings()
        try:
            t=1793000000000//300000*300000
            original=app.store.open_trade('Fibonacci','BTC-USDT','long',t+1,100,99,102,'OFFLINE FIXTURE ONLY',quantity=2.5,cost_pct=.0015,policy='quality-v2',setup_key='fixture-only')
            app.engine.open_flip(app.store,original,{'bid':99.9,'ask':100},t)
            rows=app.store.trades();flip=next(r for r in rows if r['track'].endswith('[FLIP]'))
            assert flip['opened']==t+1 and flip['quantity']==2.5 and flip['side']=='short'
            assert math.isclose(abs(flip['stop']/flip['entry']-1),.01)
            assert math.isclose(abs(flip['target']/flip['entry']-1),.02)
            # Flip can stop out first while the original remains open.
            app.engine.paper_exits(app.store,'BTC-USDT',Candle(t+300000,100,101.1,99.5,101,10,1000))
            rows=app.store.trades();assert next(r for r in rows if r['id']==original)['closed'] is None
            assert next(r for r in rows if r['id']==flip['id'])['closed'] is not None
            app.engine.paper_exits(app.store,'BTC-USDT',Candle(t+600000,101,102.2,100.5,102,10,1000))
            rows=app.store.trades();assert all(r['closed'] is not None for r in rows)
            app.render_trades(rows);app.update()
            assert app.trades.set(str(flip['id']),'track')=='Fibonacci [FLIP]'
            assert any(app.summary.item(i,'values')[0]=='Fibonacci [FLIP]' for i in app.summary.get_children())
            dialog=app.history_dialog();app.update();dialog.destroy()
            result={'input_basis':'SYNTHETIC FIXTURE ONLY; NOT LIVE DATA','original_and_flip_recorded':True,
                    'same_size_timestamp_costs_and_percentage_distances':True,'independent_engine_exits':True,
                    'gui_flip_visible':True,'platform':__import__('platform').platform()}
            app.shutdown();app=None
            db=Store(path);saved=db.trades();assert len(saved)==2 and all(r['closed'] is not None for r in saved);db.close()
            result['journal_survived_restart']=True
            Path('offline-desktop-smoke.json').write_text(json.dumps(result,indent=2))
        finally:
            if app is not None:app.shutdown()
