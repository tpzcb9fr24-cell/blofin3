"""Deterministic candidate-signal replay. NOT a market strategy detector."""
import csv
from dataclasses import dataclass
from pathlib import Path
from .targets import OrderBlock, choose_target

@dataclass(frozen=True)
class ReplayTrade:
    symbol: str
    strategy: str
    side: str
    entry_time: int
    entry: float
    stop: float
    target: float | None
    exit_time: int | None
    exit_price: float | None
    outcome: str
    gross_rr: float

def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def replay(candles_path, signals_path, blocks_path):
    """Use close-time signals and only later bars. Conservative stop-first on ambiguous bars.

    CSV candles: symbol,time,open,high,low,close; time=UNIX milliseconds of candle CLOSE.
    Signals: symbol,time,strategy,side,entry,stop (time=signal close).
    Blocks: symbol,formed_at,low,high,kind,invalidated_at (optional).
    Signals are provided by user/test fixtures; no SMC detection yet.
    """
    candles = read_csv(candles_path)
    signals = read_csv(signals_path)
    blocks = read_csv(blocks_path)
    by_symbol = {}
    for c in candles:
        by_symbol.setdefault(c['symbol'], []).append(c)
    for bars in by_symbol.values():
        bars.sort(key=lambda c: int(c['time']))
    results = []
    for s in signals:
        t = int(s['time']); entry = float(s['entry']); stop = float(s['stop']); side = s['side']
        obs = [OrderBlock(float(b['low']), float(b['high']), b['kind'], int(b['formed_at']),
                          int(b['invalidated_at']) if b.get('invalidated_at') else None)
               for b in blocks if b['symbol'] == s['symbol']]
        decision = choose_target(entry=entry, stop=stop, side=side, blocks=obs, as_of=t)
        if not decision.accepted:
            results.append(ReplayTrade(s['symbol'], s['strategy'], side, t, entry, stop, None, None, None, 'REJECTED: '+decision.reason, 0))
            continue
        target = decision.target
        exit_time = None; exit_price = None; outcome = 'OPEN / NO FILL'; rr = 0.0
        for bar in by_symbol.get(s['symbol'], []):
            if int(bar['time']) <= t:
                continue
            hi,lo = float(bar['high']),float(bar['low'])
            hit_stop = lo <= stop if side == 'long' else hi >= stop
            hit_tp = hi >= target if side == 'long' else lo <= target
            if hit_stop or hit_tp:
                # A bar's OHLC cannot reveal order of stop/target touches. Stop-first is conservative.
                exit_price = stop if hit_stop else target
                exit_time = int(bar['time'])
                outcome = 'STOP' if hit_stop else 'TARGET'
                rr = (exit_price-entry)/(entry-stop) if side == 'long' else (entry-exit_price)/(stop-entry)
                break
        results.append(ReplayTrade(s['symbol'],s['strategy'],side,t,entry,stop,target,exit_time,exit_price,outcome,rr))
    return results
