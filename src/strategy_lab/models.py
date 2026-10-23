"""Actual local CPU model inference. Errors propagate; there are no proxies."""
import math
import time
import os
import sys
from pathlib import Path

KRONOS_ID='NeoQuasar/Kronos-small'
TOKENIZER_ID='NeoQuasar/Kronos-Tokenizer-base'
TIMESFM_ID='google/timesfm-2.5-200m-pytorch'


def assets_root():
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'model-assets'


class Models:
    def __init__(self):
        self.kronos=None; self.timesfm=None

    def load(self,name):
        import torch
        torch.set_num_threads(min(4,os.cpu_count() or 1))
        root=assets_root()
        if name=='Kronos' and self.kronos is None:
            from model import Kronos, KronosTokenizer, KronosPredictor
            tokenizer=KronosTokenizer.from_pretrained(str(root/'tokenizer'),local_files_only=True)
            model=Kronos.from_pretrained(str(root/'kronos'),local_files_only=True)
            model.eval(); tokenizer.eval()
            self.kronos=KronosPredictor(model,tokenizer,device='cpu',max_context=512)
        elif name=='TimesFM' and self.timesfm is None:
            import timesfm
            self.timesfm=timesfm.TimesFM_2p5_200M_torch.from_pretrained(str(root/'timesfm'),torch_compile=False,local_files_only=True)
            self.timesfm.compile(timesfm.ForecastConfig(max_context=512,max_horizon=32,normalize_inputs=True))

    def predict(self,name,bars,horizon=6,symbol=None):
        import numpy as np
        import pandas as pd
        import torch
        from .market import contiguous
        if len(bars)<60 or not contiguous(bars,symbol) or any(not c.confirmed for c in bars):
            raise ValueError('Model needs contiguous confirmed bars')
        bars=bars[-512:]
        from .instruments import future_times,ETF_SYMBOLS
        targets=future_times(symbol,bars[-1].time,horizon)
        started=time.monotonic()
        self.load(name)
        with torch.inference_mode():
            if name=='Kronos':
                torch.manual_seed(42)
                df=pd.DataFrame([{k:getattr(c,k) for k in ('open','high','low','close','volume','amount')} for c in bars])
                timestamps=pd.Series(pd.to_datetime([c.time for c in bars],unit='ms'))
                future=pd.Series(pd.to_datetime(targets,unit='ms'))
                output=self.kronos.predict(df=df,x_timestamp=timestamps,y_timestamp=future,
                                           pred_len=horizon,T=1.0,top_p=.9,sample_count=1,verbose=False)
                values=[float(x) for x in output['close']]
                checkpoint=KRONOS_ID
            elif name=='TimesFM':
                point,_=self.timesfm.forecast(horizon=horizon,inputs=[np.array([c.close for c in bars],dtype=np.float32)])
                values=[float(x) for x in point[0]]
                checkpoint=TIMESFM_ID
            else:
                raise ValueError('Unknown model')
        if len(values)!=horizon or not all(math.isfinite(x) and x>0 for x in values):
            raise ValueError('Invalid model forecast')
        return {'values':values,'asof':bars[-1].end,'checkpoint':checkpoint,'seed':42 if name=='Kronos' else None,
                'target_times':targets,'time_basis':'regular-session bars; amount=close*share volume proxy' if symbol in ETF_SYMBOLS else 'UTC continuous five-minute bars','context':len(bars),'horizon':horizon,'interval_ms':300000,'created_ms':int(time.time()*1000),'latency_s':time.monotonic()-started}


def agrees(forecast,side,entry,asof):
    # Forecast must belong to this exact closed candle; no stale model gating.
    return bool(forecast and forecast['asof']==asof and
                (forecast['values'][-1]>entry if side=='long' else forecast['values'][-1]<entry))
