"""Stage 2: Signal Generation Engine (Formulas 2.1 - 2.6).

Formulas:
2.1 Z-score: z = (x - mu_n) / sigma_n
2.2 EMA: EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1}, alpha = 2 / (n + 1)
2.3 Momentum 12-1: mom = P(t-21) / P(t-252) - 1
2.4 RSI: RSI = 100 - 100 / (1 + avg_gain / avg_loss)
2.5 Order book imbalance: I = (Q_bid - Q_ask) / (Q_bid + Q_ask)
2.6 Funding carry: APR = funding_per_8h * 3 * 365
"""

import math
from typing import Sequence


def compute_zscore(values: Sequence[float], window: int = 20) -> list[float]:
    """Calculate rolling Z-score: z = (x - mu_n) / sigma_n."""
    n = len(values)
    if n == 0:
        return []

    z_scores: list[float] = []
    for i in range(n):
        start_idx = max(0, i + 1 - window)
        sub = values[start_idx : i + 1]
        m = len(sub)
        if m < 2:
            z_scores.append(0.0)
            continue
        mean_val = sum(sub) / m
        var = sum((x - mean_val) ** 2 for x in sub) / (m - 1)
        std_val = math.sqrt(var)
        if std_val <= 1e-12:
            z_scores.append(0.0)
        else:
            z_scores.append((values[i] - mean_val) / std_val)
    return z_scores


def compute_ema(values: Sequence[float], period: int = 20) -> list[float]:
    """Calculate Exponential Moving Average: EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1}.

    alpha = 2 / (period + 1)
    """
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    ema_list: list[float] = [values[0]]
    for i in range(1, len(values)):
        val = alpha * values[i] + (1.0 - alpha) * ema_list[-1]
        ema_list.append(val)
    return ema_list


def compute_momentum_12_1(
    prices: Sequence[float],
    lag_short: int = 21,
    lag_long: int = 252,
) -> float:
    """Calculate 12-1 momentum: mom = P(t - lag_short) / P(t - lag_long) - 1.

    Skips the most recent month (lag_short) to avoid short-term reversal.
    """
    n = len(prices)
    if n < lag_long:
        return 0.0
    p_short = prices[n - 1 - lag_short]
    p_long = prices[n - 1 - lag_long]
    if p_long <= 0.0:
        return 0.0
    return (p_short / p_long) - 1.0


def compute_rsi(prices: Sequence[float], period: int = 14) -> list[float]:
    """Calculate Relative Strength Index: RSI = 100 - 100 / (1 + avg_gain / avg_loss)."""
    n = len(prices)
    if n < 2:
        return [50.0] * n

    deltas = [prices[i] - prices[i - 1] for i in range(1, n)]
    gains = [max(0.0, d) for d in deltas]
    losses = [max(0.0, -d) for d in deltas]

    rsi_list: list[float] = [50.0]  # First bar has no delta

    # Wilder's smoothing or simple rolling average
    for i in range(len(deltas)):
        start_idx = max(0, i + 1 - period)
        sub_gains = gains[start_idx : i + 1]
        sub_losses = losses[start_idx : i + 1]
        avg_gain = sum(sub_gains) / len(sub_gains) if sub_gains else 0.0
        avg_loss = sum(sub_losses) / len(sub_losses) if sub_losses else 0.0

        if avg_loss <= 1e-12:
            rsi = 100.0 if avg_gain > 0.0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi_list.append(rsi)
    return rsi_list


def compute_order_book_imbalance(bid_qty: float, ask_qty: float) -> float:
    """Calculate Order Book Imbalance: I = (Q_bid - Q_ask) / (Q_bid + Q_ask)."""
    total = bid_qty + ask_qty
    if total <= 1e-12:
        return 0.0
    return (bid_qty - ask_qty) / total


def compute_funding_carry_apr(funding_rate_8h: float) -> float:
    """Annualize 8h perp funding rate carry: APR = funding * 3 * 365."""
    return funding_rate_8h * 3.0 * 365.0
