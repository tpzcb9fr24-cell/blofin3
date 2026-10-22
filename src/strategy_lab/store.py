"""Local durable journal; each thread owns its SQLite connection."""
import json
import math
import sqlite3
import time
from pathlib import Path
from .market import SYMBOLS

SCHEMA='''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS candles(symbol TEXT,time INTEGER,payload TEXT,PRIMARY KEY(symbol,time));
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY,track TEXT,symbol TEXT,side TEXT,opened INTEGER,
 entry REAL,stop REAL,target REAL,closed INTEGER,exit REAL,reason TEXT,fees REAL DEFAULT 0,
 source TEXT, UNIQUE(track,symbol,opened));
CREATE TABLE IF NOT EXISTS forecasts(symbol TEXT,model TEXT,asof INTEGER,created INTEGER,payload TEXT,
 PRIMARY KEY(symbol,model,asof));
CREATE TABLE IF NOT EXISTS decisions(symbol TEXT,asof INTEGER,payload TEXT,PRIMARY KEY(symbol,asof));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,payload TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,time INTEGER,kind TEXT,message TEXT);
'''

class Store:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path),timeout=15)
        self.db.row_factory=sqlite3.Row
        self.db.executescript(SCHEMA)
        columns={row['name'] for row in self.db.execute('PRAGMA table_info(trades)')}
        for name,definition in [('quantity','REAL DEFAULT 1'),('remaining','REAL DEFAULT 1'),('realized','REAL DEFAULT 0'),('cost_pct','REAL DEFAULT 0.0015')]:
            if name not in columns:
                self.db.execute('ALTER TABLE trades ADD COLUMN '+name+' '+definition)
        self.db.execute('CREATE TABLE IF NOT EXISTS manual_exits(id INTEGER PRIMARY KEY,trade_id INTEGER,time INTEGER,price REAL,quantity REAL,fee_fraction REAL)')
        self.db.commit()

    def close(self): self.db.close()

    def save_bars(self,symbol,bars):
        with self.db:
            self.db.executemany('INSERT OR REPLACE INTO candles VALUES(?,?,?)',
                                [(symbol,c.time,json.dumps(c.dict())) for c in bars])

    def event(self,kind,message):
        with self.db:
            self.db.execute('INSERT INTO events(time,kind,message) VALUES(?,?,?)',(int(time.time()*1000),kind,message))

    def setting(self,key,default=None):
        row=self.db.execute('SELECT payload FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self,key,value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value)))

    def open_trade(self,track,symbol,side,opened,entry,stop,target,reason,source='paper',quantity=1,cost_pct=.0015):
        if not math.isfinite(cost_pct) or not 0<=cost_pct<1:
            raise ValueError('Invalid entry cost estimate')
        if not math.isfinite(quantity) or quantity<=0:
            raise ValueError('Positive finite size required')
        if symbol not in SYMBOLS or side not in ('long','short') or not all(math.isfinite(x) and x>0 for x in (entry,stop,target)):
            raise ValueError('Invalid trade prices, instrument or side')
        if not (stop<entry<target if side=='long' else target<entry<stop):
            raise ValueError('Stop/target must bracket the entry')
        if self.db.execute('SELECT 1 FROM trades WHERE track=? AND symbol=? AND closed IS NULL',(track,symbol)).fetchone():
            return None
        with self.db:
            cur=self.db.execute('INSERT OR IGNORE INTO trades(track,symbol,side,opened,entry,stop,target,reason,source,quantity,remaining,cost_pct) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                                (track,symbol,side,opened,entry,stop,target,reason,source,quantity,quantity,cost_pct))
        return cur.lastrowid if cur.rowcount else None

    def close_trade(self,id,price,closed,reason,fees=0):
        if not math.isfinite(price) or price<=0 or not math.isfinite(fees) or fees<0:
            raise ValueError('Invalid exit or fees')
        row=self.db.execute('SELECT opened FROM trades WHERE id=? AND closed IS NULL',(id,)).fetchone()
        if not row or closed<row['opened']:
            raise ValueError('Invalid exit time or already closed')
        with self.db:
            self.db.execute('UPDATE trades SET exit=?,closed=?,reason=reason||?,fees=? WHERE id=? AND closed IS NULL',
                            (price,closed,' | '+reason,fees,id))
            self.db.execute("UPDATE trades SET remaining=0,realized=(CASE WHEN side='long' THEN 1 ELSE -1 END)*(?/entry-1) WHERE id=?",(price,id))

    def partial_exit(self,id,price,closed,quantity,fee_fraction=0):
        row=self.db.execute('SELECT * FROM trades WHERE id=?',(id,)).fetchone()
        if not row or row['source']!='manual' or row['closed'] is not None:
            raise ValueError('An open manual trade is required')
        if not all(math.isfinite(x) for x in (price,quantity,fee_fraction)) or price<=0 or quantity<=0 or quantity>row['remaining']+1e-9 or fee_fraction<0 or closed<row['opened']:
            raise ValueError('Invalid partial exit, size, fee or timestamp')
        fraction=quantity/row['quantity'];remaining=max(0,row['remaining']-quantity)
        realized=row['realized']+(1 if row['side']=='long' else -1)*(price/row['entry']-1)*fraction
        fees=row['fees']+fee_fraction*fraction
        with self.db:
            self.db.execute('INSERT INTO manual_exits(trade_id,time,price,quantity,fee_fraction) VALUES(?,?,?,?,?)',(id,closed,price,quantity,fee_fraction))
            average=self.db.execute('SELECT sum(price*quantity)/sum(quantity) FROM manual_exits WHERE trade_id=?',(id,)).fetchone()[0]
            self.db.execute('UPDATE trades SET remaining=?,realized=?,fees=?,exit=?,closed=? WHERE id=?',
                            (remaining,realized,fees,average,closed if remaining<1e-9 else None,id))
            self.db.execute('INSERT INTO events(time,kind,message) VALUES(?,?,?)',(closed,'manual_exit',json.dumps({'trade_id':id,'quantity':quantity,'price':price,'fees':fee_fraction})))

    def edit_manual(self,id,opened,entry,stop,target,notes):
        row=self.db.execute('SELECT * FROM trades WHERE id=?',(id,)).fetchone()
        if not row or row['source']!='manual' or row['closed'] is not None or row['remaining']!=row['quantity']:
            raise ValueError('Only an open manual trade without exits can be edited')
        if not all(math.isfinite(x) and x>0 for x in (entry,stop,target)) or not (stop<entry<target if row['side']=='long' else target<entry<stop):
            raise ValueError('Invalid entry, stop or target')
        with self.db:
            self.db.execute('UPDATE trades SET opened=?,entry=?,stop=?,target=?,reason=? WHERE id=?',(opened,entry,stop,target,notes,id))
            self.db.execute('INSERT INTO events(time,kind,message) VALUES(?,?,?)',(int(time.time()*1000),'manual_edit',json.dumps({'before':dict(row),'after':{'opened':opened,'entry':entry,'stop':stop,'target':target,'notes':notes}})))

    def trades(self):
        return [dict(x) for x in self.db.execute('SELECT * FROM trades ORDER BY opened DESC,id DESC')]

    def save_decision(self,symbol,asof,payload):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO decisions VALUES(?,?,?)',(symbol,asof,json.dumps(payload)))

    def save_forecast(self,symbol,model,asof,payload):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO forecasts VALUES(?,?,?,?,?)',
                            (symbol,model,asof,int(time.time()*1000),json.dumps(payload)))

    def forecast_scores(self,symbol,since=0):
        from .market import Candle
        from .metrics import forecast_score
        bars=[Candle(**json.loads(x[0])) for x in self.db.execute('SELECT payload FROM candles WHERE symbol=? ORDER BY time',(symbol,))]
        results=[]
        for row in self.db.execute('SELECT * FROM forecasts WHERE symbol=? AND asof>=? ORDER BY asof DESC LIMIT 500',(symbol,since)):
            f=json.loads(row['payload']);score=forecast_score(f,bars)
            results.append({'model':row['model'],'asof':row['asof'],'checkpoint':f['checkpoint'],'latency_s':f.get('latency_s'),**score})
        return results

    def sync_zones(self,symbol,detected,bars,observed_ms):
        from .targets import OrderBlock
        self.db.execute('CREATE TABLE IF NOT EXISTS zones(symbol TEXT,id TEXT,low REAL,high REAL,kind TEXT,formed INTEGER,invalidated INTEGER,mitigated INTEGER,PRIMARY KEY(symbol,id))')
        with self.db:
            for block in detected:
                self.db.execute('INSERT OR IGNORE INTO zones VALUES(?,?,?,?,?,?,?,NULL)',
                                (symbol,_zone_id(block),block.low,block.high,block.kind,block.formed_at,block.invalidated_at))
                if block.invalidated_at is not None:
                    self.db.execute('UPDATE zones SET invalidated=CASE WHEN invalidated IS NULL THEN ? ELSE min(invalidated,?) END WHERE symbol=? AND id=?',
                                    (block.invalidated_at,block.invalidated_at,symbol,_zone_id(block)))
            for row in self.db.execute('SELECT * FROM zones WHERE symbol=? AND invalidated IS NULL',(symbol,)).fetchall():
                invalidated=mitigated=None
                for c in bars:
                    timestamp=c.end if c.confirmed else observed_ms
                    if timestamp<=row['formed']:continue
                    if (row['kind']=='bullish' and c.low<row['low']) or (row['kind']=='bearish' and c.high>row['high']):
                        invalidated=timestamp;break
                    if c.low<=row['high'] and c.high>=row['low']:mitigated=timestamp
                self.db.execute('UPDATE zones SET invalidated=?,mitigated=coalesce(?,mitigated) WHERE symbol=? AND id=?',
                                (invalidated,mitigated,symbol,row['id']))
        return [OrderBlock(r['low'],r['high'],r['kind'],r['formed'],r['invalidated']) for r in self.db.execute('SELECT * FROM zones WHERE symbol=?',(symbol,))]

    def comparison(self,symbol,opened):
        """Nearest observed entry per track within one five-minute interval."""
        rows=[dict(x) for x in self.db.execute('SELECT * FROM trades WHERE symbol=? AND source=? AND abs(opened-?)<=300000 ORDER BY abs(opened-?)',
                                              (symbol,'paper',opened,opened))]
        result={}
        for row in rows:
            result.setdefault(row['track'],row)
        return result


def net_return(trade,price):
    direction=1 if trade['side']=='long' else -1
    if 'remaining' in trade:
        return trade['realized'] + direction*(price/trade['entry']-1)*trade['remaining']/trade['quantity']-trade['fees']
    return direction*(price/trade['entry']-1)-trade['fees']


# Zone identity includes recognition time and full wick range; partial touches
# never delete a zone. Registry survives rolling context and app restarts.
def _zone_id(block):
    return f'{block.formed_at}:{block.kind}:{block.low:.12g}:{block.high:.12g}'
