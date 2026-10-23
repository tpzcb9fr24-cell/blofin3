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
