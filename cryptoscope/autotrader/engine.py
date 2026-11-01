"""One inference worker; the main loop continues protective quote checks."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading
import time
from cryptoscope.autotrader.risk import AutoBroker
from cryptoscope.autotrader.signals import analyze,context,proposal
from cryptoscope.autotrader.store import BotStore,ProcessLock
from cryptoscope.providers.binance import BinanceProvider
from cryptoscope.providers.contracts import role_schema,validate_schema
from cryptoscope.providers.laya import LayaProvider
from cryptoscope.research.settings import ROOT


class AutoTrader:
    def __init__(self,settings,risk,inference,directory=None,reports=None,feed=None,provider_factory=None):
        self.settings,self.risk,self.inference=settings,risk,inference
        self.directory=Path(directory) if directory else ROOT/'work/autotrader'
        self.reports=Path(reports) if reports else ROOT/'reports/autotrader'
        self.store=BotStore(self.directory)
        self.broker=AutoBroker(self.directory/'paper.sqlite3',risk,settings)
        self.feed=feed or BinanceProvider()
        self.provider_factory=provider_factory or (lambda:LayaProvider(inference))
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='laya-paper')
        self.pending=None
        self.quotes={}
        self.analyses={}
        self.next_snapshot=0
        self.cursor=0
        self.finished_count=0
        self.last_decision=None
        self.started_at=time.time()
        self.started_monotonic=time.monotonic()
        self.feed_errors={}
        self.stopping=False
        self.closed=False
        self.decision_limit=None

    def _archive(self,body):
        body['finished_at']=time.time()
        self.store.save(body)
        output=self.reports/body['run_id']
        output.mkdir(parents=True,exist_ok=True)
        temporary=output/'report.json.tmp'
        temporary.write_text(json.dumps(body,indent=2,allow_nan=False),encoding='utf-8')
        temporary.replace(output/'report.json')
        self.finished_count+=1
        self.last_decision={k:body.get(k) for k in ('run_id','symbol','decision','execution','error','status','latency_seconds')}

    def quote_tick(self):
        for symbol in self.settings['symbols']:
            try:
                quote=self.feed.quote(symbol)
                self.broker.observe([quote])
                self.quotes[symbol]=quote
                self.feed_errors.pop(symbol,None)
                result=self.broker.mark(quote)
                if result['status']=='filled':
                    self.store.event('protective_exit',result)
                analysis=self.analyses.get(symbol)
                if analysis:
                    self.broker.trail(quote,analysis['indicators']['atr14'])
            except Exception as error:
                message=f'{type(error).__name__}: {error}'
                if self.feed_errors.get(symbol)!=message:
                    self.store.event('quote_error',{'symbol':symbol,'error':message})
                self.feed_errors[symbol]=message

    def _fresh_quote(self,symbol):
        quote=self.quotes.get(symbol)
        if quote is None or not 0<=time.time()-quote['available_at']<=self.risk['max_quote_age_seconds']:
            raise ValueError('A fresh quote is required')
        return quote

    def start_review(self,snapshot,force_review=False):
        if self.pending:
            return False
        age=time.time()-snapshot.as_of
        if not 0<=age<=self.risk['max_snapshot_age_seconds']:
            raise ValueError(f'Closed-candle snapshot age {age:.3f}s is outside the permitted range')
        analysis=analyze(snapshot)
        self.analyses[snapshot.symbol]=analysis
        quote=self._fresh_quote(snapshot.symbol)
        portfolio=self.broker.portfolio()
        prompt=context(snapshot,analysis,portfolio,quote)
        entry_blocks=self.broker.entry_status(quote)
        if not portfolio['positions'] and entry_blocks:
            prompt.update(allowed_actions=['HOLD'],allowed_strategies=['none'],entry_blocks=entry_blocks)
        body=self.store.claim(f"{snapshot.symbol}:{snapshot.candles[-1]['close_time']}",
            {'kind':'autotrader_decision','mode':'paper','symbol':snapshot.symbol,
             'snapshot':snapshot.to_dict(),'analysis':analysis,'context':prompt,'initial_portfolio':portfolio,
             'initial_quote':quote,'settings':self.settings,'model':self.inference['model']})
        if body is None:
            return False
        if prompt['allowed_actions']==['HOLD'] and not force_review:
            body.update(status='completed',decision={'action':'HOLD','strategy':'none',
                'reason':', '.join(entry_blocks) if entry_blocks else 'No eligible entry signal'},
                decision_source='deterministic_prefilter',execution={'status':'no_order'},latency_seconds=0,model_calls=[])
            self._archive(body)
            return True
        provider=self.provider_factory()
        body['model']=provider.model
        self.pending={'body':body,'snapshot':snapshot,'analysis':analysis,'provider':provider,
            'future':self.executor.submit(provider.complete,'fast_decider',prompt),
            'monotonic_start':time.monotonic()}
        return True

    def finish_review(self):
        pending=self.pending
        if not pending or not pending['future'].done():
            return
        self.pending=None
        body=pending['body']
        elapsed=time.monotonic()-pending['monotonic_start']
        body['latency_seconds']=elapsed
        try:
            decision=pending['future'].result()
            validate_schema(decision,role_schema('fast_decider',body['context']))
            body.update(decision=decision,decision_source='laya_fast_decider')
            if self.stopping or self.store.stopping():
                body['execution']={'status':'discarded_on_stop'}
            elif elapsed>self.settings['decision_max_age_seconds']:
                body['execution']={'status':'discarded_late_decision'}
            elif self.broker.portfolio()!=body['initial_portfolio']:
                body['execution']={'status':'discarded_portfolio_changed'}
            else:
                trade=proposal(decision,pending['snapshot'],pending['analysis'],body['initial_quote'],self.settings,self.risk)
                body['proposal']=trade.to_dict() if trade else None
                if trade:
                    body['execution']=self.broker.execute(body['run_id'],trade,pending['snapshot'],self._fresh_quote(body['symbol']))
                    if body['execution']['status']=='filled':
                        self.store.event('laya_fill',body['execution'])
                else:
                    body['execution']={'status':'no_order'}
            body['status']='completed'
        except Exception as error:
            body.update(status='failed',error=f'{type(error).__name__}: {error}',execution={'status':'no_order_on_error'})
        body['model_calls']=pending['provider'].calls
        self._archive(body)

    def heartbeat(self,state='running'):
        risk=self.broker.risk_status()
        self.store.runtime({'state':state,'mode':'paper','pid':os.getpid(),'started_at':self.started_at,
            'heartbeat_at':time.time(),'model':self.pending['provider'].model if self.pending else self.inference['model'],
            'symbols':self.settings['symbols'],'interval':self.settings['interval'],
            'portfolio':self.broker.portfolio(),'risk':risk,'controls':self.broker.controls(),
            'quotes':self.quotes,'feed_errors':self.feed_errors,'last_decision':self.last_decision,
            'pending_symbol':self.pending['body']['symbol'] if self.pending else None,
            'pending_seconds':round(time.monotonic()-self.pending['monotonic_start'],2) if self.pending else None,
            'quote_poll_seconds':self.settings['quote_poll_seconds'],'decisions_this_session':self.finished_count,
            'settings':self.settings})

    def step(self,force_review=False):
        self.quote_tick()
        self.finish_review()
        self.stopping=self.store.stopping()
        under_limit=self.decision_limit is None or self.finished_count<self.decision_limit
        if not self.stopping and under_limit and not self.pending and time.monotonic()>=self.next_snapshot:
            symbols=self.settings['symbols']
            held=self.broker.portfolio()['positions']
            symbol=next(iter(held)) if held else symbols[self.cursor%len(symbols)]
            self.cursor+=1
            try:
                snapshot=self.feed.snapshot(symbol,self.settings['interval'])
                self.start_review(snapshot,force_review)
            except Exception as error:
                self.store.event('snapshot_error',{'symbol':symbol,'error':f'{type(error).__name__}: {error}'})
            self.next_snapshot=time.monotonic()+self.settings['snapshot_poll_seconds']
        self.heartbeat('stopping' if self.stopping else 'running')

    def close(self):
        if self.closed:
            return
        self.stopping=True
        self.heartbeat('stopping')
        # The socket has a bounded timeout. Discard any late output before
        # releasing the OS account lock and allowing another process to start.
        self.executor.shutdown(wait=True,cancel_futures=True)
        self.finish_review()
        self.heartbeat('stopped')
        self.closed=True

    def run(self,max_decisions=None,force_review=False,max_seconds=None):
        self.decision_limit=max_decisions
        with ProcessLock(self.directory/'engine.lock'):
            self.store.abandon_inflight()
            self.store.request_stop(False)
            self.store.event('started',{'pid':os.getpid(),'mode':'paper'})
            try:
                while True:
                    self.step(force_review)
                    if self.stopping or max_decisions is not None and self.finished_count>=max_decisions:
                        break
                    if max_seconds is not None and time.monotonic()-self.started_monotonic>=max_seconds:
                        break
                    time.sleep(self.settings['quote_poll_seconds'])
            except KeyboardInterrupt:
                self.store.request_stop()
            finally:
                self.close()
