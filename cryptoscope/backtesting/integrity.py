"""Offline accounting and fixed two-leg stops. No broker or model access."""
from __future__ import annotations

import math


def trade_metrics(trades, initial_capital, equity_curve=()):
    """Pool net *trade* outcomes, never strategy net totals, for profit factor."""
    pnls = [float(t['pnl']) for t in trades]
    gross_profit = math.fsum(p for p in pnls if p > 0)
    gross_loss = math.fsum(-p for p in pnls if p < 0)
    net = math.fsum(pnls)
    peak = initial_capital
    drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak if peak > 0 else 0)
    return dict(
        total_trades=len(pnls), wins=sum(p > 0 for p in pnls),
        losses=sum(p < 0 for p in pnls), breakeven=sum(p == 0 for p in pnls),
        data_quality='sufficient trade count' if len(pnls) >= 30 else 'insufficient data',
        gross_profit_usd=gross_profit, gross_loss_usd=gross_loss,
        profit_factor=gross_profit / gross_loss if gross_loss else None,
        profit_factor_status='finite' if gross_loss else ('no losses' if gross_profit else 'no trades or gains'),
        win_rate_pct=100 * sum(p > 0 for p in pnls) / len(pnls) if pnls else None,
        net_pnl_usd=net, return_pct=100 * net / initial_capital,
        expectancy_usd=net / len(pnls) if pnls else None,
        max_drawdown_pct=100 * drawdown if equity_curve else None,
        fees_paid_usd=math.fsum(t['fees'] for t in trades) if all('fees' in t for t in trades) else None,
        initial_capital=initial_capital, final_capital=initial_capital + net,
    )


def pair_size(nav, eth, btc, beta, stop_fraction=0.02, risk_fraction=0.005,
              fee_rate=0.00075, gross_cap=0.30):
    """Log-price beta is a NOTIONAL hedge: q_b = beta*q_a*P_a/P_b.

    Both adverse leg stops are frozen at entry. Fees at these stops are inside
    the combined risk budget; entry/exit slippage and gaps are measured separately.
    No model can set this sizing or change a stop after entry.
    """
    values = (nav, eth, btc, beta, stop_fraction, risk_fraction, fee_rate, gross_cap)
    if not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError('Pair sizing requires finite positive inputs')
    if max(stop_fraction, risk_fraction, gross_cap) >= 1:
        raise ValueError('Invalid fractional pair limits')
    stop_eth, stop_btc = eth * (1 - stop_fraction), btc * (1 + stop_fraction)
    btc_per_eth = beta * eth / btc
    # Long ETH, short BTC; both can stop adversely in the same bar.
    loss_per_eth = eth - stop_eth + btc_per_eth * (stop_btc - btc)
    fees_per_eth = fee_rate * (eth + stop_eth + btc_per_eth * (btc + stop_btc))
    budget = nav * risk_fraction
    qty_eth = min(budget / (loss_per_eth + fees_per_eth), nav * gross_cap / (eth * (1 + beta)))
    qty_btc = -btc_per_eth * qty_eth
    return dict(quantity_eth=qty_eth, quantity_btc=qty_btc, stop_eth=stop_eth,
                stop_btc=stop_btc, risk_budget=budget,
                planned_loss=qty_eth * (loss_per_eth + fees_per_eth),
                gross_notional=qty_eth * eth + abs(qty_btc) * btc)


def settle_legs(legs, exit_prices, fee_rate, slippage):
    """Slippage opposes every signed leg. All four pair fees are included."""
    gross = fees = slip_cost = price_slip = 0.0
    for leg, price in zip(legs, exit_prices, strict=True):
        quantity, entry = leg['quantity'], leg['entry']
        sign = 1 if quantity > 0 else -1
        effective_entry = entry * (1 + sign * slippage)
        effective_exit = price * (1 - sign * slippage)
        gross += quantity * (effective_exit - effective_entry)
        actual_fee = abs(quantity) * (effective_entry + effective_exit) * fee_rate
        fees += actual_fee
        price_cost = abs(quantity) * (entry + price) * slippage
        price_slip += price_cost
        # Include the incremental fee effect of slipped prices in the budget
        # allowance, rather than concealing it with a tolerance.
        slip_cost += price_cost + actual_fee - abs(quantity)*(entry+price)*fee_rate
    return dict(pnl=gross - fees, fees=fees, slippage_usd=slip_cost,
                price_slippage_usd=price_slip)


def pair_stop_prices(plan, eth_bar, btc_bar):
    """Conservative OHLC stop envelope: both legs exit adversely on a breach.

    Independent extrema need not occur simultaneously. This is a pessimistic
    research bound, not a claim that exchange stop fills occur at those prices.
    Opening gaps remain uncapped and can exceed a fixed fractional budget.
    """
    if eth_bar['low'] <= plan['stop_eth'] or btc_bar['high'] >= plan['stop_btc']:
        return [min(eth_bar['open'],plan['stop_eth']),max(btc_bar['open'],plan['stop_btc'])]
    return None
