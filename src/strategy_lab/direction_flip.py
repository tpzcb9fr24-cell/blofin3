"""Direction-only paper comparison; never changes distance, quantity or costs."""
import math

SUFFIX=' [FLIP]'

def flip_plan(side,entry,stop,target,fill=None):
    if side not in ('long','short') or not all(math.isfinite(v) and v>0 for v in (entry,stop,target)):
        raise ValueError('Invalid original plan')
    if not (stop<entry<target if side=='long' else target<entry<stop):raise ValueError('Original plan must bracket entry')
    price=entry if fill is None else fill
    if not math.isfinite(price) or price<=0:raise ValueError('Invalid flipped fill')
    stop_distance=abs(stop/entry-1);target_distance=abs(target/entry-1)
    direction=-1 if side=='long' else 1
    plan={'side':'short' if side=='long' else 'long','entry':price,
          'stop':price*(1-direction*stop_distance),'target':price*(1+direction*target_distance)}
    if plan['stop']<=0 or plan['target']<=0:raise ValueError('Flipped plan has non-positive price')
    return plan

def replay_flip(trade,bars):
    """Same recorded entry price/time, size/cost. OHLC replay, no invented entry ticks.

    Entry-candle boundary touches or missing bars make the result unresolvable.
    Later both-boundary candles use conservative stop-first and are flagged.
    This is a retrospective diagnostic, not live execution or a new OB strategy.
    """
    p=flip_plan(trade['side'],trade['entry'],trade['stop'],trade['target'])
    start=trade['opened']//300000*300000
    bars=sorted((b for b in bars if b['time']>=start and b.get('confirmed',True)),key=lambda b:b['time'])
    previous=start-300000
    for b in bars:
        if b['time']!=previous+300000:return dict(p,outcome='MISSING_BARS',net=None)
        previous=b['time'];long=p['side']=='long'
        stop=b['low']<=p['stop'] if long else b['high']>=p['stop']
        target=b['high']>=p['target'] if long else b['low']<=p['target']
        if b['time']<trade['opened'] and (stop or target):return dict(p,outcome='ENTRY_BAR_UNCERTAIN',net=None)
        if stop or target:
            price=(min(b['open'],p['stop']) if long else max(b['open'],p['stop'])) if stop else p['target']
            net=(1 if long else -1)*(price/p['entry']-1)-trade['cost_pct']
            return dict(p,outcome='STOP_FIRST_AMBIGUOUS' if stop and target else 'STOP' if stop else 'TARGET',net=net,exit=price,closed=b['time']+300000)
    return dict(p,outcome='OPEN' if bars else 'MISSING_BARS',net=None)
