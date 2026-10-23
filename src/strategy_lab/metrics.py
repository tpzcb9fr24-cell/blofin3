"""Per-track normalized analytics; never aggregate correlated tracks."""
from .store import net_return


def trade_metrics(trades,quotes):
    closed=sorted((t for t in trades if t['closed'] is not None),key=lambda t:t['closed'])
    returns=[net_return(t,t['exit']) for t in closed]
    equity=peak=drawdown=0.
    for r in returns:
        equity+=r;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
    rs=[r/(abs(t['entry']-t['stop'])/t['entry']+(t.get('cost_pct',0) if t.get('policy')=='quality-v2' else 0)) for r,t in zip(returns,closed)]
    gross_rs=[(t['realized'] if 'realized' in t else (1 if t['side']=='long' else -1)*(t['exit']/t['entry']-1))/(abs(t['entry']-t['stop'])/t['entry']) for t in closed]
    opened=[t for t in trades if t['closed'] is None]
    unrealized=sum(net_return(t,quotes[t['symbol']]) for t in opened if t['symbol'] in quotes)
    return {'unpriced_open':sum(t['symbol'] not in quotes for t in opened),'closed':len(closed),'open':len(opened),'wins':sum(r>0 for r in returns),
            'average_dollars_per_100':100*sum(returns)/len(returns) if returns else None,'profit_factor':sum(r for r in returns if r>0)/-sum(r for r in returns if r<0) if any(r<0 for r in returns) else None,'net':sum(returns),'unrealized':unrealized,'max_drawdown':drawdown,
            'expectancy_r':sum(rs)/len(rs) if rs else None,'net_r':sum(rs),'gross_r':sum(gross_rs),
            'exposure_base':sum(t.get('remaining',t.get('quantity',1)) for t in opened)}


def forecast_score(forecast,bars):
    """Only compare finalized future bars. Forecast i targets asof + i intervals open."""
    lookup={c.time:c.close for c in bars if c.confirmed}
    errors=[]
    for i,predicted in enumerate(forecast['values']):
        actual=lookup.get(forecast.get('target_times',[forecast['asof']+j*300000 for j in range(len(forecast['values']))])[i])
        if actual is not None:errors.append((predicted-actual,abs(predicted/actual-1)))
    return {'observed':len(errors),'horizon':len(forecast['values']),
            'mae':sum(abs(x[0]) for x in errors)/len(errors) if errors else None,
            'mape':sum(x[1] for x in errors)/len(errors) if errors else None}
