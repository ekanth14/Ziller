"""Stage 1: Data Cleaning and Preprocessing Engine (Formulas 1.1 - 1.6).

Formulas:
1.1 Log return: r = ln(P_t / P_{t-1})
1.2 Annualized volatility: sigma_year = sigma_bar * sqrt(bars_per_year)
1.3 EWMA volatility: sigma_t^2 = lambda * sigma_{t-1}^2 + (1 - lambda) * r_{t-1}^2
1.4 ATR: TR = max(H - L, |H - C_p|, |L - C_p|); ATR = avg_14(TR)
1.5 Bad tick filter: |r - mu| / sigma > 6 -> flag
1.6 No lookahead: position_t = f(data <= t-1) -> fill at next open
"""

import math
from typing import Sequence, Union


def compute_log_returns(prices: Sequence[float]) -> list[float]:
    """Calculate log returns r = ln(P_t / P_{t-1}) across a price series."""
    if len(prices) < 2:
        return []
    returns: list[float] = []
    for i in range(1, len(prices)):
        p_prev = prices[i - 1]
        p_curr = prices[i]
        if p_prev <= 0.0 or p_curr <= 0.0:
            raise ValueError(f"Prices must be strictly positive: {p_prev=}, {p_curr=}")
        returns.append(math.log(p_curr / p_prev))
    return returns


def compute_annualized_vol(
    bar_vol_or_returns: Union[float, Sequence[float]],
    bars_per_year: int = 365,
) -> float:
    """Annualize volatility: sigma_year = sigma_bar * sqrt(bars_per_year).

    Accepts either an already computed bar volatility (float) or a return series.
    """
    if isinstance(bar_vol_or_returns, (int, float)):
        return float(bar_vol_or_returns) * math.sqrt(bars_per_year)

    returns = list(bar_vol_or_returns)
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    bar_sigma = math.sqrt(variance)
    return bar_sigma * math.sqrt(bars_per_year)


def compute_ewma_vol(returns: Sequence[float], lambda_param: float = 0.94) -> list[float]:
    """Calculate RiskMetrics EWMA volatility: sigma_t^2 = lambda * sigma_{t-1}^2 + (1-lambda) * r_{t-1}^2."""
    if not returns:
        return []
    vols: list[float] = []
    current_sigma2 = returns[0] ** 2 if returns[0] != 0.0 else 1e-8
    vols.append(math.sqrt(current_sigma2))

    for i in range(1, len(returns)):
        r_prev = returns[i]
        current_sigma2 = lambda_param * current_sigma2 + (1.0 - lambda_param) * (r_prev ** 2)
        vols.append(math.sqrt(current_sigma2))
    return vols


def compute_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float]:
    """Calculate Average True Range (ATR): TR = max(H - L, |H - C_p|, |L - C_p|)."""
    n = len(closes)
    if n == 0 or len(highs) != n or len(lows) != n:
        return []

    tr_list: list[float] = []
    for i in range(n):
        h = highs[i]
        l = lows[i]
        if i == 0:
            tr = h - l
        else:
            c_prev = closes[i - 1]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_list.append(tr)

    atr_list: list[float] = []
    for i in range(n):
        if i + 1 < period:
            atr_list.append(sum(tr_list[: i + 1]) / (i + 1))
        else:
            atr_list.append(sum(tr_list[i + 1 - period : i + 1]) / period)
    return atr_list


def filter_bad_ticks(
    returns: Sequence[float],
    threshold_sigma: float = 6.0,
    baseline_sigma: float | None = None,
) -> list[bool]:
    """Flag returns that deviate more than threshold_sigma from mean: |r - mu| / sigma > 6.

    If baseline_sigma is provided, evaluates against historical baseline volatility.
    Otherwise computes robust standard deviation using median/IQR or trimmed values.
    """
    n = len(returns)
    if n == 0:
        return []

    if baseline_sigma is not None and baseline_sigma > 1e-12:
        mean_r = sum(returns) / n
        return [abs(r - mean_r) / baseline_sigma > threshold_sigma for r in returns]

    if n < 3:
        return [False] * n

    # Robust scale estimator: Median Absolute Deviation (MAD) * 1.4826
    sorted_r = sorted(returns)
    median_r = sorted_r[n // 2]
    abs_devs = sorted([abs(r - median_r) for r in returns])
    mad = abs_devs[n // 2]
    robust_sigma = 1.4826 * mad

    if robust_sigma <= 1e-12:
        # Fallback to standard deviation if MAD is zero
        mean_r = sum(returns) / n
        variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
        robust_sigma = math.sqrt(variance)

    if robust_sigma <= 1e-12:
        return [False] * n

    return [abs(r - median_r) / robust_sigma > threshold_sigma for r in returns]


def verify_no_lookahead(bar_index: int, signal_time: int, fill_time: int) -> bool:
    """Verify that signal on bar t is executed only at t+1 or later, never same-bar."""
    return fill_time > signal_time and signal_time >= bar_index
