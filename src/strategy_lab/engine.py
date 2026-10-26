"""Observer worker, reconnect recovery, causal paper ledger, model isolation."""
import json
import queue
import threading
import time
from pathlib import Path
from dataclasses import asdict
from .market import SYMBOLS,CRYPTO_SYMBOLS,ETF_SYMBOLS, Candle, history, public_get, parse_candle, contiguous, quote
from .strategies import Settings, detect
from .store import Store
from .models import Models, agrees
from .transport import public_socket,transport_name,MarketHTTPError

BASE_TRACKS=tuple(name+suffix for name in ('SMC Trendline','SMC EMA50') for suffix in ('',' + Kronos',' + TimesFM',' + both'))+('Fibonacci','Fibonacci + SMC + both')
from .direction_flip import flip_plan,SUFFIX
TRACKS=tuple(t for base in BASE_TRACKS for t in (base,base+SUFFIX))

class Engine:
    def __init__(self,path,events):
        self.path=Path(path);self.events=events;self.stop=threading.Event();self.inbox=queue.Queue()
        self.model_jobs={name:queue.Queue(maxsize=10) for name in ('Kronos','TimesFM')};self.model_results=queue.Queue();self.model_pending=set()
        self.bars={s:{} for s in SYMBOLS};self.last={};self.forecasts={};self.pending={}
        self.last_received={};self.quotes={};self.zones={};self.threads=[];self.active_socket=None;self.streaming=False;self.blocked_until={}
        self.audit_events=queue.Queue();self.quote_retry={};self.stock_next={};self.feed_status={};self.key_path=self.path.parent/'market-data.key'

    def start(self):
        for target in (self.run,self.stream,lambda:self.infer('Kronos'),lambda:self.infer('TimesFM')):
            thread=threading.Thread(target=target,daemon=True);thread.start();self.threads.append(thread)

    def emit(self,kind,**payload):
        self.events.put((kind,payload))
        if kind in ('error','risk','transport','feed'):
            self.audit_events.put((kind,payload.get('message','')[:1000]))

    def flush_events(self,store):
        for _ in range(300):
            try:kind,message=self.audit_events.get_nowait()
            except queue.Empty:break
            store.event(kind,message)


    def stream(self):
        import websocket
        while not self.stop.is_set():
            try:
                ws=public_socket(timeout=12);self.active_socket=ws;self.streaming=True
                ws.send(json.dumps({'op':'subscribe','args':[{'channel':'candle5m','instId':s} for s in CRYPTO_SYMBOLS]}))
                self.emit('transport',message='Live public WebSocket connected | '+transport_name())
                last_ping=time.monotonic()
                while not self.stop.is_set():
                    try:raw=ws.recv()
                    except (websocket.WebSocketTimeoutException,TimeoutError):
                        ws.send('ping');continue
                    if not raw: raise ConnectionError('WebSocket closed')
                    if raw=='pong': continue
                    msg=json.loads(raw)
                    if msg.get('event')=='error': raise RuntimeError(str(msg))
                    symbol=msg.get('arg',{}).get('instId')
                    if symbol in CRYPTO_SYMBOLS:
                        valid=[]
                        for row in msg.get('data',[]):
                            try:valid.append(parse_candle(row))
                            except ValueError as exc:
                                self.emit('error',message='Rejected malformed BloFin candle: '+str(exc))
                        if valid:self.inbox.put((symbol,valid))
                    if time.monotonic()-last_ping>20:
                        ws.send('ping');last_ping=time.monotonic()
                ws.close()
            except Exception as exc:
                self.streaming=False
                if self.active_socket:
                    try:self.active_socket.close()
                    except Exception:pass
                    self.active_socket=None
                if not self.stop.is_set():
                    self.emit('transport',message='Public WebSocket unavailable; live REST fallback | '+str(exc)[:450])
                self.stop.wait(60 if getattr(exc,'status',None)==403 else 10)

    def shutdown(self):
        self.stop.set()
        if self.active_socket:
            try:self.active_socket.close()
            except Exception:pass

    def infer(self,worker_name):
        models=Models()
        while not self.stop.is_set():
            try:symbol,name,bars=self.model_jobs[worker_name].get(timeout=1)
            except queue.Empty:continue
            try:
                value=models.predict(name,bars,symbol=symbol)
                self.model_results.put((symbol,name,bars[-1].end,value,None))
            except Exception as exc:
                self.model_results.put((symbol,name,bars[-1].end,None,str(exc)))

    def update(self,store,symbol,new,bootstrap=False):
        bars=self.bars[symbol]
        now=int(time.time()*1000)
        for c in new:
            # Do not regress a finalized bar with an out-of-order partial update.
            if c.time in bars and bars[c.time].confirmed and not c.confirmed: continue
            if c.end>now+2000 and c.confirmed: continue
            bars[c.time]=c
        store.save_bars(symbol,list(bars.values())[-512:])
        ordered=sorted(bars.values(),key=lambda c:c.time)[-512:]
        self.bars[symbol]={c.time:c for c in ordered}
        if not ordered: return
        self.last_received[symbol]=time.time()
        latest=ordered[-1]
        self.emit('market',symbol=symbol,bars=ordered,price=latest.close,received=time.time())
        closed=[c for c in ordered if c.confirmed]
        if not closed:return
        previous=self.last.get(symbol)
        if previous is None:
            self.last[symbol]=closed[-1].end
            previous=closed[-1].end
        # Recover paper exits for bars missed while disconnected/restarting.
        for c in closed:
            if c.end>previous:self.paper_exits(store,symbol,c)
        self.paper_exits(store,symbol,ordered[-1])
        self.last[symbol]=max(previous,closed[-1].end)
        _,detected,_=detect(closed,self.settings,symbol=symbol)
        self.zones[symbol]=store.sync_zones(symbol,detected,ordered,now)
        signals,blocks,notes=detect(closed,self.settings,self.zones[symbol],symbol=symbol)
        store.save_decision(symbol,closed[-1].end,{'signals':[asdict(s) for s in signals],'blocks':[asdict(b) for b in blocks],'notes':notes,'settings':asdict(self.settings)})
        self.emit('analysis',symbol=symbol,signals=signals,blocks=blocks,notes=notes)
        # Never backfill historical strategy entries, or enter stale recovered signals.
        fresh=0<=now-closed[-1].end<90_000 and contiguous(closed,symbol)
        if not contiguous(closed,symbol) or now-closed[-1].end>600000:return
        asof=closed[-1].end
        key=(symbol,asof)
        if key not in self.pending:
            self.pending[key]={'signals':signals,'entered':set(),'created':time.time()}
            for name in ('Kronos','TimesFM'):
                jobkey=(symbol,name,asof)
                if jobkey not in self.model_pending:
                    self.model_pending.add(jobkey)
                    try:self.model_jobs[name].put_nowait((symbol,name,closed))
                    except queue.Full:
                        self.model_pending.discard(jobkey)
                        self.emit('model',symbol=symbol,name=name,status='Busy; this candle not inferred',forecast=None)
                        continue
                    self.emit('model',symbol=symbol,name=name,status='Queued real CPU inference',forecast=None)
        self.entries(store,symbol,asof)

    def entries(self,store,symbol,asof):
        pending=self.pending.get((symbol,asof))
        if not pending:return
        if time.time()*1000-asof>90_000:
            for row in store.db.execute("SELECT track,state FROM entry_attempts WHERE symbol=? AND asof=? AND state IN ('WAITING_QUOTE','WAITING_MODEL')",(symbol,asof)).fetchall():
                store.entry_attempt(symbol,asof,row['track'],'EXPIRED','90-second entry window ended while '+row['state'].lower())
            return
        from .instruments import market_open
        if symbol in ETF_SYMBOLS and not market_open(symbol,int(time.time()*1000)):return
        signals=pending['signals']; smc=[s for s in signals if s.strategy.startswith('SMC')]
        for s in signals:
            tracks=[s.strategy]
            if s.strategy.startswith('SMC'):
                tracks += [s.strategy+' + Kronos',s.strategy+' + TimesFM',s.strategy+' + both']
            elif any(x.side==s.side for x in smc):
                tracks.append('Fibonacci + SMC + both')
            for track in tracks:
                if track in pending['entered']:continue
                names=('Kronos','TimesFM') if 'both' in track else ('Kronos',) if 'Kronos' in track else ('TimesFM',) if 'TimesFM' in track else ()
                if not all(agrees(self.forecasts.get((symbol,name)),s.side,s.entry,asof) for name in names):
                    previous=store.db.execute('SELECT state FROM entry_attempts WHERE symbol=? AND asof=? AND track=?',(symbol,asof,track)).fetchone()
                    if not previous or previous['state']!='WAITING_MODEL':
                        store.entry_attempt(symbol,asof,track,'WAITING_MODEL','Waiting for same-candle model agreement')
                    continue
                if time.time()<self.quote_retry.get(symbol,0):continue
                # Fill at the latest observed price, not retrospectively at model-input close.
                try:
                    live_quote=self.quotes.get(symbol)
                    refresh=not live_quote or (time.time()*1000-live_quote.get('received_ms',0)>30000 if symbol in ETF_SYMBOLS else time.time()*1000-live_quote['time']>1000)
                    if refresh:
                        if symbol in ETF_SYMBOLS:
                            from .stocks import load_key,quote as stock_quote
                            live_quote=stock_quote(symbol,load_key(self.key_path))
                        else:live_quote=quote(symbol)
                        live_quote['received_ms']=int(time.time()*1000)
                        self.quotes[symbol]=live_quote
                    if not 0<=time.time()*1000-live_quote['time']<(90000 if symbol in ETF_SYMBOLS else 15000):
                        raise ValueError('Stale bid/ask')
                except Exception as exc:
                    self.quotes.pop(symbol,None)
                    self.emit('error',message='Paper entry skipped: no fresh bid/ask: '+str(exc))
                    delay=60 if getattr(exc,'status',None)==403 else 5
                    self.quote_retry[symbol]=time.time()+delay
                    store.entry_attempt(symbol,asof,track,'WAITING_QUOTE','Fresh price unavailable; retry only within original 90-second window',{'error':str(exc)[:450],'retry_seconds':delay,'http_status':getattr(exc,'status',None)})
                    continue
                if time.time()*1000-asof>90_000:
                    store.entry_attempt(symbol,asof,track,'EXPIRED','Quote request finished after the 90-second entry window')
                    pending['entered'].add(track);continue
                # Cross displayed spread; residual slippage is included in cost_pct.
                price=live_quote['price'] if symbol in ETF_SYMBOLS else live_quote['ask'] if s.side=='long' else live_quote['bid']
                names=('Kronos','TimesFM') if 'both' in track else ('Kronos',) if 'Kronos' in track else ('TimesFM',) if 'TimesFM' in track else ()
                if not all(agrees(self.forecasts.get((symbol,name)),s.side,price,asof) for name in names):
                    store.entry_attempt(symbol,asof,track,'REJECTED_MODEL','Model direction no longer agrees at observed fill',{'price':price})
                    self.emit('risk',message=track+' '+symbol+': model direction no longer agrees at observed fill')
                    pending['entered'].add(track);continue
                cfg=self.settings
                from .targets import choose_target
                closed=[c for c in sorted(self.bars[symbol].values(),key=lambda c:c.time) if c.confirmed]
                _,blocks,_=detect(closed,cfg,self.zones.get(symbol,()),symbol=symbol)
                # Invalidate using the current incomplete candle's wick as well.
                current=max(self.bars[symbol].values(),key=lambda c:c.time)
                from .targets import OrderBlock
                blocks=[OrderBlock(b.low,b.high,b.kind,b.formed_at,
                           current.time if (b.kind=='bullish' and current.low<b.low) or (b.kind=='bearish' and current.high>b.high) else b.invalidated_at) for b in blocks]
                from .risk import structural_stop,size_entry,POLICY
                stop=structural_stop(closed,s.side,price,cfg) if cfg.quality_policy else price*(1-cfg.stop_pct if s.side=='long' else 1+cfg.stop_pct)
                if stop is None:
                    store.entry_attempt(symbol,asof,track,'REJECTED_STOP','No valid structure stop within maximum distance',{'price':price})
                    self.emit('risk',message=track+' '+symbol+': no valid structure stop within maximum distance')
                    pending['entered'].add(track);continue
                cost=cfg.equity_cost_pct if symbol in ETF_SYMBOLS else cfg.cost_pct
                decision=choose_target(entry=price,stop=stop,side=s.side,blocks=blocks,as_of=int(time.time()*1000),desired_rr=cfg.rr,buffer_pct=cfg.buffer_pct,roundtrip_cost_pct=cost,min_net_rr=cfg.min_net_rr if cfg.quality_policy else 0)
                if decision.accepted:
                    quantity,note=size_entry(store.trades(),track,symbol,s.side,price,stop,cost,int(time.time()*1000),cfg) if cfg.quality_policy else (1,'legacy size')
                    if quantity is None:
                        store.entry_attempt(symbol,asof,track,'REJECTED_RISK',note,{'price':price,'stop':stop})
                        self.emit('risk',message=track+' '+symbol+': skipped: '+note)
                        pending['entered'].add(track);continue
                    trade_id=store.open_trade(track,symbol,s.side,int(time.time()*1000),price,stop,decision.target,
                                     s.reason+'; '+note+'; indicative fill '+json.dumps(live_quote)+'; TP evidence '+json.dumps(asdict(decision))+'; model gating as-of '+str(asof),cost_pct=cost,quantity=quantity,policy=POLICY if cfg.quality_policy else 'legacy-v1',setup_key=f'{symbol}:{asof}:{s.side}')
                    if trade_id:
                        try:self.open_flip(store,trade_id,live_quote,asof)
                        except Exception as exc:
                            store.entry_attempt(symbol,asof,track+SUFFIX,'FLIP_ERROR',str(exc)[:450],{'original_trade_id':trade_id})
                            self.emit('error',message='Paired flip unavailable: '+str(exc)[:450])
                    store.entry_attempt(symbol,asof,track,'OPENED' if trade_id else 'EXISTING_POSITION', 'Paper trade recorded' if trade_id else 'Existing position or duplicate entry',{'trade_id':trade_id,'price':price,'stop':stop,'target':decision.target,'quantity':quantity})
                else:
                    store.entry_attempt(symbol,asof,track,'REJECTED_TARGET',decision.reason,{'price':price,'stop':stop,'target_decision':asdict(decision)})
                pending['entered'].add(track)

    def open_flip(self,store,original_id,live_quote,asof):
        original=dict(store.db.execute('SELECT * FROM trades WHERE id=?',(original_id,)).fetchone())
        track=original['track']+SUFFIX
        # Same observed quote and entry decision. Cross the opposite side of its spread.
        price=live_quote['price'] if original['symbol'] in ETF_SYMBOLS else live_quote['bid'] if original['side']=='long' else live_quote['ask']
        plan=flip_plan(original['side'],original['entry'],original['stop'],original['target'],price)
        trade_id=store.open_trade(track,original['symbol'],plan['side'],original['opened'],plan['entry'],plan['stop'],plan['target'],
                     'DIRECTION-ONLY FLIP of original trade '+str(original_id)+'; same quantity, stop/target percentage distances and costs. No new model/OB gating. Original setup '+original['setup_key'],
                     quantity=original['quantity'],cost_pct=original['cost_pct'],policy=original['policy'],setup_key=original['setup_key'])
        store.entry_attempt(original['symbol'],asof,track,'OPENED' if trade_id else 'EXISTING_POSITION',
                            'Direction-only flipped paper trade' if trade_id else 'Previous flipped position still open; no stacked position',
                            {'original_trade_id':original_id,'trade_id':trade_id,'plan':plan,'quantity':original['quantity'],'cost_pct':original['cost_pct']})

    def paper_exits(self,store,symbol,c):
        for trade in store.trades():
            if trade['symbol']!=symbol or trade['closed'] is not None or trade['source']!='paper' or c.end<=trade['opened']:continue
            long=trade['side']=='long'
            # Full-bar extremes before an intrabar entry cannot be used to close it.
            intrabar=trade['opened']>c.time
            lo=c.close if intrabar else c.low
            hi=c.close if intrabar else c.high
            opening=c.close if intrabar else c.open
            stop=lo<=trade['stop'] if long else hi>=trade['stop']
            target=hi>=trade['target'] if long else lo<=trade['target']
            if stop or target:
                price=(min(opening,trade['stop']) if long else max(opening,trade['stop'])) if stop else trade['target']
                store.close_trade(trade['id'],price,c.end if c.confirmed else int(time.time()*1000),'PAPER STOP (stop-first)' if stop else 'PAPER TARGET',trade.get('cost_pct',self.settings.cost_pct))

    def run(self):
        store=Store(self.path)
        self.settings=Settings(**store.setting('strategy',{})).validate()
        # Reconcile open positions from the stored candle immediately after entry.
        for trade in store.trades():
            if trade['source']=='paper' and trade['closed'] is None:
                self.last[trade['symbol']]=min(self.last.get(trade['symbol'],trade['opened']),trade['opened'])
        next_poll=0
        while not self.stop.is_set():
            try:
                if time.monotonic()>=next_poll:
                    self.settings=Settings(**store.setting('strategy',{})).validate()
                    for symbol in CRYPTO_SYMBOLS:
                        if time.time()<self.blocked_until.get(symbol,0):continue
                        try:
                            new=history(symbol) if not self.bars[symbol] else public_get(symbol,100)
                            self.update(store,symbol,new,not bool(self.bars[symbol]))
                        except Exception as exc:
                            if getattr(exc,'status',None)==403:self.blocked_until[symbol]=time.time()+60
                            self.emit('error',message=symbol+': '+str(exc)[:450])
                    next_poll=time.monotonic()+(15 if self.streaming else 3)
                from .stocks import load_key,history as stock_history,next_poll as stock_next_poll
                for symbol in ETF_SYMBOLS:
                    if time.time()<self.stock_next.get(symbol,0):continue
                    try:
                        key=load_key(self.key_path)
                        if not key:raise ValueError('ETF DATA SETUP REQUIRED: Twelve Data market-data key')
                        new=stock_history(symbol,key,512)
                        self.update(store,symbol,new,not bool(self.bars[symbol]))
                        self.stock_next[symbol]=stock_next_poll(int(time.time()*1000))/1000
                        self.feed_status[symbol]='Twelve Data 5m regular-session; indicative pricing'
                    except Exception as exc:
                        message=str(exc)
                        if self.feed_status.get(symbol)!=message:self.emit('feed',symbol=symbol,message=symbol+': '+message)
                        self.feed_status[symbol]=message;self.stock_next[symbol]=time.time()+60
                for _ in range(100):
                    try:symbol,bars=self.inbox.get_nowait()
                    except queue.Empty:break
                    self.update(store,symbol,bars)
                for _ in range(10):
                    try:symbol,name,asof,value,error=self.model_results.get_nowait()
                    except queue.Empty:break
                    self.model_pending.discard((symbol,name,asof))
                    if value:
                        self.forecasts[(symbol,name)]=value;store.save_forecast(symbol,name,asof,value)
                        self.emit('model',symbol=symbol,name=name,status='Real inference completed',forecast=value)
                        self.entries(store,symbol,asof)
                    else:
                        store.event('model_error',symbol+' '+name+': '+error)
                        self.emit('model',symbol=symbol,name=name,status='UNAVAILABLE: '+error,forecast=None)
                for symbol,asof in list(self.pending):self.entries(store,symbol,asof)
                self.flush_events(store)
                self.pending={k:v for k,v in self.pending.items() if time.time()-v['created']<300}
                self.emit('trades',trades=store.trades())
            except Exception as exc:
                store.event('worker_error',str(exc));self.emit('error',message=str(exc))
            self.stop.wait(.5)
        self.flush_events(store)
        store.close()
