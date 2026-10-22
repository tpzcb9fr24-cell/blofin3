"""Opposing order-block aware target selection; pure and backtest-safe."""
import math
from dataclasses import dataclass
from typing import Literal, Iterable

Side = Literal['long', 'short']
Kind = Literal['bullish', 'bearish']

@dataclass(frozen=True)
class OrderBlock:
    low: float
    high: float
    kind: Kind
    formed_at: int  # candle close timestamp in milliseconds
    invalidated_at: int | None = None

@dataclass(frozen=True)
class TargetDecision:
    accepted: bool
    target: float | None
    original_target: float
    gross_rr: float
    net_reward_pct: float
    reason: str
    blocking_order_block: OrderBlock | None = None
    buffer_pct: float = 0.0


def choose_target(*, entry: float, stop: float, side: Side, blocks: Iterable[OrderBlock],
                  as_of: int, desired_rr: float = 2.0, buffer_pct: float = 0.0005,
                  roundtrip_cost_pct: float = 0.0015) -> TargetDecision:
    """Cap target before nearest *known active* opposing OB; never require 2R.

    roundtrip_cost_pct is an entry-notional approximation of fees+slippage.
    Only blocks formed by as_of and not invalidated by as_of are eligible.
    """
    if not all(math.isfinite(x) for x in (entry,stop,desired_rr,buffer_pct,roundtrip_cost_pct)):
        raise ValueError('Finite prices and parameters required')
    if entry <= 0 or stop <= 0 or desired_rr <= 0 or not (0 <= buffer_pct < 1) or roundtrip_cost_pct < 0:
        raise ValueError('Invalid price or parameter')
    if side not in ('long', 'short'):
        raise ValueError('Invalid side')
    if (side == 'long' and stop >= entry) or (side == 'short' and stop <= entry):
        raise ValueError('Stop must be on loss side of entry')
    risk = abs(entry - stop)
    original = entry + desired_rr * risk if side == 'long' else entry - desired_rr * risk
    if original <= 0:
        return TargetDecision(False, None, original, 0, 0, 'nonpositive_target')
    candidates = []
    blockers = {}
    for b in blocks:
        if not all(math.isfinite(x) for x in (b.low,b.high)) or b.low <= 0 or b.high <= b.low or b.formed_at > as_of:
            continue
        if b.invalidated_at is not None and b.invalidated_at <= as_of:
            continue
        if side == 'long' and b.kind == 'bearish' and b.high > entry and b.low <= original:
            candidates.append(b.low * (1 - buffer_pct)); blockers[candidates[-1]]=b
        elif side == 'short' and b.kind == 'bullish' and b.low < entry and b.high >= original:
            candidates.append(b.high * (1 + buffer_pct)); blockers[candidates[-1]]=b
    target = (min([original] + candidates) if side == 'long'
              else max([original] + candidates))
    reward = (target - entry) if side == 'long' else (entry - target)
    net_pct = reward / entry - roundtrip_cost_pct
    accepted = reward > 0 and net_pct > 0
    return TargetDecision(accepted, target if accepted else None, original,
                          max(0, reward / risk), net_pct,
                          'accepted_capped' if accepted and candidates else 'accepted_2r' if accepted else 'insufficient_net_reward',blockers.get(target),buffer_pct)
