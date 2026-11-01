from concurrent.futures import wait
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from cryptoscope.agents.schemas import Snapshot
from cryptoscope.autotrader.engine import AutoTrader
from cryptoscope.autotrader.risk import AutoBroker
from cryptoscope.autotrader.settings import load_settings
from cryptoscope.autotrader.signals import analyze,context,proposal
from cryptoscope.autotrader.store import BotStore,ProcessLock
from cryptoscope.dashboard.data import DashboardData
from cryptoscope.providers.laya import LayaProvider


def sample(now=None,symbol='BTCUSDT'):
    now=time.time() if now is None else now
    end=int(now//300)*300
    bars=[]
    for i in range(200):
        price=100+i*.025+(.15 if i%2 else 0)
        bars.append({'open_time':end-(200-i)*300,'close_time':end-(199-i)*300,
            'open':price-.02,'close':price,'high':price+.2,'low':price-.2,'volume':100,'taker_buy_volume':55})
    return Snapshot.parse({'symbol':symbol,'as_of':now,'interval_seconds':300,'candles':bars,
                           'derivatives':{},'news':[],'source':'synthetic_autotrader_test'})


class Feed:
    def __init__(self,snapshot):
        self.data=snapshot
        self.bid=snapshot.candles[-1]['close']*.9999

    def quote(self,symbol):
        return {'symbol':symbol,'bid':self.bid,'ask':self.bid*1.0002,'available_at':time.time(),'source':'test'}

    def snapshot(self,symbol,interval):
        return self.data


class Provider:
    model='TEST_FIXTURE_NOT_LAYA'
    def __init__(self,action='BUY',event=None):
        self.action,self.event=action,event
        self.calls=[]

    def complete(self,role,data):
        if self.event:
            self.event.wait(5)
        result={'action':self.action,'strategy':'ema_trend' if self.action=='BUY' else 'position_exit' if self.action=='SELL' else 'none'}
        self.calls.append({'role':role,'response':result,'status':'completed'})
        return result


class AutoTraderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.settings,self.risk,self.inference=load_settings()
        self.settings['symbols']=['BTCUSDT']
        self.risk['symbols']=['BTCUSDT']
        self.snapshot=sample()
        self.feed=Feed(self.snapshot)

    def bot(self,provider=None):
        provider=provider or Provider()
        bot=AutoTrader(self.settings,self.risk,self.inference,self.root/'work/autotrader',
                       self.root/'reports/autotrader',self.feed,lambda:provider)
        self.addCleanup(bot.close)
        return bot

    def complete(self,bot):
        if bot.pending:
            wait([bot.pending['future']],timeout=2)
            self.assertTrue(bot.pending['future'].done())
        bot.quote_tick()
        bot.finish_review()

    def entry(self,broker):
        quote=self.feed.quote('BTCUSDT')
        broker.observe([quote])
        trade=proposal({'action':'BUY','strategy':'ema_trend','reason':'Test'},self.snapshot,
                       analyze(self.snapshot),quote,self.settings,self.risk)
        return broker.execute('entry',trade,self.snapshot,quote),trade

    def test_buy_sell_and_hold_through_the_model_contract(self):
        provider=Provider()
        bot=self.bot(provider)
        bot.quote_tick()
        self.assertTrue(bot.start_review(self.snapshot))
        self.complete(bot)
        self.assertEqual(bot.last_decision['execution']['status'],'filled')
        self.assertEqual(bot.last_decision['decision']['action'],'BUY')
        self.assertIn('BTCUSDT',bot.broker.portfolio()['positions'])
        self.assertGreaterEqual(bot.broker.portfolio()['cash'],0)
        # A new closed bar is needed for another model decision.
        later=self.snapshot.as_of+301
        with patch('time.time',return_value=later):
            self.snapshot=sample(later)
            self.feed.data=self.snapshot
            provider.action='HOLD'
            bot.quote_tick()
            bot.start_review(self.snapshot)
            self.complete(bot)
            self.assertEqual(bot.last_decision['execution']['status'],'no_order')
            self.assertIn('BTCUSDT',bot.broker.portfolio()['positions'])
        later+=301
        with patch('time.time',return_value=later):
            self.snapshot=sample(later)
            self.feed.data=self.snapshot
            provider.action='SELL'
            bot.quote_tick()
            bot.start_review(self.snapshot)
            self.complete(bot)
            self.assertEqual(bot.last_decision['decision']['action'],'SELL')
            self.assertEqual(bot.last_decision['execution']['status'],'filled')
            self.assertEqual(bot.broker.portfolio()['positions'],{})
        with bot.broker.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM fills').fetchone()[0],2)

    def test_stop_executes_while_laya_is_busy_and_late_sell_is_discarded(self):
        event=threading.Event()
        self.addCleanup(event.set)
        bot=self.bot(Provider('SELL',event))
        fill,trade=self.entry(bot.broker)
        self.assertEqual(fill['status'],'filled')
        bot.quote_tick()
        bot.start_review(self.snapshot)
        self.assertFalse(bot.pending['future'].done())
        self.feed.bid=trade.stop*.99
        bot.step()
        self.assertEqual(bot.broker.portfolio()['positions'],{})
        self.assertFalse(bot.pending['future'].done())
        event.set()
        self.complete(bot)
        self.assertEqual(bot.last_decision['execution']['status'],'discarded_portfolio_changed')
        with bot.broker.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM fills').fetchone()[0],2)

    def test_stale_decision_and_operator_stop_cannot_place_entry(self):
        bot=self.bot()
        bot.quote_tick()
        bot.start_review(self.snapshot)
        bot.pending['monotonic_start']-=self.settings['decision_max_age_seconds']+1
        self.complete(bot)
        self.assertEqual(bot.last_decision['execution']['status'],'discarded_late_decision')
        self.assertEqual(bot.broker.portfolio()['positions'],{})
        other=AutoTrader(self.settings,self.risk,self.inference,self.root/'other',self.root/'other-reports',self.feed,lambda:Provider())
        self.addCleanup(other.close)
        other.quote_tick()
        other.start_review(self.snapshot)
        other.store.request_stop()
        self.complete(other)
        self.assertEqual(other.last_decision['execution']['status'],'discarded_on_stop')
        self.assertEqual(other.broker.portfolio()['positions'],{})

    def test_duplicate_bar_is_not_replayed_after_restart(self):
        provider=Provider('HOLD')
        bot=self.bot(provider)
        bot.quote_tick()
        bot.start_review(self.snapshot)
        self.complete(bot)
        self.assertFalse(bot.start_review(self.snapshot))
        bot.close()
        restarted=self.bot(provider)
        restarted.quote_tick()
        self.assertFalse(restarted.start_review(self.snapshot))
        self.assertEqual(len(provider.calls),1)

    def test_one_shot_does_not_schedule_a_second_symbol_after_completion(self):
        self.settings['symbols']=['BTCUSDT','ETHUSDT']
        self.risk['symbols']=['BTCUSDT','ETHUSDT']
        self.settings['snapshot_poll_seconds']=0
        self.feed.snapshot=lambda symbol,interval:sample(symbol=symbol)
        provider=Provider('HOLD')
        bot=self.bot(provider)
        with patch('cryptoscope.autotrader.engine.time.sleep',side_effect=lambda _:threading.Event().wait(.001)):
            bot.run(max_decisions=1,force_review=True,max_seconds=5)
        self.assertEqual(bot.finished_count,1)
        self.assertEqual(len(provider.calls),1)

    def test_pause_during_inference_prevents_buy_and_fill_counts_are_idempotent(self):
        bot=self.bot()
        bot.quote_tick()
        bot.start_review(self.snapshot)
        bot.broker.set_halt(True)
        self.complete(bot)
        self.assertIn('MANUAL_ENTRY_HALT',bot.last_decision['execution']['reasons'])
        self.assertEqual(bot.broker.portfolio()['positions'],{})
        bot.broker.set_halt(False)
        fill,trade=self.entry(bot.broker)
        again=bot.broker.execute('entry',trade,self.snapshot,self.feed.quote('BTCUSDT'))
        self.assertEqual(fill,again)
        self.assertEqual(bot.broker.risk_status()['entries_today'],1)

    def test_process_lock_excludes_a_second_owner(self):
        with ProcessLock(self.root/'engine.lock'):
            with self.assertRaises(RuntimeError):
                with ProcessLock(self.root/'engine.lock'):
                    pass
        with ProcessLock(self.root/'engine.lock'):
            pass

    def test_inflight_record_is_abandoned_without_execution_on_restart(self):
        store=BotStore(self.root/'bot')
        body=store.claim('one-bar',{'symbol':'BTCUSDT'})
        store.abandon_inflight()
        result=store.snapshot()['decisions'][0]
        self.assertEqual(result['status'],'abandoned')
        self.assertEqual(result['execution']['status'],'discarded_after_restart')
        self.assertIsNone(store.claim('one-bar',{'symbol':'BTCUSDT'}))

    def test_spread_cooldown_and_entry_count_limits_survive_restart(self):
        bot=self.bot()
        quote=self.feed.quote('BTCUSDT')
        wide={**quote,'ask':quote['bid']*1.02}
        self.assertIn('SPREAD_LIMIT',bot.broker.entry_status(wide))
        fill,trade=self.entry(bot.broker)
        self.assertEqual(fill['status'],'filled')
        restarted=AutoBroker(bot.broker.path,self.risk,self.settings)
        self.assertIn('ENTRY_COOLDOWN',restarted.entry_status(quote))
        with restarted.connect() as db:
            db.execute('UPDATE auto_risk SET entries=?,last_entry=0 WHERE id=1',(self.settings['max_entries_per_day'],))
        self.assertIn('DAILY_ENTRY_LIMIT',restarted.entry_status(quote))

    def test_loss_and_drawdown_halts_are_persistent_and_exits_remain_available(self):
        bot=self.bot()
        fill,trade=self.entry(bot.broker)
        with bot.broker.connect() as db:
            db.execute('UPDATE auto_risk SET day_start=20000 WHERE id=1')
        quote=self.feed.quote('BTCUSDT')
        state=bot.broker.observe([quote])
        self.assertEqual(state['halt_reason'],'DAILY_LOSS_LIMIT')
        restarted=AutoBroker(bot.broker.path,self.risk,self.settings)
        restarted.set_halt(False)
        self.assertIn('DAILY_LOSS_LIMIT',restarted.entry_status(quote))
        sell=proposal({'action':'SELL','strategy':'position_exit','reason':'Exit'},self.snapshot,
                      analyze(self.snapshot),quote,self.settings,self.risk)
        self.assertEqual(restarted.execute('exit',sell,self.snapshot,quote)['status'],'filled')
        self.assertEqual(restarted.portfolio()['positions'],{})
        restarted.reset_risk()
        with restarted.connect() as db:
            db.execute('UPDATE auto_risk SET peak=20000 WHERE id=1')
        self.assertEqual(restarted.risk_status()['halt_reason'],'DRAWDOWN_LIMIT')
        tomorrow=time.time()+86400
        self.assertEqual(restarted.risk_status(tomorrow)['halt_reason'],'DRAWDOWN_LIMIT')

    def test_trailing_stop_only_tightens(self):
        bot=self.bot()
        fill,trade=self.entry(bot.broker)
        quote=self.feed.quote('BTCUSDT')
        higher={**quote,'bid':trade.entry*1.03,'ask':trade.entry*1.0302}
        bot.broker.observe([higher])
        bot.broker.trail(higher,.1)
        stop=bot.broker.portfolio()['positions']['BTCUSDT']['stop']
        self.assertGreater(stop,trade.stop)
        bot.broker.trail(quote,.1)
        self.assertEqual(bot.broker.portfolio()['positions']['BTCUSDT']['stop'],stop)

    def test_fast_model_uses_one_short_non_thinking_call_and_no_invalid_retry(self):
        provider=LayaProvider(self.inference)
        prompt=context(self.snapshot,analyze(self.snapshot),{'cash':10000,'positions':{}},self.feed.quote('BTCUSDT'))
        response=io.BytesIO(json.dumps({'done':True,'done_reason':'stop','response':'{"action":"SHORT"}'}).encode())
        with patch('cryptoscope.providers.laya.urlopen',return_value=response) as request:
            with self.assertRaises(RuntimeError):
                provider.complete('fast_decider',prompt)
        self.assertEqual(request.call_count,1)
        payload=json.loads(request.call_args.args[0].data)
        self.assertFalse(payload['think'])
        self.assertEqual(payload['options']['num_predict'],48)
        self.assertEqual(payload['options']['num_ctx'],4096)
        self.assertEqual(payload['keep_alive'],'15m')

    def test_dashboard_reads_bot_without_creating_files_or_mixing_accounts(self):
        data=DashboardData(self.root,self.risk)
        self.assertFalse(data.autotrader()['available'])
        self.assertEqual(list(self.root.iterdir()),[])
        bot=self.bot(Provider('HOLD'))
        bot.quote_tick()
        bot.start_review(self.snapshot)
        self.complete(bot)
        bot.heartbeat()
        result=data.autotrader()
        self.assertEqual(result['decisions'][0]['run_id'],bot.last_decision['run_id'])
        self.assertEqual(result['runtime']['mode'],'paper')
        self.assertEqual(data.autotrader_run(bot.last_decision['run_id'])['snapshot']['source'],'synthetic_autotrader_test')
        with self.assertRaises(ValueError):
            data.autotrader_run('../../secrets')

    def test_live_mode_and_unknown_symbols_are_refused(self):
        path=self.root/'settings.json'
        for changes in ({'mode':'live'},{'symbols':['DOGEUSDT']},{'max_entries_per_day':True}):
            path.write_text(json.dumps(changes))
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                load_settings(path)

    def test_exchange_clock_ahead_is_clamped_without_open_candle_leakage(self):
        from cryptoscope.providers.binance import BinanceProvider
        now=time.time()
        data=sample(now)
        rows=[]
        for bar in data.candles:
            rows.append([bar['open_time']*1000,bar['open'],bar['high'],bar['low'],bar['close'],
                         bar['volume'],bar['close_time']*1000-1,0,0,bar['taker_buy_volume']])
        # This bar is closed for the deliberately ahead exchange clock but
        # unavailable at the receiver's current time.
        bar=rows[-1].copy()
        bar[0]+=300000
        bar[6]+=300000
        rows.append(bar)
        provider=BinanceProvider()
        provider.get=lambda path,**kwargs:{'serverTime':(data.candles[-1]['close_time']+301)*1000} if path.endswith('/time') else rows
        snapshot=provider.snapshot('BTCUSDT','5m')
        self.assertLessEqual(snapshot.as_of,time.time())
        self.assertEqual(len(snapshot.candles),200)
        self.assertLessEqual(snapshot.candles[-1]['close_time'],snapshot.as_of)

    def test_expanded_strategy_library_signals_and_proposals(self):
        analysis = analyze(self.snapshot)
        self.assertIn('mtf_confirmation', analysis['signals'])
        self.assertIn('volatility_squeeze', analysis['signals'])
        self.assertIn('macd_momentum_cross', analysis['signals'])
        # Sample data is an uptrend, so MTF and MACD confirmation trigger
        self.assertTrue(analysis['signals']['mtf_confirmation'])
        self.assertTrue(analysis['signals']['macd_momentum_cross'])
        self.assertIn('mtf_confirmation', analysis['candidates'])
        self.assertIn('macd_momentum_cross', analysis['candidates'])

        quote = self.feed.quote('BTCUSDT')
        # Proposal generation works seamlessly for all candidate strategies
        for strat in ('mtf_confirmation', 'macd_momentum_cross', 'ema_trend'):
            trade = proposal({'action': 'BUY', 'strategy': strat, 'reason': f'Testing {strat}'},
                             self.snapshot, analysis, quote, self.settings, self.risk)
            self.assertEqual(trade.action, 'LONG')
            self.assertEqual(trade.symbol, 'BTCUSDT')
            self.assertGreater(trade.target, trade.entry)
            self.assertLess(trade.stop, trade.entry)

    def test_fast_decision_layer_tier1_and_tier2_rules(self):
        from cryptoscope.autotrader.decision import Tier1Engine, LayaTier2Evaluator, FastDecisionLayer
        tier1 = Tier1Engine()
        candles = self.snapshot.candles

        # Tier 1 evaluation
        t1_res = tier1.evaluate(candles, symbol='BTCUSDT')
        self.assertIn(t1_res['action'], ['LONG', 'SHORT', 'STAND_ASIDE'])
        self.assertIn('discrete_encoding', t1_res)
        self.assertIn('trend=', t1_res['discrete_encoding'])
        self.assertLess(t1_res['latency_ms'], 20.0)  # Sub-20ms requirement

        # Fast Decision Layer with Laya Evaluator (fail-safe mode when laya uninstalled)
        evaluator = LayaTier2Evaluator()
        layer = FastDecisionLayer(evaluator)
        decision = layer.decide(candles, symbol='BTCUSDT')

        self.assertIn(decision['final_action'], ['LONG', 'SHORT', 'STAND_ASIDE'])
        self.assertIn('total_latency_ms', decision)
        self.assertEqual(len(layer.audit_log), 1)

        # When Tier 2 does not confirm, decision is strictly STAND_ASIDE
        if not decision['tier2']['agreed']:
            self.assertEqual(decision['final_action'], 'STAND_ASIDE')

    def test_laya_status_and_timeout_exceeded_reporting(self):
        from cryptoscope.autotrader.decision import LayaTier2Evaluator
        evaluator = LayaTier2Evaluator(timeout_ms=50.0)
        status = evaluator.get_status()
        self.assertIn("status", status)
        self.assertIn("pinned_threads", status)
        self.assertEqual(status["max_timeout_ms"], 50.0)

        # When evaluation exceeds timeout, status must be explicitly TIMEOUT_EXCEEDED
        dummy_t1 = {"action": "LONG", "discrete_encoding": "SMC:BULL_OB"}
        res = evaluator.evaluate(dummy_t1, simulate_delay_ms=80.0)
        self.assertEqual(res["status"], "TIMEOUT_EXCEEDED")
        self.assertFalse(res["agreed"])
        self.assertIn("exceeded", res["reason"])
