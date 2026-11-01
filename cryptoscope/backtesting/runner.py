"""Archived closed-candle strategy evaluation using QuantJourney's simulator."""
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time
import uuid
import subprocess
from cryptoscope.agents.schemas import Snapshot
from cryptoscope.research.settings import ROOT, load_config
from cryptoscope.risk_tools.__main__ import run as risk_diagnostics


def evaluate(snapshot, config, fast=20, slow=50, strategy='ema_baseline', start_index=0, diagnostics=True):
    import pandas as pd
    from backtester.execution import ContractSpec, ExecutionSimulator, FillEngine, FixedBpsCommission, FixedBpsSlippage, Order, OrderSide
    from backtester.portfolio.accounting.ledger import PortfolioLedger
    from backtester.risk.pre_trade import PreTradeRisk
    if strategy not in {'ema_baseline', 'buy_hold_baseline'}:
        raise ValueError('Unknown baseline strategy')
    if not isinstance(fast, int) or not isinstance(slow, int) or not 1 < fast < slow < len(snapshot.candles)-2:
        raise ValueError('EMA periods require 1 < fast < slow < candle count - 2')
    if snapshot.symbol not in config['symbols']:
        raise ValueError('Snapshot symbol is not in the configured universe')
    if type(start_index) is not int or not 0 <= start_index < len(snapshot.candles)-2:
        raise ValueError('Invalid trading start boundary')
    candles = snapshot.candles
    dates = pd.to_datetime([c['open_time'] for c in candles], unit='s', utc=True)
    symbol = snapshot.symbol
    def frame(key):
        return pd.DataFrame({symbol: [c[key] for c in candles]}, index=dates, dtype=float)
    closes = frame('close')[symbol]
    fast_line = closes.ewm(span=fast, adjust=False).mean()
    slow_line = closes.ewm(span=slow, adjust=False).mean()
    # Offline research sizes are continuous; exchange rounding is not implied.
    spec = ContractSpec.crypto(symbol, quote_currency='USDT', quantity_step=None)
    ledger = PortfolioLedger(initial_cash=config['initial_cash'], instruments=[symbol],
                             contract_spec_resolver=lambda _: spec, settlement_currency='USDT')
    engine = FillEngine(fill_at='open', commission=FixedBpsCommission(bps=config['fee_fraction']*10000),
                        slippage=FixedBpsSlippage(bps=config['slippage_fraction']*10000),
                        notional_fn=ledger.trade_notional)
    simulator = ExecutionSimulator(fill_engine=engine, ledger=ledger,
        pre_trade_risk=PreTradeRisk(allow_short=False, max_gross_leverage=1,
                                   max_margin_utilization=1, reserve_pending_orders=True))
    fills, decisions, rejected = [], [], []
    rows = {d: i for i, d in enumerate(dates)}

    def on_bar(date, bars, positions, nav, average_entry):
        i = rows[date]
        if i < max(slow-1,start_index) or i == len(candles)-1:
            return
        held = positions[symbol]
        want = strategy == 'buy_hold_baseline' or fast_line.iloc[i] > slow_line.iloc[i]
        # Force a flat final bar via an order submitted at the penultimate close.
        if i == len(candles)-2:
            want = False
        side = None
        if want and held <= 1e-12:
            side = OrderSide.BUY
            quantity = min(nav*config['max_position_fraction'], ledger.cash*.95) / bars[symbol].close
        elif not want and held > 1e-12:
            side, quantity = OrderSide.SELL, held
        if side is None or quantity <= 0:
            return
        order = Order(instrument=symbol, side=side, quantity=quantity, created_at=date)
        outcome = simulator.submit_batch([order])
        decisions.append({'available_at': candles[i]['close_time'], 'side': side.value,
                          'quantity': quantity, 'order_id': order.order_id})
        rejected.extend(outcome.rejected_order_ids)

    def on_fill(fill, notional):
        fills.append({'order_id': fill.order_id, 'side': fill.side.value, 'quantity': fill.quantity,
                      'price': fill.fill_price, 'fee': fill.commission,
                      'executed_at': fill.timestamp.timestamp(), 'notional': notional})

    result = simulator.run(close=frame('close'), open_=frame('open'), high=frame('high'),
                           low=frame('low'), volume=frame('volume'), on_bar=on_bar, on_fill=on_fill)
    navs = [float(x) for x in result.nav]
    equity, pnls, returns, peak, max_drawdown = [], [], [], float(config['initial_cash']), 0.0
    previous = float(config['initial_cash'])
    for i, nav in enumerate(navs):
        pnl = nav-previous
        pnls.append(pnl)
        returns.append(100*pnl/previous if previous else 0)
        peak = max(peak, nav)
        drawdown = (peak-nav)/peak if peak else 0
        max_drawdown = max(max_drawdown, drawdown)
        equity.append({'time': candles[i]['close_time'], 'nav': nav, 'cash': float(result.cash.iloc[i]),
                       'position': float(result.positions.iloc[i][symbol]), 'drawdown_pct': drawdown*100})
        previous = nav
    signal_times = {d['order_id']: d['available_at'] for d in decisions}
    if any(f['executed_at'] < signal_times[f['order_id']] for f in fills):
        raise RuntimeError('A fill preceded the signal availability time')
    settings = {k: config[k] for k in ('initial_cash', 'max_position_fraction', 'fee_fraction', 'slippage_fraction')}
    fingerprint = hashlib.sha256(json.dumps({'snapshot': snapshot.to_dict(), 'settings': settings,
        'fast': fast, 'slow': slow, 'strategy': strategy, 'start_index':start_index}, sort_keys=True, allow_nan=False).encode()).hexdigest()
    report = {'kind': 'backtest', 'status': 'completed', 'strategy': strategy,
        'decision_source': 'deterministic_baseline_not_laya', 'symbol': symbol, 'source': snapshot.source,
        'engine': 'quantjourney-bt', 'engine_version': version('quantjourney-bt'),
        'fingerprint': fingerprint, 'interval_seconds': snapshot.interval_seconds,
        'period_start': candles[0]['open_time'], 'period_end': candles[-1]['close_time'],
        'parameters': {'fast': fast, 'slow': slow, 'start_index':start_index}, 'settings': settings,
        'metrics': {'initial_cash': config['initial_cash'], 'final_nav': navs[-1],
                    'net_return_pct': (navs[-1]/config['initial_cash']-1)*100,
                    'max_drawdown_pct': max_drawdown*100, 'fees': sum(f['fee'] for f in fills),
                    'fills': len(fills), 'rejected_orders': len(rejected)},
        'equity': equity, 'fills': fills, 'decisions': decisions, 'rejected_order_ids': rejected,
        'limitations': ['Baseline evaluation, not a historical Laya replay.',
            'No perpetual funding, liquidation, order-book impact or exchange lot rounding.',
            'Final exit is submitted at the penultimate close for the last open.',
            'Risk figures assume one USDT equals one USD for diagnostic comparison only.']}
    from cryptoscope.backtesting.validation import performance
    report['performance'] = performance(navs, config['initial_cash'], snapshot.interval_seconds)
    if not diagnostics:
        return report
    try:
        report['risk'] = risk_diagnostics({'source': 'quantjourney_nav_usdt_at_usd_parity_assumption',
                                          'pnl_usd': pnls, 'returns_pct': returns, 'positions': []})
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        report['risk'] = {'status': 'unavailable', 'error': str(error)}
    return report


def save_report(report, directory=None):
    root = Path(directory) if directory else ROOT/'reports/backtests'
    run_id = uuid.uuid4().hex
    output = root/run_id
    output.mkdir(parents=True)
    report = {**report, 'run_id': run_id, 'created_at': time.time()}
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    with (output/'equity.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['time','nav','cash','position','drawdown_pct'])
        writer.writeheader()
        writer.writerows(report['equity'])
    (output/'summary.md').write_text('# Zien baseline backtest\n\n'+
        f"Strategy: {report['strategy']} | Symbol: {report['symbol']}\n\n"+
        '```json\n'+json.dumps(report['metrics'], indent=2)+'\n```\n\n'+
        '\n'.join('- '+line for line in report['limitations']), encoding='utf-8')
    return report
