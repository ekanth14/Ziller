import math
import numpy as np
import pytest

from core.quant.levels.level6_stoch import (
    simulate_random_walk,
    compute_random_walk_variance,
    compute_diffusion_scaling,
    simulate_brownian_motion,
    simulate_gbm_path,
    gbm_expected_value,
    gbm_variance,
    compute_ito_drift,
    compute_ito_diffusion,
    ito_log_price_drift,
    compute_gamblers_ruin,
    compute_infinite_horizon_ruin,
    is_martingale_property,
)


# ---------------------------------------------------------------------------
# Formula 6.1: Random Walk
# ---------------------------------------------------------------------------

def test_random_walk_simulation_and_variance():
    steps = 100
    x0 = 10.0
    # Deterministic seed test
    path = simulate_random_walk(steps=steps, x0=x0, step_size=1.0, p_up=0.5, seed=42)
    assert len(path) == steps + 1
    assert path[0] == x0

    # Variance scaling: Var(X_t) = t * sigma^2
    var_100 = compute_random_walk_variance(time_steps=100, sigma=2.0, dt=1.0)
    assert pytest.approx(var_100, 1e-6) == 100 * (2.0 ** 2)

    # Diffusion scaling: sigma * sqrt(t)
    diff = compute_diffusion_scaling(sigma=2.0, time_t=25.0)
    assert pytest.approx(diff, 1e-6) == 2.0 * math.sqrt(25.0)


def test_random_walk_boundaries():
    assert simulate_random_walk(steps=0, x0=5.0) == [5.0]
    with pytest.raises(ValueError):
        simulate_random_walk(steps=-5)
    assert compute_random_walk_variance(time_steps=0, sigma=1.0) == 0.0
    assert compute_diffusion_scaling(sigma=1.0, time_t=0.0) == 0.0


# ---------------------------------------------------------------------------
# Formula 6.2: Brownian Motion (Wiener Process)
# ---------------------------------------------------------------------------

def test_brownian_motion_properties():
    t_end = 2.0
    n_steps = 2000
    times, w = simulate_brownian_motion(t=t_end, n_steps=n_steps, seed=123)
    assert len(times) == n_steps + 1
    assert len(w) == n_steps + 1
    assert times[0] == 0.0
    assert pytest.approx(times[-1], 1e-6) == t_end
    # W(0) == 0
    assert w[0] == 0.0

    # Test ensemble properties over multiple paths
    terminal_values = []
    for s in range(500):
        _, path = simulate_brownian_motion(t=1.0, n_steps=50, seed=s)
        terminal_values.append(path[-1])

    mean_term = sum(terminal_values) / len(terminal_values)
    var_term = sum((x - mean_term) ** 2 for x in terminal_values) / (len(terminal_values) - 1)
    # E[W(1)] = 0, Var(W(1)) = 1
    assert abs(mean_term) < 0.15
    assert pytest.approx(var_term, abs=0.20) == 1.0


def test_brownian_motion_boundaries():
    times, w = simulate_brownian_motion(t=0.0, n_steps=10)
    assert times == [0.0]
    assert w == [0.0]

    with pytest.raises(ValueError):
        simulate_brownian_motion(t=-1.0, n_steps=10)
    with pytest.raises(ValueError):
        simulate_brownian_motion(t=1.0, n_steps=0)


# ---------------------------------------------------------------------------
# Formula 6.3: Geometric Brownian Motion (GBM)
# ---------------------------------------------------------------------------

def test_gbm_positive_prices_and_moments():
    s0 = 100.0
    mu = 0.05
    sigma = 0.20
    t = 1.0
    n_steps = 100

    times, prices = simulate_gbm_path(s0=s0, mu=mu, sigma=sigma, t=t, n_steps=n_steps, seed=42)
    assert len(prices) == n_steps + 1
    assert prices[0] == s0
    # Crucial property: prices must be strictly positive (> 0)
    assert all(p > 0.0 for p in prices)

    # Analytical moments
    exp_val = gbm_expected_value(s0=s0, mu=mu, t=t)
    assert pytest.approx(exp_val, 1e-5) == s0 * math.exp(mu * t)

    theo_var = gbm_variance(s0=s0, mu=mu, sigma=sigma, t=t)
    expected_var = (s0 ** 2) * math.exp(2 * mu * t) * (math.exp(sigma ** 2 * t) - 1.0)
    assert pytest.approx(theo_var, 1e-4) == expected_var


def test_gbm_prevent_negative_initial_price():
    with pytest.raises(ValueError, match="Initial price s0 must be strictly positive"):
        simulate_gbm_path(s0=-50.0, mu=0.05, sigma=0.2, t=1.0, n_steps=10)

    with pytest.raises(ValueError, match="Initial price s0 must be strictly positive"):
        simulate_gbm_path(s0=0.0, mu=0.05, sigma=0.2, t=1.0, n_steps=10)


# ---------------------------------------------------------------------------
# Formula 6.4: Itô's Lemma
# ---------------------------------------------------------------------------

def test_ito_lemma_log_price_and_polynomial():
    # For f(S) = ln(S):
    # df/dt = 0, df/dS = 1/S, d2f/dS2 = -1/S^2
    # drift = 0 + mu * S * (1/S) + 0.5 * sigma^2 * S^2 * (-1/S^2) = mu - 0.5 * sigma^2
    # diffusion = sigma * S * (1/S) = sigma
    s = 100.0
    mu = 0.08
    sigma = 0.25

    drift = compute_ito_drift(df_dt=0.0, df_ds=1.0 / s, d2f_ds2=-1.0 / (s ** 2), s=s, mu=mu, sigma=sigma)
    assert pytest.approx(drift, 1e-7) == mu - 0.5 * (sigma ** 2)

    diffusion = compute_ito_diffusion(df_ds=1.0 / s, s=s, sigma=sigma)
    assert pytest.approx(diffusion, 1e-7) == sigma

    # Helper function verification
    assert pytest.approx(ito_log_price_drift(mu=mu, sigma=sigma), 1e-7) == mu - 0.5 * (sigma ** 2)

    # For f(S) = S^2:
    # df/dt = 0, df/dS = 2S, d2f/dS2 = 2
    # drift = mu * S * 2S + 0.5 * sigma^2 * S^2 * 2 = (2*mu + sigma^2) * S^2
    drift_sq = compute_ito_drift(df_dt=0.0, df_ds=2 * s, d2f_ds2=2.0, s=s, mu=mu, sigma=sigma)
    assert pytest.approx(drift_sq, 1e-5) == (2 * mu + sigma ** 2) * (s ** 2)


# ---------------------------------------------------------------------------
# Formula 6.5: Martingales & Gambler's Ruin
# ---------------------------------------------------------------------------

def test_gamblers_ruin_finite():
    # Fair coin (p = 0.5): P(ruin) = 1 - k / n
    # Starting with 40 out of 100 capital
    p_ruin_fair = compute_gamblers_ruin(k=40, n=100, p=0.5)
    assert pytest.approx(p_ruin_fair, 1e-5) == 0.60

    # Unfavorable coin (p = 0.45): higher ruin probability
    p_ruin_bad = compute_gamblers_ruin(k=40, n=100, p=0.45)
    assert p_ruin_bad > 0.60

    # Favorable coin (p = 0.55): lower ruin probability
    p_ruin_good = compute_gamblers_ruin(k=40, n=100, p=0.55)
    assert p_ruin_good < 0.60

    # Boundary conditions
    assert compute_gamblers_ruin(k=0, n=100, p=0.5) == 1.0  # Already broke
    assert compute_gamblers_ruin(k=100, n=100, p=0.5) == 0.0  # Already reached goal


def test_infinite_horizon_ruin():
    # Formula: P(ruin) = ((1 - p) / p)^N for p > 0.5
    # If p = 0.6, q = 0.4, ratio = 0.4 / 0.6 = 2/3
    # N = 3 units: (2/3)^3 = 8 / 27 ≈ 0.2963
    p_ruin = compute_infinite_horizon_ruin(initial_units=3, win_prob=0.6)
    assert pytest.approx(p_ruin, 1e-4) == (2.0 / 3.0) ** 3

    # If game is fair or unfavorable (p <= 0.5), ruin is certain against infinite bank
    assert compute_infinite_horizon_ruin(initial_units=10, win_prob=0.5) == 1.0
    assert compute_infinite_horizon_ruin(initial_units=10, win_prob=0.45) == 1.0


def test_martingale_property():
    # Constant conditional expectation sequence
    martingale_seq = [100.0, 100.0, 100.0, 100.0]
    assert is_martingale_property(martingale_seq) is True

    # Drifting sequence
    submartingale_seq = [100.0, 101.0, 102.0, 103.0]
    assert is_martingale_property(submartingale_seq) is False
