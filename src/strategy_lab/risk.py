"""Experimental quality-v2 admission and unlevered paper-account risk budgets."""
import math
from .instruments import ETF_SYMBOLS
from .store import net_return

POLICY='quality-v2'

def atr(bars,n=14):
    sample=bars[-n:]
    if len(bars)<n+1:return None
    previous=bars[-n-1].close;values=[]
    for c in sample:values.append(max(c.high-c.low,abs(c.high-previous),abs(c.low-previous)));previous=c.close
    return sum(values)/n

def structural_stop(bars,side,entry,cfg):
    from .strategies import pivots
    a=atr(bars)
    if not a or a<=0:return None
    highs,lows=pivots(bars,cfg.pivot)
    anchors=lows if side=='long' else highs
    anchors=[p for _,p in anchors if p<entry] if side=='long' else [p for _,p in anchors if p>entry]
    if not anchors:return None
    stop=min(anchors[-1],bars[-1].low)-cfg.atr_buffer*a if side=='long' else max(anchors[-1],bars[-1].high)+cfg.atr_buffer*a
    distance=abs(entry-stop)/entry
    if stop<=0 or distance>cfg.stop_pct or distance<=0:return None
    return stop

def trend_context(bars,side):
    from .strategies import ema
    groups={}
    for c in bars:
        if c.confirmed:groups.setdefault(c.time//900000,[]).append(c)
    # Exact completed quarters only. An incomplete quarter never enters the regime filter.
    quarters=[v for _,v in sorted(groups.items()) if len(v)==3 and all(b.time-a.time==300000 for a,b in zip(v,v[1:]))]
    from .market import Candle
    q=[Candle(v[0].time,v[0].open,max(c.high for c in v),min(c.low for c in v),v[-1].close,sum(c.volume for c in v),sum(c.amount for c in v)) for v in quarters]
    if len(q)<23:return {'accepted':False,'reason':'need 23 complete 15-minute bars'}
    current=ema(q,20);prior=ema(q[:-3],20)
    accepted=q[-1].close>current>prior if side=='long' else q[-1].close<current<prior
    return {'accepted':accepted,'reason':'15-minute EMA20 direction and slope','close':q[-1].close,'ema20':current,'earlier_ema20':prior}

def account(trades,track,quotes,cfg):
    rows=[t for t in trades if t['source']=='paper' and t['track']==track and t.get('policy','legacy-v1')==POLICY]
    closed=sorted((t for t in rows if t['closed'] is not None),key=lambda t:(t['closed'],t['id']))
    pnl=[net_return(t,t['exit'])*t['entry']*t['quantity'] for t in closed]
    equity=peak=cfg.initial_equity;drawdown=0
    for value in pnl:
        equity+=value;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
    loss=-sum(v for v in pnl if v<0)
    profit_factor=sum(v for v in pnl if v>0)/loss if loss else None
    opened=[t for t in rows if t['closed'] is None]
    unrealized=sum(net_return(t,quotes.get(t['symbol'],t['entry']))*t['entry']*t['quantity'] for t in opened)
    return {'closed_drawdown_cash':drawdown,'dollar_profit_factor':profit_factor,'unpriced_open':sum(t['symbol'] not in quotes for t in opened),'equity':equity,'marked_equity':equity+unrealized,'opened':opened,'rows':rows}

def size_entry(trades,track,symbol,side,entry,stop,cost,now,cfg):
    a=account(trades,track,{},cfg);equity=a['equity'];opened=a['opened']
    if any(t['symbol']==symbol for t in opened):return None,'one position per symbol per strategy account'
    # Positions using the old policy continue to close normally, but block opposite new exposure.
    if any(t['source']=='paper' and t['track']==track and t['symbol']==symbol and t['closed'] is None for t in trades):return None,'existing position in this strategy account'
    day=now//86400000*86400000
    today=sum(net_return(t,t['exit'])*t['entry']*t['quantity'] for t in a['rows'] if t['closed'] is not None and t['closed']>=day)
    if equity<=0 or today<=-cfg.initial_equity*cfg.daily_loss_fraction:return None,'UTC-day realized loss limit'
    group=lambda s:'US equity beta' if s in ETF_SYMBOLS else 'crypto beta'
    risk=lambda t:(abs(t['entry']-t['stop'])+t['entry']*t['cost_pct'])*t['remaining']
    total=sum(risk(t) for t in opened);correlated=sum(risk(t) for t in opened if group(t['symbol'])==group(symbol))
    budget=min(equity*cfg.risk_fraction,equity*cfg.max_open_risk-total,equity*cfg.group_open_risk-correlated)
    free=max(0,equity-sum(t['entry']*t['remaining'] for t in opened))
    if budget<=1e-8 or free<=0:return None,'account or correlated-group exposure budget'
    unit_risk=abs(entry-stop)+entry*cost
    qty=min(budget/unit_risk,free/(entry*(1+cost)))
    if not math.isfinite(qty) or qty<=0:return None,'no unlevered buying power'
    return qty,'quality-v2: risk-budgeted; equity and crypto are separate correlated groups; no leverage'
