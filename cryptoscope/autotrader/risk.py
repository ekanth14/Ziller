"""Persistent entry limits in the same transaction as simulated fills."""
import time
from cryptoscope.agents.schemas import number
from cryptoscope.execution.paper_broker import PaperBroker


class AutoBroker(PaperBroker):
    def __init__(self,path,risk,settings):
        super().__init__(path,risk)
        self.settings=settings
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS auto_risk (
                    id INTEGER PRIMARY KEY CHECK(id=1), day TEXT, day_start REAL,
                    peak REAL, halt_reason TEXT, entries INTEGER, last_entry REAL);
                CREATE TABLE IF NOT EXISTS auto_marks (symbol TEXT PRIMARY KEY, bid REAL, stamp REAL);
            ''')
            db.execute('INSERT OR IGNORE INTO auto_risk VALUES (1,?,?,?,?,0,0)',
                       (time.strftime('%Y-%m-%d',time.gmtime()),risk['initial_cash'],risk['initial_cash'],''))

    def _equity(self,db,now):
        portfolio=self._portfolio(db)
        equity=portfolio['cash']
        for symbol,position in portfolio['positions'].items():
            mark=db.execute('SELECT bid,stamp FROM auto_marks WHERE symbol=?',(symbol,)).fetchone()
            if not mark or not 0<=now-mark[1]<=self.config['max_quote_age_seconds']:
                return None
            equity+=position['quantity']*mark[0]*(1-self.config['slippage_fraction'])*(1-self.config['fee_fraction'])
        return equity

    def _update(self,db,now):
        equity=self._equity(db,now)
        day,start,peak,halt,entries,last=db.execute('SELECT day,day_start,peak,halt_reason,entries,last_entry FROM auto_risk WHERE id=1').fetchone()
        current_day=time.strftime('%Y-%m-%d',time.gmtime(now))
        if equity is not None:
            if day!=current_day:
                day,start,entries=current_day,equity,0
            peak=max(peak,equity)
            if not halt and equity<=start*(1-self.settings['daily_loss_fraction']):
                halt='DAILY_LOSS_LIMIT'
            if not halt and equity<=peak*(1-self.settings['drawdown_fraction']):
                halt='DRAWDOWN_LIMIT'
            db.execute('UPDATE auto_risk SET day=?,day_start=?,peak=?,halt_reason=?,entries=? WHERE id=1',
                       (day,start,peak,halt,entries))
        return {'equity':equity,'day':day,'day_start_equity':start,'peak_equity':peak,
                'halt_reason':halt,'entries_today':entries,'last_entry_at':last}

    def observe(self,quotes,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for quote in quotes:
                bid=number(quote.get('bid'),'bid',.00000001)
                ask=number(quote.get('ask'),'ask',.00000001)
                stamp=number(quote.get('available_at'),'quote timestamp',1)
                if quote.get('symbol') not in self.config['symbols'] or ask<bid or not 0<=now-stamp<=self.config['max_quote_age_seconds']:
                    raise ValueError('Invalid or stale autonomous quote')
                db.execute('INSERT OR REPLACE INTO auto_marks VALUES (?,?,?)',(quote['symbol'],bid,stamp))
            return self._update(db,now)

    def _entry_reasons(self,db,portfolio,quote,now):
        state=self._update(db,now)
        reasons=[]
        if state['equity'] is None:
            reasons.append('FRESH_PORTFOLIO_MARKS_REQUIRED')
        if state['halt_reason']:
            reasons.append(state['halt_reason'])
        if state['entries_today']>=self.settings['max_entries_per_day']:
            reasons.append('DAILY_ENTRY_LIMIT')
        if state['last_entry_at'] and now-state['last_entry_at']<self.settings['cooldown_seconds']:
            reasons.append('ENTRY_COOLDOWN')
        try:
            bid=number(quote.get('bid'),'bid',.00000001)
            ask=number(quote.get('ask'),'ask',.00000001)
            if ask<bid or (ask-bid)/bid>self.settings['max_spread_fraction']:
                reasons.append('SPREAD_LIMIT')
        except (ValueError,AttributeError,TypeError):
            reasons.append('INVALID_QUOTE')
        return reasons

    def _after_fill(self,db,fill):
        if fill['action']=='LONG':
            db.execute('UPDATE auto_risk SET entries=entries+1,last_entry=? WHERE id=1',(fill['at'],))
        else:
            db.execute('UPDATE auto_risk SET last_entry=? WHERE id=1',(fill['at'],))

    def entry_status(self,quote,now=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            reasons=self._entry_reasons(db,self._portfolio(db),quote,time.time() if now is None else now)
            if db.execute('SELECT halted FROM controls WHERE id=1').fetchone()[0]:
                reasons.append('MANUAL_ENTRY_HALT')
            return reasons

    def risk_status(self,now=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._update(db,time.time() if now is None else now)

    def reset_risk(self,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            equity=self._equity(db,now)
            if equity is None:
                raise ValueError('Refresh all open-position quotes before resetting risk')
            db.execute('UPDATE auto_risk SET day=?,day_start=?,peak=?,halt_reason=? WHERE id=1',
                       (time.strftime('%Y-%m-%d',time.gmtime(now)),equity,equity,''))
        return self.risk_status(now)

    def trail(self,quote,atr):
        now=time.time()
        if not 0<=now-quote['available_at']<=self.config['max_quote_age_seconds']:
            return
        distance=max(number(atr,'ATR')*self.settings['trailing_atr_multiple'],
                     quote['bid']*self.settings['minimum_stop_fraction'])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            position=self._portfolio(db)['positions'].get(quote['symbol'])
            if position and quote['bid']>position['entry']+distance:
                stop=min(quote['bid']-distance,position['target']*.999999)
                if stop>position['stop']:
                    db.execute('UPDATE positions SET stop=? WHERE symbol=?',(stop,quote['symbol']))
