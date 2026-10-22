"""Windows desktop observer. Manual journal changes only local SQLite data."""
import math
import os
import queue
import tempfile
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk, messagebox
from dataclasses import asdict
from .engine import Engine, TRACKS
from .market import SYMBOLS
from .store import Store, net_return
from .strategies import Settings
from .metrics import trade_metrics


def report_error(title,message,**kwargs):
    import sys
    if any(flag in sys.argv for flag in ('--self-test','--acceptance-smoke')):
        raise RuntimeError(title+': '+str(message))
    messagebox.showerror(title,message,**kwargs)


def app_path():
    return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'BloFinObserver'/'observer.sqlite3'


def stamp(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%m-%d %H:%M:%S UTC')


class App(tk.Tk):
    def __init__(self,path=None,start=True):
        super().__init__()
        self.title('Alyssa | BloFin Live Observer')
        self.geometry(f'{min(1440,self.winfo_screenwidth()-60)}x{min(900,self.winfo_screenheight()-100)}')
        self.minsize(640,480)
        self.configure(bg='#111827');self.path=path or app_path();self.store=Store(self.path)
        self.events=queue.Queue();self.engine=Engine(self.path,self.events)
        self.market={};self.analysis={};self.models={};self.rows=[];self.received={};self.last_scores=0
        style=ttk.Style(self);style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10),background='#111827',foreground='#e5e7eb')
        style.configure('Treeview',background='#1f2937',fieldbackground='#1f2937',foreground='#e5e7eb',rowheight=27)
        style.configure('Treeview.Heading',background='#374151',foreground='white')
        style.configure('TButton',background='#374151',padding=6)
        style.configure('TEntry',fieldbackground='#fff',foreground='#111827')
        style.configure('TCombobox',fieldbackground='#fff',foreground='#111827')
        # Keep every control reachable at small resolutions and Windows display scaling.
        viewport=ttk.Frame(self);viewport.pack(fill='both',expand=True)
        viewport.rowconfigure(0,weight=1);viewport.columnconfigure(0,weight=1)
        self.viewport=tk.Canvas(viewport,bg='#111827',highlightthickness=0)
        self.viewport.grid(row=0,column=0,sticky='nsew')
        self.page_y=ttk.Scrollbar(viewport,orient='vertical',command=self.viewport.yview)
        self.page_y.grid(row=0,column=1,sticky='ns')
        self.page_x=ttk.Scrollbar(viewport,orient='horizontal',command=self.viewport.xview)
        self.page_x.grid(row=1,column=0,sticky='ew')
        self.viewport.configure(yscrollcommand=self.page_y.set,xscrollcommand=self.page_x.set)
        self.content=ttk.Frame(self.viewport)
        self.content_window=self.viewport.create_window(0,0,window=self.content,anchor='nw')
        self.viewport.bind('<Configure>',self.resize_page)
        self.content.bind('<Configure>',self.page_configured)
        self.bind_all('<MouseWheel>',self.scroll_page,add='+')
        self.bind_all('<Button-4>',self.scroll_page,add='+')
        self.bind_all('<Button-5>',self.scroll_page,add='+')
        ttk.Label(self.content,text='ALYSSA  /  BLOFIN LIVE OBSERVER',font=('Segoe UI',20,'bold')).pack(anchor='w',padx=18,pady=(15,3))
        ttk.Label(self.content,text='USDT PERPETUALS | OBSERVE ONLY | All strategy trades are paper simulations | Manual journal never submits an exchange order',foreground='#6ee7b7').pack(anchor='w',padx=18)
        ttk.Label(self.content,text='SMC rules: explicit configurable interpretation; annotated-example validation outstanding. Model failures block model tracks.',foreground='#fbbf24').pack(anchor='w',padx=18,pady=4)
        header=ttk.Frame(self.content);header.pack(fill='x',padx=18,pady=5)
        self.symbol=tk.StringVar(value=SYMBOLS[0]);box=ttk.Combobox(header,textvariable=self.symbol,values=SYMBOLS,state='readonly',width=14)
        box.pack(side='left');box.bind('<<ComboboxSelected>>',lambda e:(self.render_chart(),self.render_trades(self.rows)))
        self.prices=tk.StringVar(value='Connecting to BloFin public data...')
        ttk.Label(header,textvariable=self.prices,font=('Segoe UI',12,'bold')).pack(side='left',padx=15)
        ttk.Button(header,text='Strategy settings / rules',command=self.settings_dialog).pack(side='right')
        self.chart_visible=True
        self.chart_toggle=ttk.Button(header,text='Hide chart / more journal space',command=self.toggle_chart)
        self.chart_toggle.pack(side='right',padx=6)
        self.chart=tk.Canvas(self.content,bg='#0b1220',height=230,highlightthickness=0);self.chart.pack(fill='x',padx=18,pady=5)
        self.chart.bind('<Configure>',lambda e:self.render_chart())
        self.detail=tk.StringVar(value='Waiting for confirmed candles')
        self.chart_detail=ttk.Label(self.content,textvariable=self.detail)
        self.chart_detail.pack(anchor='w',padx=18)
        self.model_status=tk.StringVar(value='Models: waiting for fresh confirmed candle; packaged CPU inference')
        ttk.Label(self.content,textvariable=self.model_status,wraplength=1380,foreground='#93c5fd').pack(anchor='w',padx=18,pady=4)
        self.notebook=notebook=ttk.Notebook(self.content);notebook.pack(fill='both',expand=True,padx=18,pady=5)
        compare=ttk.Frame(notebook);journal=ttk.Frame(notebook);audit=ttk.Frame(notebook)
        notebook.add(compare,text='Side-by-side performance');notebook.add(journal,text='Trade journal & manual comparison');notebook.add(audit,text='Connection & inference log')
        decisions=ttk.Frame(notebook);notebook.add(decisions,text='Signals & evidence')
        self.decisions=self.table(decisions,('track','state','side','asof','entry','stop','target','R'),(260,200,70,180,90,90,90,80))
        self.evidence=tk.Text(decisions,height=9,bg='#0b1220',fg='#d1d5db',wrap='word')
        self.evidence.pack(fill='x',pady=5)
        forecasts=ttk.Frame(notebook);notebook.add(forecasts,text='Forecast quality')
        self.scores=self.table(forecasts,('model','asof','observed','MAE','MAPE','latency'),(120,200,140,140,140,120))
        ttk.Label(forecasts,text='Out-of-sample errors use only future finalized candle closes. Blank means the forecast horizon has not yet occurred.').pack(anchor='w',pady=6)
        filters=ttk.Frame(compare);filters.pack(fill='x',pady=5)
        ttk.Label(filters,text='Performance window (selected chart symbol)').pack(side='left',padx=5)
        self.window=tk.StringVar(value='All time')
        choice=ttk.Combobox(filters,textvariable=self.window,values=('All time','Last 24 hours','Last 7 days'),state='readonly',width=18)
        choice.pack(side='left');choice.bind('<<ComboboxSelected>>',lambda e:self.render_trades(self.rows))
        self.summary=self.table(compare,('track','closed','open','win','net','unrealized','net_R','expect_R','max_DD'),(260,65,65,70,110,110,85,85,90))
        ttk.Label(compare,text='Returns use equal entry notional per trade; no leverage. Paper costs are configurable; funding excluded. Manual fees entered separately.').pack(anchor='w',padx=8,pady=5)
        self.manual_panel(journal)
        self.trades=self.table(journal,('id','track','symbol','side','time','entry','stop','target','exit','net'),(45,190,100,65,165,95,95,95,95,90))
        self.match=tk.StringVar(value='Select Alyssa’s journal row to compare nearest paper entries within +/-5 minutes for the same symbol.')
        ttk.Label(journal,textvariable=self.match,wraplength=1300).pack(anchor='w',pady=5)
        self.trades.bind('<<TreeviewSelect>>',self.show_match)
        self.log=tk.Text(audit,bg='#0b1220',fg='#d1d5db',height=8,state='disabled');self.log.pack(fill='both',expand=True)
        self.status=tk.StringVar(value='Starting...')
        self.status_label=ttk.Label(self.content,textvariable=self.status,wraplength=1400)
        self.status_label.pack(anchor='w',padx=18,pady=8)
        self.protocol('WM_DELETE_WINDOW',self.shutdown)
        if start:self.engine.start()
        self.after(300,self.drain)

    def page_configured(self,event=None):
        self.resize_page()
        self.viewport.configure(scrollregion=self.viewport.bbox('all'))

    def resize_page(self,event=None):
        # A minimum virtual page preserves the journal rows instead of squeezing them out.
        minimum_height=1000 if getattr(self,'chart_visible',True) else 755
        self.viewport.itemconfigure(self.content_window,
            width=max(1380,self.content.winfo_reqwidth(),self.viewport.winfo_width()),
            height=max(minimum_height,self.content.winfo_reqheight(),self.viewport.winfo_height()))

    def toggle_chart(self):
        self.chart_visible=not self.chart_visible
        if self.chart_visible:
            self.chart.pack(fill='x',padx=18,pady=5,before=self.chart_detail)
        else:self.chart.pack_forget()
        self.chart_toggle.configure(text='Hide chart / more journal space' if self.chart_visible else 'Show chart')
        self.resize_page();self.viewport.yview_moveto(0)

    def scroll_page(self,event):
        # Tables and text retain their own wheel behavior. Elsewhere scroll the whole page.
        if isinstance(event.widget,(ttk.Treeview,tk.Text,ttk.Combobox)):
            return
        units=-1 if getattr(event,'num',None)==4 else 1 if getattr(event,'num',None)==5 else -int(event.delta/120) if abs(event.delta)>=120 else (-1 if event.delta>0 else 1)
        self.viewport.yview_scroll(units*3,'units')
        return 'break'

    def verify_layout(self):
        """Exercise small-window access using actual Tk geometry, without network or orders."""
        import json
        results=[]
        original_scale=float(self.tk.call('tk','scaling'))
        for scale in (1.0,1.5,2.0):
            self.tk.call('tk','scaling',original_scale*scale)
            self.geometry('1024x640');self.update()
            self.notebook.select(1);self.update()
            self.page_configured();self.update()
            assert self.trades.winfo_height()>=200, 'Journal rows were squeezed out'
            assert self.viewport.yview()[1]<1, 'Missing vertical page overflow'
            self.viewport.yview_moveto(1);self.viewport.xview_moveto(1);self.update()
            bottom=self.status_label
            assert bottom.winfo_rooty()+bottom.winfo_height() <= self.viewport.winfo_rooty()+self.viewport.winfo_height()+2, 'Bottom status cannot be reached'
            assert self.viewport.xview()[1]>.999, 'Right edge cannot be reached'
            self.viewport.xview_moveto(0)
            self.toggle_chart();self.update()
            assert not self.chart.winfo_ismapped()
            self.toggle_chart();self.update()
            assert self.chart.winfo_ismapped()
            for tab in range(self.notebook.index('end')):
                self.notebook.select(tab);self.update()
                assert self.notebook.nametowidget(self.notebook.select()).winfo_ismapped()
            results.append({'window':'1024x640','relative_scale':scale,'journal_height':self.trades.winfo_height(),'bottom_reachable':True,'chart_toggle':True})
        self.tk.call('tk','scaling',original_scale)
        self.notebook.select(1);self.geometry('640x480');self.update()
        self.viewport.yview_moveto(1);self.update()
        assert self.trades.winfo_height()>=200
        Path('layout-smoke.json').write_text(json.dumps(results,indent=2))

    def table(self,parent,columns,widths):
        frame=ttk.Frame(parent);frame.pack(fill='both',expand=True)
        frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        tree=ttk.Treeview(frame,columns=columns,show='headings',height=8)
        for c,w in zip(columns,widths):tree.heading(c,text=c.title());tree.column(c,width=w,minwidth=w,stretch=False)
        vertical=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
        horizontal=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
        tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        tree.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns')
        horizontal.grid(row=1,column=0,sticky='ew')
        return tree

    def manual_panel(self,parent):
        form=ttk.Frame(parent);form.pack(fill='x',pady=8)
        self.fields={}
        for label,default in [('Symbol',SYMBOLS[0]),('Side','long'),('Entry',''),('Stop',''),('Target',''),('Size','1'),('Exit',''),('Exit size',''),('Fees %','0')]:
            group=ttk.Frame(form);group.pack(side='left',padx=4)
            ttk.Label(group,text=label).pack(anchor='w')
            var=tk.StringVar(value=default);self.fields[label]=var
            if label in ('Symbol','Side'):
                ttk.Combobox(group,textvariable=var,values=SYMBOLS if label=='Symbol' else ('long','short'),state='readonly',width=12).pack()
            else:ttk.Entry(group,textvariable=var,width=8).pack()
        ttk.Button(form,text='Record my entry now',command=self.manual_open).pack(side='left',padx=6,pady=(18,0))
        ttk.Button(form,text='Record exit / partial',command=self.manual_close).pack(side='left',padx=6,pady=(18,0))
        second=ttk.Frame(parent);second.pack(fill='x',pady=3)
        self.manual_time=tk.StringVar(value='')
        ttk.Label(second,text='UTC fill time (blank = now; YYYY-MM-DD HH:MM:SS)').pack(side='left')
        ttk.Entry(second,textvariable=self.manual_time,width=23).pack(side='left',padx=5)
        ttk.Button(second,text='Prefill current quote',command=self.prefill_quote).pack(side='left',padx=5)
        ttk.Button(second,text='Edit selected entry / notes',command=self.edit_selected).pack(side='left',padx=5)
        ttk.Label(parent,text='Local actual-fill journal. Size in base units. Blank exit size closes remaining. Fee % = total cost for the exited portion.').pack(anchor='w')

    def fill_time(self):
        value=self.manual_time.get().strip()
        when=int(datetime.strptime(value,'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000) if value else int(time.time()*1000)
        if when>int(time.time()*1000)+2000 or when<0:raise ValueError('Fill time must be a past UTC timestamp')
        return when

    def prefill_quote(self):
        symbol=self.fields['Symbol'].get()
        if symbol not in self.market:return
        price=self.market[symbol][-1].close;cfg=Settings(**self.store.setting('strategy',{}))
        side=self.fields['Side'].get();direction=1 if side=='long' else -1
        self.fields['Entry'].set(f'{price:.6f}')
        self.fields['Stop'].set(f'{price*(1-direction*cfg.stop_pct):.6f}')
        self.fields['Target'].set(f'{price*(1+direction*cfg.stop_pct*cfg.rr):.6f}')

    def edit_selected(self):
        selected=self.trades.selection()
        if not selected:return
        row=next(x for x in self.rows if x['id']==int(selected[0]))
        if row['source']!='manual':return
        dialog=tk.Toplevel(self);dialog.title('Edit local actual-fill record')
        fields={}
        for key,value in [('opened',datetime.fromtimestamp(row['opened']/1000,timezone.utc).strftime('%Y-%m-%d %H:%M:%S')),('entry',row['entry']),('stop',row['stop']),('target',row['target']),('notes',row['reason'])]:
            frame=ttk.Frame(dialog);frame.pack(fill='x',padx=12,pady=5)
            ttk.Label(frame,text=key,width=10).pack(side='left');var=tk.StringVar(value=str(value));fields[key]=var
            ttk.Entry(frame,textvariable=var,width=65).pack(side='left')
        def save():
            try:
                opened=int(datetime.strptime(fields['opened'].get(),'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
                if opened>time.time()*1000 or opened<0:raise ValueError('Invalid fill timestamp')
                self.store.edit_manual(row['id'],opened,float(fields['entry'].get()),float(fields['stop'].get()),float(fields['target'].get()),fields['notes'].get())
                self.render_trades(self.store.trades());dialog.destroy()
            except Exception as exc:report_error('Cannot edit',str(exc),parent=dialog)
        ttk.Button(dialog,text='Save with audit history',command=save).pack(pady=8)

    def manual_open(self):
        try:
            f=self.fields
            id=self.store.open_trade('Alyssa manual',f['Symbol'].get(),f['Side'].get(),self.fill_time(),
                float(f['Entry'].get()),float(f['Stop'].get()),float(f['Target'].get()),'User-recorded actual fill','manual',float(f['Size'].get()))
            if id is None:raise ValueError('An open manual trade already exists for this symbol')
            self.render_trades(self.store.trades())
        except Exception as exc:report_error('Cannot record entry',str(exc))

    def manual_close(self):
        try:
            selection=self.trades.selection()
            if not selection:raise ValueError('Select an open manual journal row')
            id=int(selection[0]);row=next(x for x in self.store.trades() if x['id']==id)
            if row['source']!='manual' or row['closed'] is not None:raise ValueError('Select an open Alyssa manual trade')
            self.store.partial_exit(id,float(self.fields['Exit'].get()),self.fill_time(),float(self.fields['Exit size'].get()) if self.fields['Exit size'].get() else row['remaining'],float(self.fields['Fees %'].get())/100)
            self.render_trades(self.store.trades())
        except Exception as exc:report_error('Cannot record exit',str(exc))

    def show_match(self,event=None):
        selected=self.trades.selection()
        if not selected:return
        row=next((x for x in self.rows if x['id']==int(selected[0])),None)
        if not row or row['source']!='manual':return
        matches=self.store.comparison(row['symbol'],row['opened'])
        self.match.set('Same-symbol entries +/-5m: '+('; '.join(f'{k}: {v["side"]}, entry delta {(v["entry"]/row["entry"]-1)*100:+.3f}%, time delta {(v["opened"]-row["opened"])/1000:+.0f}s' for k,v in matches.items()) or 'No matching paper entry.'))

    def settings_dialog(self):
        dialog=tk.Toplevel(self);dialog.title('Strategy rules & parameters');dialog.geometry('740x790')
        text=('Both SMC detectors require a closed-candle rejection, retest of a still-valid FVG or order block, and volume >= prior 20-bar mean × multiplier.\n\n'
              'Trendline: two confirmed ascending pivot lows / descending pivot highs; line retest within 0.1%; BOS or CHoCH within 10 bars.\n\n'
              'EMA50: close on the trend side of EMA50; CHoCH within 10 bars. Pivots require N bars on both sides. OB = last opposite candle in 20 bars before structure break.\n\n'
              'Fibonacci: latest confirmed ordered swing; rejection out of 50-61.8% zone, with volume. Model gates require same-candle six-bar forecast direction.\n\n'
              'TP is capped before the nearest opposing block, even below 2R. Partial touches retain blocks; a wick strictly beyond the far edge invalidates. Models never replace entry detectors.\n\n'
              'These are explicit implementation assumptions, not a claim that annotated examples have been validated. Stop/cost defaults were proposed, not approved. Funding is excluded.')
        ttk.Label(dialog,text=text,wraplength=700).pack(padx=15,pady=15)
        current=asdict(Settings(**self.store.setting('strategy',{})))
        fields={}
        for name,value in current.items():
            row=ttk.Frame(dialog);row.pack(fill='x',padx=15,pady=3)
            ttk.Label(row,text=name+' (fraction for percentages)',width=40).pack(side='left')
            var=tk.StringVar(value=str(value));fields[name]=var;ttk.Entry(row,textvariable=var,width=15).pack(side='left')
        def save():
            try:
                values={k:int(v.get()) if k=='pivot' else float(v.get()) for k,v in fields.items()}
                if not all(math.isfinite(v) for v in values.values()):raise ValueError('Finite values required')
                Settings(**values).validate();self.store.set_setting('strategy',values)
                self.store.event('settings',str(values));dialog.destroy()
            except Exception as exc:report_error('Invalid settings',str(exc),parent=dialog)
        ttk.Button(dialog,text='Save parameters for future paper entries',command=save).pack(pady=10)

    def drain(self):
        for _ in range(300):
            try:kind,p=self.events.get_nowait()
            except queue.Empty:break
            if kind=='market':
                self.market[p['symbol']]=p['bars'];self.received[p['symbol']]=p['received'];self.render_chart()
            elif kind=='analysis':self.analysis[p['symbol']]=p;self.render_chart()
            elif kind=='trades':self.render_trades(p['trades'])
            elif kind=='model':
                self.models[(p['symbol'],p['name'])]=p
                self.append_log(p['symbol']+' '+p['name']+': '+p['status'])
                self.render_chart()
            else:self.status.set(p['message']);self.append_log(p['message'])
        now=time.time()
        self.prices.set('   |   '.join(s.replace('-USDT','')+': '+(f'{self.market[s][-1].close:,.2f}'+(('  LIVE' if not self.market[s][-1].confirmed else '  CLOSED BAR ONLY') if now-self.received.get(s,0)<30 and now*1000-self.market[s][-1].time<600000 else '  STALE') if s in self.market else 'connecting') for s in SYMBOLS))
        self.after(500,self.drain)

    def append_log(self,message):
        self.log.configure(state='normal');self.log.insert('end',stamp(int(time.time()*1000))+'  '+message+'\n')
        if int(self.log.index('end-1c').split('.')[0])>500:self.log.delete('1.0','100.0')
        self.log.see('end');self.log.configure(state='disabled')

    def render_chart(self):
        symbol=self.symbol.get();bars=self.market.get(symbol,[])[-90:];canvas=self.chart;canvas.delete('all')
        if not bars:canvas.create_text(20,30,text='Connecting to live BloFin candles...',fill='white',anchor='w');return
        w=max(canvas.winfo_width(),100);h=max(canvas.winfo_height(),100);left=70;right=w-15
        lo=min(c.low for c in bars);hi=max(c.high for c in bars);span=max(hi-lo,hi*.001);lo-=span*.08;hi+=span*.08
        y=lambda value: h-25-(value-lo)/(hi-lo)*(h-45)
        dx=(right-left)/(len(bars)+8)
        for j in range(5):
            val=lo+(hi-lo)*j/4;yy=y(val);canvas.create_line(left,yy,right,yy,fill='#243044');canvas.create_text(left-5,yy,text=f'{val:,.2f}',fill='#94a3b8',anchor='e')
        for i,c in enumerate(bars):
            x=left+i*dx;color='#34d399' if c.close>=c.open else '#fb7185'
            canvas.create_line(x,y(c.high),x,y(c.low),fill=color)
            canvas.create_rectangle(x-max(1,dx*.3),y(max(c.open,c.close)),x+max(1,dx*.3),y(min(c.open,c.close))+1,fill=color,outline=color)
        analysis=self.analysis.get(symbol,{})
        for b in analysis.get('blocks',[]):
            if b.invalidated_at is None and lo<b.high and hi>b.low:
                canvas.create_rectangle(left,y(b.high),right,y(b.low),outline='#f59e0b',dash=(4,3))
        notes=analysis.get('notes',{})
        full=self.market.get(symbol,[]);offset=max(0,len(full)-len(bars))
        def line_price(value,color,label,dash=(3,3)):
            if lo<=value<=hi:
                yy=y(value);canvas.create_line(left,yy,right,yy,fill=color,dash=dash)
                canvas.create_text(right-4,yy-6,text=label,fill=color,anchor='e')
        if full:
            value=full[0].close;points=[]
            for i,c in enumerate(full):
                if i:value+=2/51*(c.close-value)
                if i>=offset:points.extend([left+(i-offset)*dx,max(5,min(h-5,y(value)))])
            if len(points)>=4:canvas.create_line(*points,fill='#facc15',width=2)
        for side in ('long','short'):
            if 'trendline_'+side in notes:line_price(notes['trendline_'+side],'#c084fc','Trendline '+side)
        for gap in notes.get('gaps',[]):
            if not gap['invalidated'] and gap['low']<hi and gap['high']>lo:
                canvas.create_rectangle(left,max(5,y(gap['high'])),right,min(h-5,y(gap['low'])),outline='#22d3ee',dash=(2,5))
        anchors=notes.get('fib_anchors')
        if anchors:
            high,low=anchors['high'],anchors['low']
            up=anchors['low_index']<anchors['high_index']
            fibcfg=Settings(**self.store.setting('strategy',{}))
            for level in sorted(set((.382,fibcfg.fib_shallow,fibcfg.fib_deep,.786,1.,1.272,fibcfg.fib_extension))):
                value=high-(high-low)*level if up else low+(high-low)*level
                line_price(value,'#64748b',f'Fib {level:g}')
        for key,color in [('pivot_highs','#fb7185'),('pivot_lows','#6ee7b7')]:
            for index,value in notes.get(key,[]):
                if offset<=index<offset+len(bars):
                    xx=left+(index-offset)*dx;yy=y(value)
                    canvas.create_oval(xx-3,yy-3,xx+3,yy+3,fill=color,outline='')
        for trade in self.rows:
            if trade['symbol']==symbol and bars[0].time<=trade['opened']<=bars[-1].end:
                x=left+next((i for i,c in enumerate(bars) if c.time<=trade['opened']<c.end),len(bars)-1)*dx
                yy=max(5,min(h-5,y(trade['entry'])))
                canvas.create_polygon(x,yy-6,x-5,yy+4,x+5,yy+4,fill='#fff' if trade['source']=='manual' else '#fb923c')
        for index in (0,len(bars)//2,len(bars)-1):
            canvas.create_text(left+index*dx,h-10,text=datetime.fromtimestamp(bars[index].time/1000,timezone.utc).strftime('%H:%M'),fill='#94a3b8')
        for name,color in [('Kronos','#a78bfa'),('TimesFM','#38bdf8')]:
            p=self.models.get((symbol,name),{});forecast=p.get('forecast')
            if forecast and forecast['asof']==next((c.end for c in reversed(bars) if c.confirmed),None):
                pts=[left+(len(bars)-1)*dx,y(bars[-1].close)]
                for j,val in enumerate(forecast['values']):pts.extend([left+(len(bars)+j)*dx,max(10,min(h-10,y(val)))])
                canvas.create_line(*pts,fill=color,width=2)
        notes=analysis.get('notes',{});signals=analysis.get('signals',[])
        self.detail.set(symbol+' | 5m | '+stamp(bars[-1].time)+' | '+('forming' if not bars[-1].confirmed else 'confirmed')+' | '+str(notes.get('structure',''))+' | '+(', '.join(s.strategy+' '+s.side for s in signals) or 'No current entry'))
        labels=[]
        for name in ('Kronos','TimesFM'):
            p=self.models.get((symbol,name),{});f=p.get('forecast')
            labels.append(name+': '+(f'{f["checkpoint"]} | {stamp(f["asof"])} | 30m | {f.get("latency_s",0):.2f}s | final {f["values"][-1]:.3f}' if f else p.get('status','waiting')))
        self.model_status.set(' | '.join(labels))
        self.render_decisions(symbol)
        if time.time()-self.last_scores>10:
            self.last_scores=time.time()
            for item in self.scores.get_children():self.scores.delete(item)
            for score in self.store.forecast_scores(symbol):
                self.scores.insert('','end',values=(score['model'],stamp(score['asof']),str(score['observed'])+'/'+str(score['horizon']),f'{score["mae"]:.5f}' if score['mae'] is not None else '-',f'{score["mape"]*100:.3f}%' if score['mape'] is not None else '-',f'{score["latency_s"]:.2f}s' if score['latency_s'] is not None else '-'))

    def render_decisions(self,symbol):
        import json
        analysis=self.analysis.get(symbol,{})
        signals=analysis.get('signals',[]);notes=analysis.get('notes',{})
        for item in self.decisions.get_children():self.decisions.delete(item)
        for track in TRACKS:
            base='SMC Trendline' if track.startswith('SMC Trendline') else 'SMC EMA50' if track.startswith('SMC EMA50') else 'Fibonacci'
            signal=next((s for s in signals if s.strategy==base),None)
            opened=next((t for t in self.rows if t['track']==track and t['symbol']==symbol and t['closed'] is None),None)
            latest=next((t for t in self.rows if t['track']==track and t['symbol']==symbol),None)
            state='OPEN PAPER' if opened else 'NO SIGNAL'
            if signal and not opened:
                state='CONFIRMED / EXPIRED' if time.time()*1000-signal.time>90000 else 'CONFIRMED'
                names=('Kronos','TimesFM') if 'both' in track else ('Kronos',) if 'Kronos' in track else ('TimesFM',) if 'TimesFM' in track else ()
                from .models import agrees
                if names and not all(agrees(self.models.get((symbol,n),{}).get('forecast'),signal.side,signal.entry,signal.time) for n in names):
                    state='WAIT / MODEL DISAGREES'
            if not signal and latest and latest['closed'] is not None:state='CLOSED / NO NEW SIGNAL'
            row=opened
            self.decisions.insert('','end',values=(track,state,row['side'] if row else signal.side if signal else '-',stamp(row['opened']) if row else stamp(signal.time) if signal else '-',f'{row["entry"]:.4f}' if row else f'{signal.entry:.4f}' if signal else '-',f'{row["stop"]:.4f}' if row else f'{signal.stop:.4f}' if signal else '-',f'{row["target"]:.4f}' if row else f'{signal.target:.4f}' if signal else '-',f'{abs(row["target"]-row["entry"])/abs(row["entry"]-row["stop"]):.2f}' if row else f'{signal.rr:.2f}' if signal else '-'))
        text=json.dumps({'checks':notes.get('checks',{}),'target_decisions':notes.get('target_decisions',[]),'note':'All entries here are paper only. False checks explain NO SIGNAL.'},indent=2)
        if getattr(self,'evidence_text',None)!=text:
            self.evidence_text=text;self.evidence.delete('1.0','end');self.evidence.insert('1.0',text)

    def render_trades(self,rows):
        self.rows=rows;selected=self.trades.selection()
        for item in self.trades.get_children():self.trades.delete(item)
        for row in rows[:500]:
            exit=row['exit'];price=(exit if row['closed'] is not None else None) or (self.market[row['symbol']][-1].close if row['symbol'] in self.market else row['entry'])
            self.trades.insert('','end',iid=str(row['id']),values=(row['id'],row['track'],row['symbol'],row['side'],stamp(row['opened']),f'{row["entry"]:.3f}',f'{row["stop"]:.3f}',f'{row["target"]:.3f}',f'{exit:.3f}' if exit else 'OPEN',f'{net_return(row,price)*100:+.3f}%'))
        if selected and self.trades.exists(selected[0]):self.trades.selection_set(selected)
        for item in self.summary.get_children():self.summary.delete(item)
        for track in ('Alyssa manual',)+TRACKS:
            days={'All time':None,'Last 24 hours':1,'Last 7 days':7}[self.window.get()]
            since=0 if days is None else time.time()*1000-days*86400000
            entries=[x for x in rows if x['track']==track and x['symbol']==self.symbol.get() and x['opened']>=since]
            metrics=trade_metrics(entries,{s:bars[-1].close for s,bars in self.market.items()})
            self.summary.insert('','end',values=(track,metrics['closed'],metrics['open'],f'{metrics["wins"]/metrics["closed"]*100:.1f}%' if metrics['closed'] else '-',f'{metrics["net"]*100:+.3f}%',f'{metrics["unrealized"]*100:+.3f}%',f'{metrics["net_r"]:+.2f}',f'{metrics["expectancy_r"]:+.2f}' if metrics['expectancy_r'] is not None else '-',f'{metrics["max_drawdown"]*100:.3f}%'))


    def shutdown(self):
        self.engine.shutdown();self.store.close();self.destroy()


def main():
    import sys
    if '--self-test' in sys.argv:
        with tempfile.TemporaryDirectory() as directory:
            app=App(Path(directory)/'test.db',start=False)
            app.update()
            app.verify_layout()
            app.fields['Entry'].set('100');app.fields['Stop'].set('99');app.fields['Target'].set('102');app.fields['Size'].set('2')
            app.manual_open();assert len(app.store.trades())==1
            row=app.store.trades()[0];app.trades.selection_set(str(row['id']))
            app.fields['Exit'].set('101');app.fields['Exit size'].set('1');app.manual_close()
            assert app.store.trades()[0]['remaining']==1
            app.fields['Exit size'].set('1');app.manual_close()
            assert app.store.trades()[0]['closed'] is not None
            app.shutdown()
            reopened=Store(Path(directory)/'test.db');assert len(reopened.trades())==1;reopened.close()
        return
    if '--acceptance-smoke' in sys.argv:
        from .smoke import desktop_smoke
        desktop_smoke();return
    if '--network-smoke' in sys.argv:
        from .network_probe import run
        run();return
    if '--model-smoke' in sys.argv:
        from .smoke import model_smoke
        model_smoke();return
    if '--live-smoke' in sys.argv:
        from .smoke import live_smoke
        live_smoke();return
    App().mainloop()
