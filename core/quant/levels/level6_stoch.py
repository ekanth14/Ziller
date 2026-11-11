"""Level 6: Stochastic Calculus & Random Processes Engine (Formulas 6.1 - 6.5).

Formulas:
6.1 Random Walk: X_t = sum(Z_i), Var(X_t) = t * sigma^2 (sqrt(t) diffusion scaling)
6.2 Brownian Motion: Wiener process W_t - W_s ~ N(0, t-s), W_0 = 0
6.3 Geometric Brownian Motion (GBM): S_t = S_0 * exp((mu - 0.5*sigma^2)*t + sigma*W_t)
6.4 Itô's Lemma: df = (df/dt + mu*S*df/dS + 0.5*sigma^2*S^2*d2f/dS2)dt + sigma*S*df/dS*dW
6.5 Martingales & Gambler's Ruin: P(ruin) = ((1-p)/p)^N
"""

from __future__ import annotations

import math
from typing import Sequence
import numpy as np


# ---------------------------------------------------------------------------
# Formula 6.1: Random Walk
# ---------------------------------------------------------------------------

def simulate_random_walk(
    steps: int,
    x0: float = 0.0,
    step_size: float = 1.0,
    p_up: float = 0.5,
    seed: int | None = None,
) -> list[float]:
    """Simulate a discrete random walk path: X_t = X_0 + sum_{i=1}^t Z_i.

    Parameters:
        steps: Number of discrete steps.
        x0: Starting level.
        step_size: Size of up/down move (+step_size or -step_size).
        p_up: Probability of an upward step.
        seed: Optional RNG seed.
    """
    if steps < 0:
        raise ValueError(f"Steps must be non-negative: {steps=}")
    if steps == 0:
        return [x0]

    rng = np.random.default_rng(seed)
    # Generate Bernoulli steps (+1 with prob p_up, -1 with prob 1 - p_up)
    flips = rng.uniform(0.0, 1.0, size=steps)
    increments = np.where(flips < p_up, step_size, -step_size)

    path = [x0]
    curr = x0
    for inc in increments:
        curr += float(inc)
        path.append(curr)

    return path


def compute_random_walk_variance(
    time_steps: int | float,
    sigma: float = 1.0,
    dt: float = 1.0,
) -> float:
    """Calculate variance of a random walk: Var(X_t) = t * sigma^2 * dt."""
    if time_steps <= 0:
        return 0.0
    return float(time_steps) * (sigma ** 2) * dt


def compute_diffusion_scaling(sigma: float, time_t: float) -> float:
    """Compute diffusion standard deviation scaling: sigma * sqrt(t)."""
    if time_t <= 0.0:
        return 0.0
    return sigma * math.sqrt(time_t)


# ---------------------------------------------------------------------------
# Formula 6.2: Brownian Motion (Wiener Process)
# ---------------------------------------------------------------------------

def simulate_brownian_motion(
    t: float,
    n_steps: int,
    seed: int | None = None,
) -> tuple[list[float], list[float]]:
    """Simulate continuous standard Brownian motion (Wiener process) W_t for t in [0, T].

    Guarantees:
    - W_0 = 0
    - Independent increments: W_{t+dt} - W_t ~ N(0, dt)
    - Returns (times, w_values)
    """
    if t < 0.0:
        raise ValueError(f"Time horizon t cannot be negative: {t=}")
    if t == 0.0:
        return [0.0], [0.0]
    if n_steps <= 0:
        raise ValueError(f"n_steps must be strictly positive: {n_steps=}")

    rng = np.random.default_rng(seed)
    dt = t / n_steps
    sqrt_dt = math.sqrt(dt)

    dw = rng.normal(0.0, sqrt_dt, size=n_steps)
    w = np.empty(n_steps + 1, dtype=float)
    w[0] = 0.0
    np.cumsum(dw, out=w[1:])

    times = [i * dt for i in range(n_steps + 1)]
    times[-1] = t  # prevent precision drift on endpoint

    return times, w.tolist()


# ---------------------------------------------------------------------------
# Formula 6.3: Geometric Brownian Motion (GBM)
# ---------------------------------------------------------------------------

def simulate_gbm_path(
    s0: float,
    mu: float,
    sigma: float,
    t: float,
    n_steps: int,
    seed: int | None = None,
) -> tuple[list[float], list[float]]:
    """Simulate Geometric Brownian Motion price trajectory:

    S_t = S_0 * exp((mu - 0.5 * sigma^2) * t + sigma * W_t)

    Guarantees:
    - Prices are strictly positive (S_t > 0), preventing negative prices.
    - Exact analytical discretization.
    """
    if s0 <= 0.0:
        raise ValueError(f"Initial price s0 must be strictly positive: {s0=}")
    if t <= 0.0:
        raise ValueError(f"Time horizon t must be strictly positive: {t=}")
    if n_steps <= 0:
        raise ValueError(f"n_steps must be strictly positive: {n_steps=}")

    times, w = simulate_brownian_motion(t=t, n_steps=n_steps, seed=seed)

    drift_term = mu - 0.5 * (sigma ** 2)
    prices = [s0]
    for i in range(1, len(times)):
        curr_t = times[i]
        curr_w = w[i]
        s_t = s0 * math.exp(drift_term * curr_t + sigma * curr_w)
        prices.append(s_t)

    return times, prices


def gbm_expected_value(s0: float, mu: float, t: float) -> float:
    """Calculate theoretical expected value under GBM: E[S_t] = S_0 * exp(mu * t)."""
    return s0 * math.exp(mu * t)


def gbm_variance(s0: float, mu: float, sigma: float, t: float) -> float:
    """Calculate theoretical variance under GBM: Var(S_t) = S_0^2 * exp(2*mu*t) * (exp(sigma^2 * t) - 1)."""
    return (s0 ** 2) * math.exp(2.0 * mu * t) * (math.exp((sigma ** 2) * t) - 1.0)


# ---------------------------------------------------------------------------
# Formula 6.4: Itô's Lemma
# ---------------------------------------------------------------------------

def compute_ito_drift(
    df_dt: float,
    df_ds: float,
    d2f_ds2: float,
    s: float,
    mu: float,
    sigma: float,
) -> float:
    """Compute the drift component of df(S, t) via Itô's Lemma:

    Drift = df/dt + mu * S * (df/dS) + 0.5 * sigma^2 * S^2 * (d2f/dS2)
    Accounts for non-zero quadratic variation (dW_t)^2 = dt.
    """
    return df_dt + mu * s * df_ds + 0.5 * (sigma ** 2) * (s ** 2) * d2f_ds2


def compute_ito_diffusion(
    df_ds: float,
    s: float,
    sigma: float,
) -> float:
    """Compute the diffusion / volatility component of df(S, t) via Itô's Lemma:

    Diffusion = sigma * S * (df/dS)
    """
    return sigma * s * df_ds


def ito_log_price_drift(mu: float, sigma: float) -> float:
    """Compute the drift of log price ln(S) under Itô's Lemma: mu - 0.5 * sigma^2."""
    return mu - 0.5 * (sigma ** 2)


# ---------------------------------------------------------------------------
# Formula 6.5: Martingales & Gambler's Ruin
# ---------------------------------------------------------------------------

def compute_gamblers_ruin(k: int, n: int, p: float) -> float:
    """Calculate probability of Gambler's Ruin starting with capital k out of total n.

    Parameters:
        k: Starting fortune (0 <= k <= n).
        n: Target total capital.
        p: Win probability per bet (0.0 < p < 1.0).

    Returns:
        P(ruin) in [0.0, 1.0].
    """
    if k <= 0:
        return 1.0
    if k >= n:
        return 0.0
    if n <= 0:
        return 0.0

    if math.isclose(p, 0.5, abs_tol=1e-9):
        # Fair game martingale: P(ruin) = 1 - k / n
        return 1.0 - (float(k) / float(n))

    q = 1.0 - p
    ratio = q / p

    # Analytical formula: P(ruin) = ((q/p)^n - (q/p)^k) / ((q/p)^n - 1)
    try:
        num = (ratio ** n) - (ratio ** k)
        denom = (ratio ** n) - 1.0
        return max(0.0, min(1.0, num / denom))
    except OverflowError:
        return 1.0 if ratio > 1.0 else 0.0


def compute_infinite_horizon_ruin(initial_units: int, win_prob: float) -> float:
    """Calculate probability of eventual ruin against an infinite bankroll:

    P(ruin) = ((1 - p) / p)^N  for p > 0.5
    P(ruin) = 1.0              for p <= 0.5
    """
    if initial_units <= 0:
        return 1.0
    if win_prob <= 0.5:
        return 1.0
    if win_prob >= 1.0:
        return 0.0

    ratio = (1.0 - win_prob) / win_prob
    return max(0.0, min(1.0, ratio ** initial_units))


def is_martingale_property(
    expectations: Sequence[float],
    tolerance: float = 1e-6,
) -> bool:
    """Verify if a sequence satisfies the martingale conditional expectation property:

    E[X_{t+1} | F_t] == X_t.
    """
    if len(expectations) < 2:
        return True

    for i in range(1, len(expectations)):
        if abs(expectations[i] - expectations[i - 1]) > tolerance:
            return False
    return True
