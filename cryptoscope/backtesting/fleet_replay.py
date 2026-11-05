"""Research-only candle replay through the actual DebateBot and RiskBot.

No exchange/broker imports, network fallback, production DB writes or model
generation. Run the CLI only using the disposable research launcher.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from cryptoscope.autotrader.strategies.stat_arb_pairs import StatArbPairsStrategy
from cryptoscope.autotrader.strategies.volatility_breakout import VolatilityCompressionBreakoutStrategy
from cryptoscope.backtesting.debate_cache import RecordedDebateEngine
from cryptoscope.backtesting.integrity import pair_size, settle_legs, trade_metrics
from cryptoscope.orchestrator.bots.debate_bot import DebateBot
from cryptoscope.orchestrator.bots.risk_bot import RiskBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import DebateResult, PositionClosed, RiskDecision, TradeIntent

SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT')
FEE = 0.00075
FROZEN_PARAMETERS = dict(ema_fast=20, ema_slow=50, atr=14, atr_stop=1.5,
                         ema_target=3.0, pair_entry_z=1.8, pair_exit_z=0.25,
                         pair_z_stop=3.5, pair_window=30, pair_stop_fraction=0.02,
                         fee_rate=FEE, slippage_major=0.0005, slippage_alt=0.001,
                         risk_fraction=0.005, daily_loss=0.03, drawdown=0.10,
                         max_positions=3, max_coin=0.15, max_order=0.05,
                         correlation_cap=0.85, split_fraction=0.70)


def load_archive(path, count=2160):
    """Read-only, timestamp aligned and gap checked; never fetch missing data."""
    columns = 'open_time,open,high,low,close,volume,close_time,taker_buy_volume'
    store = {}
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA busy_timeout=5000')
        for symbol in SYMBOLS:
            rows = db.execute(f'SELECT {columns} FROM crypto_candles WHERE symbol=? '
                              "AND interval='1h' ORDER BY open_time", (symbol,)).fetchall()
            if len(rows) != count:
                raise ValueError('Archive length differs from the frozen 90-day dataset')
            candles = [dict(zip(columns.split(','), row)) for row in rows]
            for i, c in enumerate(candles):
                if not all(math.isfinite(x) for x in c.values()):
                    raise ValueError('Nonfinite candle')
                if not (0 < c['low'] <= min(c['open'], c['close']) <= max(c['open'], c['close']) <= c['high']):
                    raise ValueError('Invalid candle prices')
                if c['volume'] < 0 or not c['open_time'] < c['close_time'] < c['open_time'] + 3600:
                    raise ValueError('Invalid candle interval/volume')
                if i and c['open_time'] - candles[i-1]['open_time'] != 3600:
                    raise ValueError('Duplicate, gap or non-hourly archive')
            store[symbol] = candles
    times = [[c['open_time'] for c in store[s]] for s in SYMBOLS]
    if any(t != times[0] for t in times[1:]):
        raise ValueError('Cross-symbol timestamps disagree')
    return store


def data_fingerprint(store):
    return hashlib.sha256(json.dumps(store, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def indicators(candles):
    fast = slow = candles[0]['close']
    fasts, slows, atrs, trs = [], [], [], []
    atr = 0.0
    for i, c in enumerate(candles):
        price = c['close']
        fast += 2/21 * (price-fast)
        slow += 2/51 * (price-slow)
        fasts.append(fast)
        slows.append(slow)
        previous = candles[i-1]['close'] if i else price
        trs.append(max(c['high']-c['low'], abs(c['high']-previous), abs(c['low']-previous)))
        if i == 13:
            atr = sum(trs)/14
        elif i > 13:
            atr = (13*atr+trs[-1])/14
        atrs.append(atr)
    return fasts, slows, atrs


class ReplayPipeline:
    """Real risk checks and sizing; only debate inference is an offline adapter."""
    def __init__(self, capital=10000.0, records=None, mode='recorded'):
        self.bus = EventBus()
        self.risk = RiskBot(self.bus, initial_nav=capital)
        self.debate = DebateBot(self.bus, risk_bot=self.risk)
        self.engine = RecordedDebateEngine(records, mode)
        self.debate.deliberation_engine = self.engine
        self.counts = Counter()
        self.reasons = Counter()
        self.debates, self.decisions = [], []
        self.bus.subscribe(DebateResult, self._debate_result)
        self.bus.subscribe(RiskDecision, self._risk_result)
        self.day = None

    async def _debate_result(self, result):
        self.debates.append(result)

    async def _risk_result(self, result):
        self.decisions.append(result)

    def mark(self, nav, timestamp):
        # UTC calendar days, not wall-clock date. Daily latch resets only here;
        # the portfolio drawdown peak persists throughout the entire split.
        day = int(timestamp // 86400)
        if self.day != day:
            self.risk.daily_realized_pnl = 0.0
            self.risk.daily_loss_circuit_breaker = False
            self.day = day
        self.risk.current_nav = nav
        self.risk.peak_nav = max(self.risk.peak_nav, nav)

    def _veto(self, stage, reasons):
        self.counts[stage] += 1
        self.reasons.update(r.split(':', 1)[0] for r in reasons)

    async def approve(self, intent, *, pair_intent=None):
        self.counts['proposals'] += 1
        if self.risk.halt_state.snapshot()['halted']:
            self._veto('risk_pre_veto', ['EMERGENCY_HALT'])
            return None
        passed, reasons = self.risk.check_pre_trade_risk(intent)
        if pair_intent is not None:
            # Atomic pairs still obey gross correlation and position limits.
            # Never relax the live risk cap to make a research pair pass.
            positions = dict(self.risk.open_positions)
            try:
                self.risk.open_positions[intent.symbol] = dict(usd_value=0, quantity=0)
                other_passed, other_reasons = self.risk.check_pre_trade_risk(pair_intent)
                passed = passed and other_passed
                reasons += other_reasons
            finally:
                self.risk.open_positions = positions
        if not passed:
            self._veto('risk_pre_veto', reasons)
            return None
        self.debates.clear()
        await self.debate._deliberate_intent(intent)
        if len(self.debates) != 1:
            self._veto('debate_veto', ['DEBATE_OUTPUT_MISSING'])
            return None
        debate = self.debates[0]
        if debate.verdict != 'APPROVE' or debate.conviction_score < 6:
            self._veto('debate_veto', ['DEBATE_REJECT'])
            return None
        self.decisions.clear()
        await self.risk.on_event(intent)
        await self.risk._evaluate_risk(debate)
        self.risk.cached_intents.pop(intent.intent_id, None)
        if len(self.decisions) != 1 or self.decisions[0].decision != 'APPROVED':
            reasons = self.decisions[0].veto_reasons if self.decisions else ['RISK_OUTPUT_MISSING']
            self._veto('risk_post_veto', reasons)
            return None
        decision = self.decisions[0]
        nav, entry, stop = self.risk.current_nav, intent.entry_price, intent.stop_loss
        # RiskBot currently advertises max_order_pct without applying it to
        # fixed-fractional notional. Add a stricter research-only clamp; do not
        # relax or mutate the production limits. Reserve both fees inside risk.
        qty = min(decision.approved_quantity, nav*self.risk.max_order_pct/entry,
                  max(0,nav*self.risk.max_per_coin_pct-self.risk.open_positions.get(intent.symbol,{}).get('usd_value',0))/entry,
                  nav*self.risk.fixed_risk_fraction/(abs(entry-stop)+FEE*(entry+stop)))
        if not math.isfinite(qty) or qty <= 0:
            self._veto('risk_post_veto', ['INVALID_SIZE'])
            return None
        if qty < decision.approved_quantity:
            self.counts['size_reductions'] += 1
        self.counts['approved'] += 1
        return qty

    async def closed(self, trade):
        # The real risk event handler tracks realized loss and circuit breaker.
        await self.risk.on_event(PositionClosed(symbol=trade['symbols'][0], pnl_usd=trade['pnl']))

    def summary(self):
        names = ('proposals','risk_pre_veto','debate_veto','risk_post_veto','approved','size_reductions')
        result = {name: self.counts[name] for name in names}
        result.update(reasons=dict(self.reasons), debate_sources=dict(self.engine.counts))
        assert result['proposals'] == sum(result[n] for n in ('risk_pre_veto','debate_veto','risk_post_veto','approved'))
        return result


async def replay(store, *, mode='recorded', records=None, only=None, capital=10000.0):
    """One shared account. Close signals are processed at the next open.

    No future high/low/close enters the admission pipeline. Stops execute only
    after entry. Stop wins ambiguous bars; adverse opening gaps are not clipped.
    Pair shorts are research algebra, never executable Binance Spot orders.
    """
    pipeline = ReplayPipeline(capital, records, mode)
    risk = pipeline.risk
    n = len(store[SYMBOLS[0]])
    stats = {s: indicators(store[s]) for s in SYMBOLS}
    vol = VolatilityCompressionBreakoutStrategy()
    pairs = StatArbPairsStrategy(entry_zscore=1.8, exit_zscore=0.25, stop_zscore=3.5, window=30)
    cash = capital
    positions, trades, curve, pending = [], [], [capital], []
    no_signal = Counter()
    gap_excesses = []
    prefix_hash = hashlib.sha256()
    parameter_hash = hashlib.sha256(json.dumps(FROZEN_PARAMETERS,sort_keys=True).encode()).hexdigest()

    def equity_at(i, field):
        return cash + sum(sum(l['quantity']*(store[l['symbol']][i][field]-l['entry'])
                    - abs(l['quantity'])*l['entry']*(FEE+pos['slippage'])
                    for l in pos['legs']) for pos in positions)

    async def close_position(pos, prices, timestamp, reason):
        nonlocal cash
        result = settle_legs(pos['legs'], prices, FEE, pos['slippage'])
        trade = dict(result, strategy=pos['strategy'], symbols=[l['symbol'] for l in pos['legs']],
                     entry_time=pos['entry_time'], signal_time=pos['signal_time'],
                     exit_time=timestamp, reason=reason, risk_budget=pos['risk_budget'],
                     legs=pos['legs'], exit_prices=prices)
        trade['loss_budget_breach'] = -trade['pnl'] > trade['risk_budget'] + trade['slippage_usd'] + 1e-8
        if trade['loss_budget_breach']:
            gap_excesses.append(trade)
        cash += trade['pnl']
        risk.current_nav = cash - trade['pnl']
        await pipeline.closed(trade)
        for leg in pos['legs']:
            risk.open_positions.pop(leg['symbol'], None)
        positions.remove(pos)
        trades.append(trade)

    for i in range(n):
        first = store[SYMBOLS[0]][i]
        pipeline.mark(equity_at(i,'open'),first['open_time'])
        curve.append(equity_at(i,'open'))
        for symbol,holding in risk.open_positions.items():
            holding['usd_value'] = abs(holding['quantity'])*store[symbol][i]['open']
        # Fill exits decided at the preceding close before new admissions.
        for pos in list(positions):
            if pos.get('exit_pending'):
                await close_position(pos,[store[l['symbol']][i]['open'] for l in pos['legs']],
                                     first['open_time'],pos['exit_pending'])
        pipeline.mark(equity_at(i,'open'),first['open_time'])
        for proposal in pending:
            symbol, strategy = proposal['symbol'],proposal['strategy']
            if symbol in risk.open_positions:
                pipeline.counts['proposals'] += 1
                pipeline._veto('risk_pre_veto',['EXISTING_SYMBOL'])
                continue
            entry = store[symbol][i]['open']
            nav = equity_at(i,'open')
            pipeline.mark(nav,first['open_time'])
            if strategy == 'stat_arb_pairs':
                btc = store['BTCUSDT'][i]['open']
                beta = proposal['beta']
                if beta <= 0 or 'BTCUSDT' in risk.open_positions:
                    pipeline.counts['proposals'] += 1
                    pipeline._veto('risk_pre_veto',['PAIR_INVALID_OR_HELD'])
                    continue
                plan = pair_size(nav,entry,btc,beta)
                stop,target = plan['stop_eth'],entry*1.04
                other = TradeIntent(symbol='BTCUSDT',direction='SELL',entry_price=btc,
                                    stop_loss=plan['stop_btc'],take_profit=btc*0.96)
                proposal['context'].update(beta=beta,btc=btc)
            else:
                stop,target,other = proposal['stop'],proposal['target'],None
                if not 0 < stop < entry < target:
                    pipeline.counts['proposals'] += 1
                    pipeline._veto('risk_pre_veto',['INVALID_NEXT_OPEN_BRACKET'])
                    continue
            intent = TradeIntent(symbol=symbol,strategy_id=strategy,entry_price=entry,
                                 stop_loss=stop,take_profit=target,
                                 metadata={'debate_context':proposal['context']})
            qty = await pipeline.approve(intent,pair_intent=other)
            if qty is None:
                continue
            if other is not None:
                raise RuntimeError('Atomic pair approval needs review before research fills')
            slip = 0.0005 if symbol in SYMBOLS[:2] else 0.001
            positions.append(dict(strategy=strategy,legs=[dict(symbol=symbol,quantity=qty,entry=entry)],
                entry_time=first['open_time'],signal_time=proposal['context']['bar_close'],
                stop=stop,target=target,risk_budget=nav*0.005,slippage=slip))
            risk.open_positions[symbol] = dict(quantity=qty,entry=entry,usd_value=qty*entry)
        pending = []
        for pos in list(positions):
            leg = pos['legs'][0]
            c = store[leg['symbol']][i]
            if c['low'] <= pos['stop']:
                await close_position(pos,[min(c['open'],pos['stop'])],c['close_time'],'STOP_LOSS')
            elif c['high'] >= pos['target']:
                await close_position(pos,[pos['target']],c['close_time'],'TAKE_PROFIT')
            elif i == n-1:
                await close_position(pos,[c['close']],c['close_time'],'END_OF_BACKTEST')
            elif pos['strategy'] == 'ema_trend' and stats[leg['symbol']][0][i] < stats[leg['symbol']][1][i]:
                pos['exit_pending'] = 'TREND_FLIP'
        equity = equity_at(i,'close')
        pipeline.mark(equity,first['close_time'])
        curve.append(equity)
        prefix_hash.update(json.dumps({s:store[s][i] for s in SYMBOLS},sort_keys=True).encode())
        if i < 50 or i >= n-1:
            continue
        context = dict(bar_close=first['close_time'],history=prefix_hash.hexdigest(),parameters=parameter_hash)
        for symbol in SYMBOLS:
            for strategy in ('ema_trend','volatility_breakout'):
                if only is not None and only != (strategy,symbol):
                    continue
                fast,slow,atr = stats[symbol]
                price = store[symbol][i]['close']
                stop,target = price-1.5*atr[i],price+3*atr[i]
                signal = fast[i] > slow[i] and fast[i-1] <= slow[i-1]
                if strategy == 'volatility_breakout':
                    res = vol.evaluate(store[symbol][max(0,i-65):i+1])
                    signal = bool(res and res.get('side') == 'BUY')
                    if signal:
                        stop,target = res['stop_loss'],res['take_profit']
                if not signal:
                    no_signal[f'{strategy}/{symbol}'] += 1
                    continue
                pending.append(dict(symbol=symbol,strategy=strategy,stop=stop,target=target,
                                    context=dict(context)))
        if only is None or only == ('stat_arb_pairs','ETH/BTC'):
            res = pairs.evaluate_pair(store['ETHUSDT'][:i+1],store['BTCUSDT'][:i+1])
            if not res or res.get('side') != 'LONG_SPREAD':
                no_signal['stat_arb_pairs/ETH/BTC'] += 1
            else:
                pending.append(dict(symbol='ETHUSDT',strategy='stat_arb_pairs',
                                    beta=res['hedge_ratio_beta'],context=dict(context)))
    if positions:
        raise AssertionError('Unclosed research positions')
    assert math.isclose(cash-capital,math.fsum(t['pnl'] for t in trades),abs_tol=1e-7)
    return dict(metrics=trade_metrics(trades,capital,curve),trades=trades,equity_curve=curve,
                stages=pipeline.summary(),no_signal=dict(no_signal),
                debate_request_keys=pipeline.engine.keys,loss_budget_breaches=gap_excesses)
