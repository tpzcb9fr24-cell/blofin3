"""Real network acceptance probe: all instruments, websocket, closed-bar advance."""
import json
import time
import websocket
from pathlib import Path
from strategy_lab.market import SYMBOLS,history,parse_candle,contiguous

results={'started_ms':int(time.time()*1000),'symbols':{},'websocket':{},'closed_advance':False}
for symbol in SYMBOLS:
    bars=history(symbol)
    assert contiguous(bars)
    results['symbols'][symbol]={'history_count':len(bars),'initial_confirmed':max(c.end for c in bars if c.confirmed)}
ws=websocket.create_connection('wss://openapi.blofin.com/ws/public',timeout=20)
ws.send(json.dumps({'op':'subscribe','args':[{'channel':'candle5m','instId':s} for s in SYMBOLS]}))
started=time.monotonic();deadline=started+360;last_ping=started
while time.monotonic()<deadline:
    try:raw=ws.recv()
    except websocket.WebSocketTimeoutException:
        ws.send('ping');continue
    if raw=='pong':continue
    msg=json.loads(raw)
    if msg.get('event')=='error':raise RuntimeError(str(msg))
    symbol=msg.get('arg',{}).get('instId')
    if symbol in SYMBOLS:
        for row in msg.get('data',[]):
            c=parse_candle(row)
            item=results['websocket'].setdefault(symbol,{'updates':0,'first_price':c.close})
            item['updates']+=1;item['last_price']=c.close;item['last_open']=c.time
            if c.confirmed and c.end>results['symbols'][symbol]['initial_confirmed']:
                item['new_closed_end']=c.end
    if time.monotonic()-last_ping>20:ws.send('ping');last_ping=time.monotonic()
    if len(results['websocket'])==3 and all('new_closed_end' in x for x in results['websocket'].values()):
        results['closed_advance']=True;break
ws.close()
# Explicit reconnect and backfill reconciliation.
ws=websocket.create_connection('wss://openapi.blofin.com/ws/public',timeout=20)
ws.send(json.dumps({'op':'subscribe','args':[{'channel':'candle5m','instId':'BTC-USDT'}]}));ws.close()
for symbol in SYMBOLS:
    fresh=history(symbol);assert contiguous(fresh)
    results['symbols'][symbol]['reconnected_confirmed']=max(c.end for c in fresh if c.confirmed)
results['duration_s']=time.monotonic()-started
Path('live-stream-evidence.json').write_text(json.dumps(results,indent=2))
assert results['closed_advance'], 'No newly closed bar seen within six minutes'
print(json.dumps(results))
