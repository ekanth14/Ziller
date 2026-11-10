"""Stage 7: Risk Management Engine (Formulas 7.1 - 7.6).

Formulas:
7.1 Max drawdown: DD = (peak - equity) / peak
7.2 Recovery math: gain_needed = DD / (1 - DD)
7.3 Value at Risk: VaR_95 = 1.645 * sigma * V
7.4 Portfolio volatility: sigma_p = sqrt(w^T * Sigma * w)
7.5 Risk of ruin: ruin = ((1 - p) / p)^N
7.6 Kill switch: equity < peak * (1 - DD_max) -> stop
"""

import math
from typing import Sequence, Tuple


def compute_max_drawdown(equity_series: Sequence[float]) -> Tuple[float, float, float]:
    """Calculate maximum peak-to-trough drawdown fraction, historical peak, and trough.

    Returns (max_dd_fraction, peak_value, trough_value).
    """
    if not equity_series:
        return 0.0, 0.0, 0.0
    if len(equity_series) == 1:
        return 0.0, equity_series[0], equity_series[0]

    peak = equity_series[0]
    max_dd = 0.0
    best_peak = peak
    best_trough = peak

    for val in equity_series:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 1e-12 else 0.0
        if dd > max_dd:
            max_dd = dd
            best_peak = peak
            best_trough = val

    return max_dd, best_peak, best_trough


def compute_recovery_gain(drawdown_pct: float) -> float:
    """Calculate required gain to recover from a given drawdown fraction: gain = DD / (1 - DD)."""
    if drawdown_pct >= 1.0:
        return float("inf")
    if drawdown_pct <= 0.0:
        return 0.0
    return drawdown_pct / (1.0 - drawdown_pct)


def compute_var_95(portfolio_value: float, daily_vol: float, z_score: float = 1.645) -> float:
    """Calculate 1-day 95% Parametric Value at Risk (VaR): VaR_95 = 1.645 * sigma * V."""
    return z_score * daily_vol * portfolio_value


def compute_portfolio_volatility(
    weights: Sequence[float],
    cov_matrix: Sequence[Sequence[float]],
) -> float:
    """Calculate total joint portfolio volatility: sigma_p = sqrt(w^T * Sigma * w)."""
    n = len(weights)
    if n == 0 or len(cov_matrix) != n:
        return 0.0

    # Matrix multiplication: w^T * Sigma * w
    var_p = 0.0
    for i in range(n):
        for j in range(n):
            var_p += weights[i] * cov_matrix[i][j] * weights[j]

    if var_p <= 0.0:
        return 0.0
    return math.sqrt(var_p)


def compute_risk_of_ruin(win_prob: float, units: int) -> float:
    """Calculate theoretical gambler's ruin probability for even-money bets: ruin = ((1 - p) / p)^N."""
    if units <= 0:
        return 1.0
    if win_prob <= 0.5:
        return 1.0
    if win_prob >= 1.0:
        return 0.0
    ratio = (1.0 - win_prob) / win_prob
    return ratio ** units


def check_kill_switch(
    current_equity: float,
    peak_equity: float,
    max_allowed_dd: float = 0.15,
) -> bool:
    """Evaluate hard kill switch condition: equity < peak * (1 - DD_max) -> True (halt required)."""
    if peak_equity <= 1e-12:
        return False
    threshold_equity = peak_equity * (1.0 - max_allowed_dd)
    return current_equity < threshold_equity
