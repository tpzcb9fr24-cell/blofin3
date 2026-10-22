"""Developer-only actual UI acceptance helper."""
import json
import tempfile
import time
from pathlib import Path
from strategy_lab.app import App
from strategy_lab.market import SYMBOLS

with tempfile.TemporaryDirectory() as folder:
    app=App(Path(folder)/'probe.sqlite3',start=True)
    start=time.monotonic()
    try:
        while time.monotonic()-start<100:
            app.update();time.sleep(.05)
            if len(app.market)==3 and all(app.models.get((s,n),{}).get('forecast') for s in SYMBOLS for n in ('Kronos','TimesFM')):break
        assert len(app.market)==3
        assert all(app.models.get((s,n),{}).get('forecast') for s in SYMBOLS for n in ('Kronos','TimesFM'))
        for symbol in SYMBOLS:
            app.symbol.set(symbol);app.render_chart();app.render_trades(app.rows);app.update()
            assert len(app.decisions.get_children())==10
        app.symbol.set('BTC-USDT');app.render_chart();app.update()
        try:
            from Xlib import display, X
            from PIL import Image
            screen=display.Display();root=screen.screen().root
            raw=root.get_image(0,0,1440,1000,X.ZPixmap,0xffffffff)
            Image.frombytes('RGB',(1440,1000),raw.data,'raw','BGRX').save('/tmp/blofin-ui.png')
        except ImportError:pass
        print(json.dumps({'live_symbols':list(app.market),'model_pairs':len(app.models),'decision_tracks':len(app.decisions.get_children()),'duration_s':time.monotonic()-start}))
    finally:
        app.shutdown()
        for thread in app.engine.threads:thread.join(timeout=20)
