"""Explicit causal interpretations; user annotated entry validation outstanding.

Pivots require two right bars. Only confirmed bars enter this module.
No historical signal is relabelled with information from a future candle.
"""
from dataclasses import dataclass
from .targets import OrderBlock, choose_target
from .market import contiguous

@dataclass(frozen=True)
class Settings:
    stop_pct: float = .0075
    rr: float = 2.
    buffer_pct: float = .0005
    cost_pct: float = .0015
    volume_multiple: float = 1.
    pivot: int = 2
    fib_shallow: float = .5
    fib_deep: float = .618
    fib_extension: float = 1.618

    quality_policy: int = 1
    min_net_rr: float = 1.0
    atr_buffer: float = .25
    risk_fraction: float = .0025
    max_open_risk: float = .01
    group_open_risk: float = .005
    daily_loss_fraction: float = .01
    initial_equity: float = 10000.
    equity_cost_pct: float = .0005

    def validate(self):
        import math
        from dataclasses import asdict
        if not all(math.isfinite(v) for v in asdict(self).values()):raise ValueError('Finite settings required')
        if self.quality_policy not in (0,1) or not 0<=self.min_net_rr<=10 or not 0<=self.atr_buffer<=5:raise ValueError('Invalid quality policy')
        if not 0<self.risk_fraction<=self.group_open_risk<=self.max_open_risk<=.1 or not 0<self.daily_loss_fraction<=.1 or not self.initial_equity>=100:raise ValueError('Invalid paper-account risk budgets')
        if not 0<=self.equity_cost_pct<.05:raise ValueError('ETF costs must be 0–5%')
        if not 0 < self.stop_pct < .2 or not 0 < self.rr <= 20:
            raise ValueError('Stop must be 0–20%; RR must be 0–20')
        if not 0 <= self.buffer_pct < .05 or not 0 <= self.cost_pct < .05:
            raise ValueError('Buffer and costs must be 0–5%')
        if not 0 < self.volume_multiple <= 10 or not 1 <= self.pivot <= 10:
            raise ValueError('Invalid volume or pivot setting')
        if not 0<self.fib_shallow<self.fib_deep<1 or not 1<=self.fib_extension<=5:
            raise ValueError('Fib retracements require 0 < shallow < deep < 1; extension 1–5')
        return self

@dataclass(frozen=True)
class Signal:
    strategy: str
    side: str
    time: int
    entry: float
    stop: float
    target: float
    reason: str
    rr: float


def pivots(bars, n=2):
    highs, lows = [], []
    for i in range(n, len(bars)-n):
        segment = bars[i-n:i+n+1]
        if all(bars[i].high > c.high for j,c in enumerate(segment) if j != n):
            highs.append((i, bars[i].high))
        if all(bars[i].low < c.low for j,c in enumerate(segment) if j != n):
            lows.append((i, bars[i].low))
    return highs, lows


def structure(bars, n=2):
    """Retain blocks formed in supplied history; invalidate on far-edge wick only."""
    blocks, gaps, trend, events = [], [], 0, []
    highs, lows = pivots(bars, n)
    known_h, known_l, broken_h, broken_l = None, None, set(), set()
    high_map, low_map = dict(highs), dict(lows)
    for i, c in enumerate(bars):
        # Invalidation is evaluated BEFORE newly confirmed structures are created.
        blocks = [OrderBlock(b.low,b.high,b.kind,b.formed_at,
                  c.end if b.invalidated_at is None and
                  ((b.kind=='bullish' and c.low < b.low) or
                   (b.kind=='bearish' and c.high > b.high)) else b.invalidated_at) for b in blocks]
        gaps = [(lo,hi,side,t,invalid or (c.low < lo if side=='long' else c.high > hi))
                for lo,hi,side,t,invalid in gaps]
        if i-n in high_map:
            known_h=(i-n,high_map[i-n])
        if i-n in low_map:
            known_l=(i-n,low_map[i-n])
        direction = 0
        if known_h and known_h[0] not in broken_h and c.close > known_h[1]:
            direction=1; broken_h.add(known_h[0])
        elif known_l and known_l[0] not in broken_l and c.close < known_l[1]:
            direction=-1; broken_l.add(known_l[0])
        if direction:
            event='CHoCH' if trend and trend!=direction else 'BOS'
            events.append((i,direction,event)); trend=direction
            for j in range(i-1,max(-1,i-21),-1):
                prev=bars[j]
                if (direction==1 and prev.close<prev.open) or (direction==-1 and prev.close>prev.open):
                    # Block must not already have been pierced between origin and recognition.
                    invalid=any(x.low<prev.low if direction==1 else x.high>prev.high for x in bars[j+1:i+1])
                    if not invalid:
                        blocks.append(OrderBlock(prev.low,prev.high,'bullish' if direction==1 else 'bearish',c.end))
                    break
        if i>=2:
            if c.low>bars[i-2].high:
                gaps.append((bars[i-2].high,c.low,'long',c.end,False))
            elif c.high<bars[i-2].low:
                gaps.append((c.high,bars[i-2].low,'short',c.end,False))
    return blocks, gaps, trend, events


def ema(bars, span=50):
    value=bars[0].close
    for c in bars[1:]:
        value += 2/(span+1)*(c.close-value)
    return value


def detect(bars, settings=Settings(), known_blocks=(), symbol=None):
    settings.validate()
    if len(bars)<60 or any(not c.confirmed for c in bars) or not contiguous(bars,symbol):
        return [], [], {'status':'Waiting for 60 contiguous confirmed five-minute bars'}
    blocks,gaps,trend,events=structure(bars,settings.pivot)
    asof=bars[-1].end
    merged={(b.formed_at,b.kind,b.low,b.high):b for b in blocks}
    for b in known_blocks:
        if b.formed_at<=asof:
            key=(b.formed_at,b.kind,b.low,b.high)
            current=merged.get(key)
            invalids=[t for t in (b.invalidated_at,current.invalidated_at if current else None) if t is not None and t<=asof]
            merged[key]=OrderBlock(b.low,b.high,b.kind,b.formed_at,min(invalids) if invalids else None)
    blocks=list(merged.values())
    c=bars[-1]; previous=bars[-2]; i=len(bars)-1
    highs,lows=pivots(bars,settings.pivot)
    average=sum(x.volume for x in bars[-21:-1])/20
    volume=c.volume>=average*settings.volume_multiple and average>0
    ev=events[-1] if events else None
    recent=ev and i-ev[0]<=10
    candidates=[]
    notes={'status':'Monitoring', 'ema50':ema(bars), 'volume_ratio':c.volume/average if average else 0,
           'structure':f'{ev[2]} {"bullish" if ev[1]==1 else "bearish"}' if ev else 'None'}
    notes['checks']={}
    notes['gaps']=[{'low':lo,'high':hi,'side':side,'formed_at':t,'invalidated':invalid} for lo,hi,side,t,invalid in gaps]
    notes['pivot_highs']=highs;notes['pivot_lows']=lows
    for side,direction in [('long',1),('short',-1)]:
        rejection=c.close>c.open if direction==1 else c.close<c.open
        zone=any(b.invalidated_at is None and b.formed_at<c.end and
                 b.kind==('bullish' if direction==1 else 'bearish') and
                 c.low<=b.high and c.high>=b.low for b in blocks)
        zone=zone or any(not invalid and t<c.end and s==side and c.low<=hi and c.high>=lo
                         for lo,hi,s,t,invalid in gaps)
        anchor=lows if direction==1 else highs
        trendline=False
        if len(anchor)>=2:
            (a,p),(b,q)=anchor[-2:]
            slope=(q-p)/(b-a)
            line=q+slope*(i-b)
            trendline=(slope>0 and c.low<=line*1.001 and c.close>line) if direction==1 else (slope<0 and c.high>=line*.999 and c.close<line)
            notes['trendline_'+side]=line
        structure_ok=recent and ev[1]==direction
        notes['checks']['SMC Trendline '+side]={'zone':zone,'volume':volume,'rejection':rejection,'recent_structure':bool(structure_ok),'trendline':trendline}
        if zone and volume and rejection and structure_ok and trendline:
            candidates.append(('SMC Trendline',side,'Trendline retest + FVG/OB + recent structure + volume'))
        ema_ok=c.close>notes['ema50'] if direction==1 else c.close<notes['ema50']
        notes['checks']['SMC EMA50 '+side]={'zone':zone,'volume':volume,'rejection':rejection,'recent_choch':bool(structure_ok and ev[2]=='CHoCH'),'ema50':ema_ok}
        if zone and volume and rejection and structure_ok and ev[2]=='CHoCH' and ema_ok:
            candidates.append(('SMC EMA50',side,'EMA50 + FVG/OB retest + recent CHoCH + volume'))
        # Latest confirmed swing impulse, ordered in time, not rolling future extrema.
        if highs and lows:
            hi,hp=highs[-1]; li,lp=lows[-1]
            up=li<hi and hp>lp
            down=hi<li and hp>lp
            lo62=hp-(hp-lp)*settings.fib_deep; hi50=hp-(hp-lp)*settings.fib_shallow
            shortlo=lp+(hp-lp)*settings.fib_shallow; shorthi=lp+(hp-lp)*settings.fib_deep
            notes['fib_long']=(lo62,hi50);notes['fib_short']=(shortlo,shorthi)
            fib=(up and c.low<=hi50 and c.high>=lo62 and c.close>hi50) if direction==1 else (down and c.high>=shortlo and c.low<=shorthi and c.close<shortlo)
            notes['checks']['Fibonacci '+side]={'retracement_rejection':fib,'rejection':rejection,'volume':volume}
            notes['fib_anchors']={'high':hp,'low':lp,'high_index':hi,'low_index':li}
            if fib and rejection and volume:
                candidates.append(('Fibonacci',side,'Confirmed swing 50–61.8% retracement rejection + volume'))
    signals=[]
    for name,side,reason in candidates:
        from .risk import structural_stop,trend_context
        from .instruments import ETF_SYMBOLS
        cost=settings.equity_cost_pct if symbol in ETF_SYMBOLS else settings.cost_pct
        stop=structural_stop(bars,side,c.close,settings) if settings.quality_policy else c.close*(1-settings.stop_pct if side=='long' else 1+settings.stop_pct)
        regime=trend_context(bars,side) if settings.quality_policy else {'accepted':True,'reason':'legacy policy'}
        notes.setdefault('quality_checks',[]).append({'strategy':name,'side':side,'structural_stop':stop,'regime':regime,'minimum_net_R':settings.min_net_rr})
        if stop is None or not regime['accepted']:continue
        target=choose_target(entry=c.close,stop=stop,side=side,blocks=blocks,as_of=c.end,
                             desired_rr=settings.rr,buffer_pct=settings.buffer_pct,roundtrip_cost_pct=cost,min_net_rr=settings.min_net_rr if settings.quality_policy else 0)
        notes.setdefault('target_decisions',[]).append({'strategy':name,'side':side,'entry':c.close,'stop':stop,'unrestricted':target.original_target,'target':target.target,'gross_rr':target.gross_rr,'net_reward_pct':target.net_reward_pct,'reason':target.reason})
        if target.accepted:
            signals.append(Signal(name,side,c.end,c.close,stop,target.target,reason+'; '+target.reason,target.gross_rr))
    return signals, blocks, notes
