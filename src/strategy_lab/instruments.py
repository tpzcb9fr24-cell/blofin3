"""Instrument metadata and official-session continuity (no fabricated gap candles)."""
from functools import lru_cache

CRYPTO_SYMBOLS=('BTC-USDT','ETH-USDT','SOL-USDT')
ETF_SYMBOLS=('SPY','QQQ')
SYMBOLS=CRYPTO_SYMBOLS+ETF_SYMBOLS
STEP=300000

@lru_cache(maxsize=1)
def calendar():
    import exchange_calendars as xc
    return xc.get_calendar('XNYS',start='2020-01-01',end='2035-12-31')

def session_bounds(ms):
    import pandas as pd
    c=calendar();day=pd.Timestamp(ms,unit='ms',tz='UTC').tz_convert('America/New_York').date().isoformat()
    if not c.is_session(day):return None
    return int(c.session_open(day).value//1000000),int(c.session_close(day).value//1000000)

def market_open(symbol,ms):
    if symbol in CRYPTO_SYMBOLS:return True
    bounds=session_bounds(ms)
    return bool(bounds and bounds[0]<=ms<bounds[1])

def valid_bar(symbol,ms):
    if ms%STEP:return False
    if symbol in CRYPTO_SYMBOLS:return True
    bounds=session_bounds(ms)
    return bool(bounds and bounds[0]<=ms and ms+STEP<=bounds[1])

@lru_cache(maxsize=8192)
def next_bar(symbol,ms):
    candidate=ms+STEP
    if symbol not in ETF_SYMBOLS or valid_bar(symbol,candidate):return candidate
    import pandas as pd
    return int(calendar().next_open(pd.Timestamp(ms,unit='ms',tz='UTC')).value//1000000)

def future_times(symbol,last_open,count):
    result=[]
    for _ in range(count):last_open=next_bar(symbol,last_open);result.append(last_open)
    return result
