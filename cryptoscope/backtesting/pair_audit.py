"""Pair stop/accounting diagnostic, not an approved trading pipeline.

The real RiskBot rejects ETH/BTC on correlation. This separate mechanical
exercise tests the loss bound on actual candles; it cannot authorize fills.
"""
from cryptoscope.autotrader.strategies.stat_arb_pairs import StatArbPairsStrategy
from cryptoscope.backtesting.integrity import pair_size, pair_stop_prices, settle_legs, trade_metrics


def audit_pair_stops(eth,btc,capital=10000.0):
    if [c['open_time'] for c in eth] != [c['open_time'] for c in btc]:
        raise ValueError('Pair timestamps must match')
    strategy = StatArbPairsStrategy(entry_zscore=1.8,exit_zscore=0.25,stop_zscore=3.5,window=30)
    cash, position, pending = capital,None,None
    trades,curve = [],[capital]
    for i,(a,b) in enumerate(zip(eth,btc,strict=True)):
        if pending is not None and position is None:
            plan = pair_size(cash,a['open'],b['open'],pending['beta'])
            position = dict(plan=plan,entry_time=a['open_time'],
                signal_time=pending['time'],legs=[
                    dict(symbol='ETHUSDT',quantity=plan['quantity_eth'],entry=a['open']),
                    dict(symbol='BTCUSDT',quantity=plan['quantity_btc'],entry=b['open'])])
        pending = None
        if position:
            timestamp = a['close_time']
            if position.get('exit_pending'):
                prices,reason,timestamp = [a['open'],b['open']],'MEAN_REVERSION_OR_Z_STOP',a['open_time']
            else:
                prices = pair_stop_prices(position['plan'],a,b)
                reason = 'PAIR_PRICE_STOP' if prices else None
            if prices is None and i == len(eth)-1:
                prices,reason = [a['close'],b['close']],'END_OF_BACKTEST'
            if prices is not None:
                result = settle_legs(position['legs'],prices,0.00075,0.0005)
                result.update(entry_time=position['entry_time'],signal_time=position['signal_time'],
                              exit_time=timestamp,reason=reason,legs=position['legs'],exit_prices=prices,
                              risk_budget=position['plan']['risk_budget'],planned_loss=position['plan']['planned_loss'])
                result['loss_budget_breach'] = -result['pnl'] > result['risk_budget']+result['slippage_usd']+1e-8
                cash += result['pnl']
                trades.append(result)
                position = None
        equity = cash
        if position:
            equity += sum(l['quantity']*(price-l['entry'])-abs(l['quantity'])*l['entry']*0.00125
                          for l,price in zip(position['legs'],[a['close'],b['close']],strict=True))
        curve.append(equity)
        if i < 45 or i == len(eth)-1:
            continue
        result = strategy.evaluate_pair(eth[:i+1],btc[:i+1])
        if position is not None:
            if result and result.get('side') in {'EXIT_TARGET','STOP_LOSS'}:
                position['exit_pending'] = True
        elif result and result.get('side') == 'LONG_SPREAD' and result['hedge_ratio_beta'] > 0:
            pending = dict(beta=result['hedge_ratio_beta'],time=a['close_time'])
    return dict(label='mechanical sizing audit only; bypasses approval pipeline; not deployable',
                metrics=trade_metrics(trades,capital,curve),trades=trades,
                loss_budget_breaches=[t for t in trades if t['loss_budget_breach']])
