"""Read-only Twelve Data ETF adapter. Data key never enters a URL, log, or SQLite."""
import ctypes as ct
import json
import math
import os
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
from .instruments import ETF_SYMBOLS,STEP,valid_bar,market_open,calendar

class DataUnavailable(RuntimeError):pass

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class _Blob(ct.Structure):
    _fields_=[('size',ct.c_uint32),('data',ct.POINTER(ct.c_ubyte))]

def _crypt(data,protect):
    if sys.platform!='win32':raise DataUnavailable('Saved data keys require Windows protected storage; use the process environment for development')
    buffer=ct.create_string_buffer(data);source=_Blob(len(data),ct.cast(buffer,ct.POINTER(ct.c_ubyte)));dest=_Blob()
    crypt=ct.WinDLL('crypt32',use_last_error=True);kernel=ct.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ct.c_void_p];kernel.LocalFree.restype=ct.c_void_p
    if protect:
        fn=crypt.CryptProtectData;fn.argtypes=[ct.POINTER(_Blob),ct.c_wchar_p,ct.c_void_p,ct.c_void_p,ct.c_void_p,ct.c_uint32,ct.POINTER(_Blob)]
        ok=fn(ct.byref(source),'BloFin observer market data',None,None,None,1,ct.byref(dest))
    else:
        fn=crypt.CryptUnprotectData;fn.argtypes=[ct.POINTER(_Blob),ct.c_void_p,ct.c_void_p,ct.c_void_p,ct.c_void_p,ct.c_uint32,ct.POINTER(_Blob)]
        ok=fn(ct.byref(source),None,None,None,None,1,ct.byref(dest))
    if not ok:raise DataUnavailable('Windows could not access the protected market-data key')
    try:return ct.string_at(dest.data,dest.size)
    finally:kernel.LocalFree(dest.data)

def save_key(path,key):
    key=key.strip()
    if not key or len(key)>512 or any(c.isspace() for c in key):raise ValueError('Enter a valid market-data-only key')
    data=_crypt(key.encode(),True);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)

def load_key(path):
    key=os.environ.get('TWELVE_DATA_API_KEY','').strip()
    if key:return key
    if Path(path).is_file():return _crypt(Path(path).read_bytes(),False).decode()
    return ''

def request(endpoint,symbol,key,**params):
    if endpoint not in ('time_series','quote') or symbol not in ETF_SYMBOLS:raise ValueError('Only SPY/QQQ market-data endpoints are allowed')
    if not key:raise DataUnavailable('SPY/QQQ need a Twelve Data market-data key; open ETF data setup')
    url='https://api.twelvedata.com/'+endpoint+'?'+urlencode(dict(symbol=symbol,**params))
    req=Request(url,headers={'Authorization':'apikey '+key,'Accept':'application/json','User-Agent':'BloFinObserver/0.3.0'})
    try:
        with build_opener(_NoRedirect()).open(req,timeout=15) as response:
            data=response.read(4*1024*1024+1)
        if len(data)>4*1024*1024:raise DataUnavailable('ETF data response too large')
        payload=json.loads(data)
    except HTTPError as exc:raise DataUnavailable(f'ETF data HTTP {exc.code}; check key, entitlement, or provider limit') from None
    except DataUnavailable:raise
    except Exception:raise DataUnavailable('ETF data request failed; no substitute feed used') from None
    if payload.get('status')=='error':
        raise DataUnavailable('ETF provider rejected request (code '+str(payload.get('code','unknown'))+'); check key, entitlement or request limit')
    return payload

def parse_history(payload,symbol,now_ms):
    from .market import Candle
    meta=payload.get('meta',{})
    if meta.get('symbol')!=symbol or meta.get('interval')!='5min' or meta.get('currency')!='USD':raise DataUnavailable('Unexpected ETF metadata')
    if meta.get('exchange_timezone') not in ('America/New_York','US/Eastern'):raise DataUnavailable('Unexpected ETF exchange timezone')
    result={}
    for row in payload.get('values',[]):
        t=int(datetime.strptime(row['datetime'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
        values=[float(row[k]) for k in ('open','high','low','close','volume')];o,h,l,c,v=values
        if not valid_bar(symbol,t) or not all(math.isfinite(x) for x in values) or min(o,h,l,c)<=0 or v<0 or l>min(o,c) or h<max(o,c) or t>now_ms:raise DataUnavailable('Invalid ETF OHLCV/session timestamp')
        # Provider has share volume, not traded dollar volume. The Kronos input proxy is explicit.
        result[t]=Candle(t,o,h,l,c,v,v*c,t+STEP+3000<=now_ms)
    if not result:raise DataUnavailable('No regular-session ETF bars returned')
    return sorted(result.values(),key=lambda c:c.time)

def history(symbol,key,count=512):
    payload=request('time_series',symbol,key,interval='5min',outputsize=min(512,count),timezone='UTC',prepost='false',adjust='splits',order='desc')
    return parse_history(payload,symbol,int(time.time()*1000))

def quote(symbol,key):
    # /quote's stock timestamp can identify the daily bar open, not its last price update.
    # Use a timestamped one-minute bar instead; never invent a fresh tick timestamp.
    payload=request('time_series',symbol,key,interval='1min',outputsize=1,timezone='UTC',prepost='false',adjust='splits',order='desc')
    if payload.get('meta',{}).get('symbol')!=symbol or payload.get('meta',{}).get('interval')!='1min' or payload.get('meta',{}).get('currency')!='USD':raise DataUnavailable('Unexpected ETF indicative-price metadata')
    rows=payload.get('values',[])
    if not rows:raise DataUnavailable('No ETF indicative price')
    row=rows[0];price=float(row['close'])
    timestamp=int(datetime.strptime(row['datetime'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
    if not math.isfinite(price) or price<=0 or not market_open(symbol,timestamp):raise DataUnavailable('Invalid ETF indicative price/session')
    return {'price':price,'time':timestamp,'basis':'Twelve Data one-minute indicative close (maximum age 90s); no executable bid/ask; ETF costs include estimated spread'}

def next_poll(ms):
    if market_open('SPY',ms):return (ms//STEP+1)*STEP+5000
    # One final reconciliation immediately after the close; then sleep until next open.
    from .instruments import session_bounds
    bounds=session_bounds(ms)
    if bounds and bounds[1]<=ms<bounds[1]+30000:return ms+30000
    import pandas as pd
    return int(calendar().next_open(pd.Timestamp(ms,unit='ms',tz='UTC')).value//1000000)+5000
