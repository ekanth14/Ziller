"""Stage 8: Strategy Validation & Cross-Validation Engine (Formulas 8.1 - 8.6).

Formulas:
8.1 Sharpe ratio: SR = mean(r - r_f) / sigma * sqrt(bars_per_year)
8.2 Sharpe t-stat: t \approx SR * sqrt(years)
8.3 Multiple testing: P(>= 1 false) = 1 - (1 - alpha)^N
8.4 Best of N noise: E[max SR] \approx sigma_SR * sqrt(2 * ln(N))
8.5 Walk-forward: train [t0, t1] -> test [t1, t2] -> roll
8.6 Monte Carlo: shuffle trades x 1,000 -> 95th percentile DD
"""

import math
import random
from typing import Sequence, Tuple

from core.quant import native as _native


def compute_sharpe_ratio(
    returns: Sequence[float],
    rf: float = 0.0,
    bars_per_year: int = 365,
) -> float:
    """Calculate annualized Sharpe Ratio: SR = mean(r - r_f) / sigma * sqrt(bars_per_year)."""
    if len(returns) < 2:
        return 0.0
    excess = [r - (rf / bars_per_year) for r in returns]
    mean_e = sum(excess) / len(excess)
    var = sum((e - mean_e) ** 2 for e in excess) / (len(excess) - 1)
    sigma = math.sqrt(var)
    if sigma <= 1e-12:
        return 0.0
    return (mean_e / sigma) * math.sqrt(bars_per_year)


def compute_sharpe_tstat(sharpe: float, years: float) -> float:
    """Calculate t-statistic of Sharpe ratio: t \approx SR * sqrt(years)."""
    if years <= 0.0:
        return 0.0
    return sharpe * math.sqrt(years)


def compute_multiple_testing_p_false(alpha: float, n_tests: int) -> float:
    """Calculate probability of at least one false discovery: P(>= 1 false) = 1 - (1 - alpha)^N."""
    if n_tests <= 0:
        return 0.0
    alpha_clamped = max(0.0, min(1.0, alpha))
    return 1.0 - ((1.0 - alpha_clamped) ** n_tests)


def compute_best_of_n_noise_expected_sharpe(
    n_tests: int,
    sigma_sharpe: float = 0.5,
) -> float:
    """Calculate expected maximum Sharpe ratio from pure random noise: E[max SR] \approx sigma_SR * sqrt(2 * ln(N))."""
    if n_tests <= 1:
        return 0.0
    return sigma_sharpe * math.sqrt(2.0 * math.log(n_tests))


def generate_walk_forward_windows(
    total_bars: int,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
) -> list[Tuple[slice, slice]]:
    """Generate rolling walk-forward train and out-of-sample test window slices."""
    if step_bars is None:
        step_bars = test_bars

    windows: list[Tuple[slice, slice]] = []
    start = 0

    while start + train_bars + test_bars <= total_bars:
        train_slice = slice(start, start + train_bars)
        test_slice = slice(start + train_bars, start + train_bars + test_bars)
        windows.append((train_slice, test_slice))
        start += step_bars

    return windows


def run_monte_carlo_drawdown(
    trade_pnls: Sequence[float],
    iterations: int = 1000,
    confidence: float = 0.95,
    initial_equity: float = 10000.0,
    seed: int | None = 42,
) -> float:
    """Shuffle trade sequence across N iterations and return percentile maximum drawdown fraction.

    Confidence 0.95 returns the 95th percentile worst drawdown. Uses the native C++ kernel
    (bit-identical shuffles to Python's random.Random) when available, else pure Python.
    """
    if not trade_pnls:
        return 0.0
    if seed is not None:
        fast = _native.monte_carlo_drawdown(list(trade_pnls), iterations, confidence, initial_equity, seed)
        if fast is not None:
            return fast
    return run_monte_carlo_drawdown_py(trade_pnls, iterations, confidence, initial_equity, seed)


def run_monte_carlo_drawdown_py(
    trade_pnls: Sequence[float],
    iterations: int = 1000,
    confidence: float = 0.95,
    initial_equity: float = 10000.0,
    seed: int | None = 42,
) -> float:
    """Pure-Python reference implementation (source of truth and fallback)."""
    if not trade_pnls:
        return 0.0

    rng = random.Random(seed)
    pnls = list(trade_pnls)
    max_dds: list[float] = []

    for _ in range(iterations):
        shuffled = list(pnls)
        rng.shuffle(shuffled)

        equity = initial_equity
        peak = equity
        max_dd = 0.0

        for pnl in shuffled:
            equity += pnl
            if equity > peak:
                peak = equity
            if peak > 1e-12:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd

        max_dds.append(max_dd)

    max_dds.sort()
    idx = int(confidence * len(max_dds))
    idx = min(idx, len(max_dds) - 1)
    return max_dds[idx]
