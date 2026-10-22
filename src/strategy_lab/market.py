"""Public-only BloFin transport. No credentials or exchange write methods."""
import json
import math
import logging
from dataclasses import dataclass, asdict
from .transport import get_json
from urllib.parse import urlencode

SYMBOLS = ('BTC-USDT', 'ETH-USDT', 'SOL-USDT')
INTERVAL = 300_000

@dataclass(frozen=True)
class Candle:
    time: int  # OPEN timestamp, always UTC and aligned to five minutes
    open: float
    high: float
    low: float
    close: float
    volume: float  # base currency, NOT contracts
    amount: float  # quote currency
    confirmed: bool = True

    @property
    def end(self):
        return self.time + INTERVAL

    def dict(self):
        return asdict(self)


def parse_candle(row):
    if len(row) != 9:
        raise ValueError('Unexpected BloFin candle schema')
    t = int(row[0])
    values = [float(v) for v in row[1:8]]
    o, h, l, c, contracts, volume, amount = values
    if t % INTERVAL or not all(math.isfinite(v) for v in values):
        raise ValueError('Non-finite or misaligned candle')
    if min(o, h, l, c) <= 0 or l > min(o, c) or h < max(o, c) or min(contracts, volume, amount) < 0:
        raise ValueError('Invalid OHLCV: '+repr(row))
    if str(row[8]) not in ('0', '1'):
        raise ValueError('Invalid confirmation flag')
    return Candle(t, o, h, l, c, volume, amount, str(row[8]) == '1')


def contiguous(bars):
    return all(b.time - a.time == INTERVAL for a, b in zip(bars, bars[1:]))


def public_get(symbol, limit=300, before=None):
    if symbol not in SYMBOLS:
        raise ValueError('Unsupported instrument')
    params = dict(instId=symbol, bar='5m', limit=str(limit))
    if before is not None:
        params['after'] = str(before)  # BloFin: older than timestamp
    url = 'https://openapi.blofin.com/api/v1/market/candles?' + urlencode(params)
    payload=get_json(url,timeout=15)
    if payload.get('code') != '0':
        raise RuntimeError('BloFin: ' + str(payload.get('msg', payload)))
    parsed=[]
    for row in payload['data']:
        try:parsed.append(parse_candle(row))
        except ValueError:
            # An inconsistent developing candle is not model input. Do not
            # repair it or reject valid finalized history alongside it.
            if len(row)==9 and str(row[-1])=='0':
                logging.warning('Rejected malformed developing BloFin candle: %s',row)
                continue
            raise
    return sorted(parsed,key=lambda c:c.time)


def history(symbol, count=512):
    result = {}
    before = None
    for _ in range(5):
        page = public_get(symbol, min(300, count), before)
        if not page:
            break
        old = len(result)
        result.update({c.time: c for c in page})
        if len(result) >= count or len(result) == old:
            break
        before = page[0].time
    return sorted(result.values(), key=lambda c: c.time)[-count:]


def quote(symbol):
    if symbol not in SYMBOLS:raise ValueError('Unsupported instrument')
    url='https://openapi.blofin.com/api/v1/market/tickers?'+urlencode({'instId':symbol})
    payload=get_json(url,timeout=10)
    if payload.get('code')!='0' or len(payload.get('data',[]))!=1:raise ValueError('Invalid quote response')
    row=payload['data'][0];bid,ask=float(row['bidPrice']),float(row['askPrice']);timestamp=int(row['ts'])
    if not (0<bid<=ask and math.isfinite(ask)):raise ValueError('Invalid bid/ask')
    return {'bid':bid,'ask':ask,'time':timestamp}
