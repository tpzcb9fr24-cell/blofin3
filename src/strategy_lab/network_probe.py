"""Genuine public REST + WebSocket test using the shipped transport."""
import json
import sys
import time
from pathlib import Path
from .market import SYMBOLS,history,contiguous,parse_candle,quote
from .transport import public_socket,transport_name


def run():
    result={'transport':transport_name(),'platform':sys.platform,'history':{},'websocket_updates':{s:0 for s in SYMBOLS}}
    started=time.monotonic()
    for symbol in SYMBOLS:
        bars=history(symbol);closed=[c for c in bars if c.confirmed]
        assert len(closed)>=60 and contiguous(closed),symbol+' invalid history'
        assert 0<=time.time()*1000-closed[-1].end<600000,symbol+' stale history'
        ticker=quote(symbol)
        result['history'][symbol]={'bars':len(bars),'last_confirmed':closed[-1].end,'bid':ticker['bid'],'ask':ticker['ask']}
    socket=public_socket(timeout=12)
    try:
        socket.send(json.dumps({'op':'subscribe','args':[{'channel':'candle5m','instId':s} for s in SYMBOLS]}))
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            raw=socket.recv()
            if raw=='pong':continue
            if not raw:raise ConnectionError('Public stream closed')
            msg=json.loads(raw)
            if msg.get('event')=='error':raise RuntimeError(str(msg))
            symbol=msg.get('arg',{}).get('instId')
            if symbol in SYMBOLS:
                for row in msg.get('data',[]):
                    try:parse_candle(row)
                    except ValueError:continue
                    result['websocket_updates'][symbol]+=1
            if all(v>=2 for v in result['websocket_updates'].values()):break
        assert all(v>=2 for v in result['websocket_updates'].values()),'Missing real public stream updates: '+str(result)
    finally:socket.close()
    result['elapsed_s']=time.monotonic()-started
    Path('network-smoke.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    return result

if __name__=='__main__':run()
