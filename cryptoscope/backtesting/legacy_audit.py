"""Instrument the frozen local baseline in a disposable copy for evidence only.

This intentionally preserves its known defects. It is never an execution path
for current backtests and must not be imported by the production runtime.
"""
import ast
from pathlib import Path

from cryptoscope.backtesting.integrity import trade_metrics


class _ExposeLedger(ast.NodeTransformer):
    def visit_FunctionDef(self,node):
        if node.name not in {'run_strategy_backtest','run_stat_arb_backtest'}:
            return node
        is_pair = node.name == 'run_stat_arb_backtest'
        for child in ast.walk(node):
            if isinstance(child,ast.Return) and isinstance(child.value,ast.Dict):
                names = [k.value for k in child.value.keys if isinstance(k,ast.Constant)]
                if 'total_trades' in names:
                    child.value.keys.append(ast.Constant('trade_ledger'))
                    child.value.values.append(ast.Name(id='trades',ctx=ast.Load()))
            if isinstance(child,ast.Call) and isinstance(child.func,ast.Attribute):
                if isinstance(child.func.value,ast.Name) and child.func.value.id == 'trades' and child.func.attr == 'append':
                    ledger = child.args[0]
                    fields = [
                        ('risk_budget','risk_usd'),('entry_fee','fees_entry'),
                        ('quantity_eth','position_eth'),('quantity_btc','position_btc'),
                        ('entry_eth','entry_eth'),('entry_btc','entry_btc'),
                        ('exit_eth','eff_exit_eth'),('exit_btc','eff_exit_btc'),
                        ('full_fee_pnl','net_trade_pnl-fees_entry'),('fees','fees_entry+fees')
                    ] if is_pair else [
                        ('entry_fee','cost_basis*FEE_RATE'),('full_fee_pnl','pnl-cost_basis*FEE_RATE'),
                        ('fees','cost_basis*FEE_RATE+fee')]
                    for key,expression in fields:
                        ledger.keys.append(ast.Constant(key))
                        ledger.values.append(ast.parse(expression,mode='eval').body)
        return node


def audit_legacy(source_path,store):
    tree = _ExposeLedger().visit(ast.parse(Path(source_path).read_text(encoding='utf-8')))
    # Do not execute the historical CLI or any data loader/network function.
    tree.body = [n for n in tree.body if not isinstance(n,ast.If)]
    ast.fix_missing_locations(tree)
    namespace = {'__name__':'frozen_legacy_audit'}
    exec(compile(tree,'frozen_local_baseline','exec'),namespace)
    results,violations,slippage_violations = [],[],[]
    for split in ('TRAIN','TEST'):
        lo,hi = (0,1512) if split == 'TRAIN' else (1512,2160)
        for symbol in ('BTCUSDT','ETHUSDT','SOLUSDT'):
            for strategy in ('ema_trend','volatility_breakout'):
                results.append(namespace['run_strategy_backtest'](strategy,symbol,store[symbol][lo:hi],split=='TRAIN'))
        pair = namespace['run_stat_arb_backtest'](store['ETHUSDT'][lo:hi],store['BTCUSDT'][lo:hi],split=='TRAIN')
        for t in pair['trade_ledger']:
            t['loss_to_budget'] = -t['full_fee_pnl']/t['risk_budget']
            entry_a,entry_b = t['entry_eth']/1.0005,t['entry_btc']/0.9995
            exit_a,exit_b = t['exit_eth']/0.9995,t['exit_btc']/1.0005
            qa,qb = abs(t['quantity_eth']),abs(t['quantity_btc'])
            t['price_slippage_usd'] = (qa*(entry_a+exit_a)+qb*(entry_b+exit_b))*0.0005
            # Baseline entry fee was a fixed notional charge, not based on
            # effective leg values. Only its exit fee changes with slippage.
            fee_slippage = 0.00075*(qa*(t['exit_eth']-exit_a)+qb*(t['exit_btc']-exit_b))
            t['slippage_allowance_usd'] = t['price_slippage_usd']+fee_slippage
            t['loss_exceeds_budget_plus_slippage'] = -t['full_fee_pnl'] > t['risk_budget']+t['slippage_allowance_usd']+1e-8
            if t['loss_to_budget'] > 1:
                violations.append(dict(t,split=split))
            if t['loss_exceeds_budget_plus_slippage']:
                slippage_violations.append(dict(t,split=split))
        results.append(pair)
    aggregates = {}
    for split in ('TRAIN','TEST'):
        rows = [r for r in results if r['split'].startswith(split)]
        trades = [dict(t,pnl=t['full_fee_pnl']) for r in rows for t in r['trade_ledger']]
        aggregates[split] = trade_metrics(trades,70000.0)
        aggregates[split]['note'] = 'Legacy fills with entry fees restored to trade PnL; no equity curve retained. Not corrected execution/risk performance.'
        assert abs(sum(t['pnl'] for t in trades)-sum(r['net_pnl_usd'] for r in rows)) < 0.05
    multiples = sorted(t['loss_to_budget'] for t in violations)
    return dict(source_revision='676af22',results=results,ledger_aggregates=aggregates,
                pair_risk_budget_violations=violations,
                pair_budget_plus_slippage_violations=slippage_violations,
                pair_budget_plus_slippage_violation_count=len(slippage_violations),
                pair_violation_count=len(violations),
                pair_worst_loss_multiple=max(multiples) if multiples else None,
                pair_median_violation_multiple=multiples[len(multiples)//2] if multiples else None)
