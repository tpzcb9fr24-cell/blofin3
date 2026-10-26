"""Readable local decision audit. Historical missing execution reasons stay unknown."""
import collections
import json
import time
from datetime import datetime,timezone

def stamp(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%m-%d %H:%M:%S UTC')

def decision_history(store,now=None,hours=12):
    now=int(time.time()*1000) if now is None else now
    start=now-int(hours*3600000)
    lines=[f'DECISION HISTORY: {stamp(start)} to {stamp(now)}',
           'Paper simulations only. Counts are strategy candidates, not independent investment opportunities.',
           'No qualifying setup is different from a qualified signal rejected at entry.', '']
    rows=list(store.db.execute('SELECT symbol,asof,payload FROM decisions WHERE asof>? AND asof<=? ORDER BY asof',(start,now)))
    for symbol in sorted({r['symbol'] for r in rows}):
        selected=[r for r in rows if r['symbol']==symbol];base=trend=stop=target=signals=0
        failures=collections.Counter()
        for r in selected:
            d=json.loads(r['payload']);n=d.get('notes',{})
            for name,checks in n.get('checks',{}).items():
                base+=int(bool(checks) and all(checks.values()))
                failures.update(name+': '+k for k,v in checks.items() if not v)
            for q in n.get('quality_checks',[]):
                if q.get('structural_stop') is None:stop+=1
                elif not q.get('regime',{}).get('accepted'):trend+=1
            target+=sum(t.get('target') is None for t in n.get('target_decisions',[]))
            signals+=len(d.get('signals',[]))
        lines += [f'{symbol}: {len(selected)} saved candle decisions; latest {stamp(selected[-1]["asof"])}',
                  f'  Base candidates {base}; stop rejected {stop}; trend rejected {trend}; target rejected {target}; accepted signals {signals}',
                  '  Frequent failed base checks (overlap): '+('; '.join(f'{k} ({v})' for k,v in failures.most_common(4)) or 'none recorded')]
    attempts=list(store.db.execute('SELECT * FROM entry_attempts WHERE asof>? AND asof<=? ORDER BY last_time DESC',(start,now)))
    lines += ['',f'ENTRY OUTCOMES: {len(attempts)} signal/track records']
    for a in attempts[:150]:
        lines += [f'{stamp(a["asof"])} | {a["symbol"]} | {a["track"]} | {a["state"]}',
                  f'  {a["reason"]}; recorded attempts/transitions {a["attempts"]}; last {stamp(a["last_time"])}',
                  '  '+a['details']]
    unknown=[]
    for r in rows:
        d=json.loads(r['payload'])
        for sig in d.get('signals',[]):
            if not store.db.execute('SELECT 1 FROM entry_attempts WHERE symbol=? AND asof=? AND track IN (?,?)',(r['symbol'],r['asof'],sig['strategy'],sig['strategy']+' [FLIP]')).fetchone():
                unknown.append(f'{stamp(r["asof"])} {r["symbol"]} {sig["strategy"]}')
    lines += ['',f'Signals without saved entry outcome: {len(unknown)}. Older versions did not save these reasons; cause UNKNOWN.']+unknown[:100]
    events=list(store.db.execute('SELECT * FROM events WHERE time>? AND time<=? ORDER BY time DESC LIMIT 40',(start,now)))
    lines += ['',f'LATEST SAVED EVENTS ({len(events)}, maximum 40 shown)']
    lines += [f'{stamp(e["time"])} | {e["kind"]} | {e["message"]}' for e in events]
    lines += ['','No saved errors does not prove no errors occurred in an older app version. No historical fills are created by this report.']
    return '\n'.join(lines)
