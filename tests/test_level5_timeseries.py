import math
import numpy as np
import pytest

from core.quant.levels.level5_timeseries import (
    compute_log_returns,
    compute_annualized_volatility,
    compute_autocorrelation,
    classify_autocorrelation_regime,
    compute_adf_stationarity,
    compute_cointegration_hedge_ratio,
    compute_half_life,
    compute_garch11_filter,
    forecast_garch11_next,
    estimate_garch11_parameters,
)


# ---------------------------------------------------------------------------
# Formula 5.1: Log Returns & Annualized Volatility
# ---------------------------------------------------------------------------

def test_log_returns_basic_and_additive():
    prices = [100.0, 105.0, 102.0, 110.0]
    returns = compute_log_returns(prices)
    assert len(returns) == 3
    assert pytest.approx(returns[0], 1e-6) == math.log(105.0 / 100.0)
    assert pytest.approx(returns[1], 1e-6) == math.log(102.0 / 105.0)
    assert pytest.approx(returns[2], 1e-6) == math.log(110.0 / 102.0)

    # Multi-period additive property: sum(r_t) == ln(P_T / P_0)
    assert pytest.approx(sum(returns), 1e-6) == math.log(110.0 / 100.0)


def test_log_returns_boundary_and_validation():
    # Empty or single price returns empty list
    assert compute_log_returns([]) == []
    assert compute_log_returns([100.0]) == []

    # Non-positive prices raise ValueError
    with pytest.raises(ValueError):
        compute_log_returns([100.0, 0.0])
    with pytest.raises(ValueError):
        compute_log_returns([-10.0, 100.0])


def test_annualized_volatility_from_scalar_and_series():
    # 1. From scalar bar vol
    bar_vol = 0.02  # 2% daily vol
    ann_vol_365 = compute_annualized_volatility(bar_vol, bars_per_year=365)
    assert pytest.approx(ann_vol_365, 1e-5) == 0.02 * math.sqrt(365)

    ann_vol_252 = compute_annualized_volatility(bar_vol, bars_per_year=252)
    assert pytest.approx(ann_vol_252, 1e-5) == 0.02 * math.sqrt(252)

    # 2. From return sequence
    np.random.seed(42)
    daily_returns = np.random.normal(0.0, 0.015, size=200).tolist()
    sample_std = float(np.std(daily_returns, ddof=1))
    computed_ann_vol = compute_annualized_volatility(daily_returns, bars_per_year=365)
    assert pytest.approx(computed_ann_vol, 1e-5) == sample_std * math.sqrt(365)

    # Edge cases
    assert compute_annualized_volatility([], bars_per_year=365) == 0.0
    assert compute_annualized_volatility([0.01], bars_per_year=365) == 0.0


# ---------------------------------------------------------------------------
# Formula 5.2: Autocorrelation
# ---------------------------------------------------------------------------

def test_autocorrelation_momentum_and_mean_reversion():
    # Momentum: AR(1) with phi = 0.7 -> strong positive lag-1 autocorrelation
    np.random.seed(42)
    mom_returns = [0.0]
    for _ in range(300):
        mom_returns.append(0.7 * mom_returns[-1] + np.random.normal(0, 0.01))
    ac_mom = compute_autocorrelation(mom_returns, lag=1)
    assert ac_mom > 0.5
    assert classify_autocorrelation_regime(ac_mom, threshold=0.05) == "momentum"

    # Mean reversion: strongly oscillating sequence -> negative autocorrelation at lag 1
    oscillating = [1.0 if i % 2 == 0 else -1.0 for i in range(100)]
    ac_rev = compute_autocorrelation(oscillating, lag=1)
    assert ac_rev < -0.8
    assert classify_autocorrelation_regime(ac_rev) == "mean_reverting"

    # Neutral / Random walk: i.i.d. noise
    np.random.seed(123)
    noise = np.random.normal(0, 1, 1000).tolist()
    ac_noise = compute_autocorrelation(noise, lag=1)
    assert abs(ac_noise) < 0.1
    assert classify_autocorrelation_regime(ac_noise, threshold=0.1) == "neutral"


def test_autocorrelation_boundaries():
    assert compute_autocorrelation([1.0, 2.0], lag=2) == 0.0
    assert compute_autocorrelation([5.0, 5.0, 5.0, 5.0], lag=1) == 0.0
    assert compute_autocorrelation([], lag=1) == 0.0


# ---------------------------------------------------------------------------
# Formula 5.3: Stationarity (ADF Test)
# ---------------------------------------------------------------------------

def test_adf_stationarity_mean_reverting_vs_random_walk():
    np.random.seed(42)
    # 1. Stationary series (AR(1) with phi = 0.2)
    stationary = [0.0]
    for _ in range(300):
        stationary.append(0.2 * stationary[-1] + np.random.normal(0, 1))

    t_stat, is_stat = compute_adf_stationarity(stationary, critical_value=-2.86)
    assert is_stat is True
    assert t_stat < -2.86

    # 2. Non-stationary random walk with drift
    random_walk = [100.0]
    for _ in range(300):
        random_walk.append(random_walk[-1] + 0.1 + np.random.normal(0, 1))

    t_stat_rw, is_stat_rw = compute_adf_stationarity(random_walk, critical_value=-2.86)
    assert is_stat_rw is False
    assert t_stat_rw > -2.86


def test_adf_boundaries():
    # Short series
    t_stat, is_stat = compute_adf_stationarity([1.0, 2.0, 3.0])
    assert t_stat == 0.0
    assert is_stat is False

    # Flat series
    t_stat, is_stat = compute_adf_stationarity([10.0] * 50)
    assert t_stat == 0.0
    assert is_stat is False


# ---------------------------------------------------------------------------
# Formula 5.4: Cointegration & Half-Life
# ---------------------------------------------------------------------------

def test_cointegration_hedge_ratio():
    np.random.seed(99)
    # Generate X as random walk, Y = 2.5 * X + 10.0 + noise
    x = np.cumsum(np.random.normal(0, 1, 200)) + 50.0
    noise = np.random.normal(0, 0.5, 200)
    y = 2.5 * x + 10.0 + noise

    beta, alpha, spread = compute_cointegration_hedge_ratio(y.tolist(), x.tolist())
    assert pytest.approx(beta, abs=0.1) == 2.5
    assert pytest.approx(alpha, abs=1.5) == 10.0
    assert len(spread) == 200


def test_half_life_mean_reversion():
    # Ornstein-Uhlenbeck: dS = -lambda * S * dt + sigma * dW
    # Discrete AR(1): S_t = (1 + lambda*dt) * S_{t-1} + noise
    # Let lambda = -0.1 => half-life = -ln(2) / -0.1 ≈ 6.93
    np.random.seed(77)
    target_lambda = -0.1
    phi = 1.0 + target_lambda  # 0.9
    ou_series = [10.0]
    for _ in range(500):
        ou_series.append(phi * ou_series[-1] + np.random.normal(0, 0.5))

    half_life = compute_half_life(ou_series)
    assert 4.0 <= half_life <= 10.0

    # Divergent or random walk has infinite half life
    rw = list(range(100))  # strictly increasing
    assert math.isinf(compute_half_life(rw))

    # Boundary: short series
    assert math.isinf(compute_half_life([1.0, 2.0, 3.0]))


# ---------------------------------------------------------------------------
# Formula 5.5: GARCH(1,1) Volatility
# ---------------------------------------------------------------------------

def test_garch11_filter_and_clustering():
    # Model parameters: sigma_t^2 = omega + alpha * eps_{t-1}^2 + beta * sigma_{t-1}^2
    omega = 0.00001
    alpha = 0.15
    beta = 0.80  # persistence = alpha + beta = 0.95 < 1
    unconditional_var = omega / (1.0 - alpha - beta)

    # 1. Constant zero returns -> variance converges to unconditional variance
    zero_returns = [0.0] * 100
    var_series = compute_garch11_filter(zero_returns, omega=omega, alpha=alpha, beta=beta, initial_sigma2=unconditional_var)
    assert len(var_series) == 100
    # Since returns are 0, sigma^2_t = omega + beta * sigma^2_{t-1} -> omega / (1 - beta)
    assert pytest.approx(var_series[-1], 1e-6) == omega / (1.0 - beta)

    # 2. Large shock spike and volatility clustering
    shocked_returns = [0.01] * 20 + [0.10] + [0.01] * 20
    var_shock = compute_garch11_filter(shocked_returns, omega=omega, alpha=alpha, beta=beta)
    # Variance right after the 0.10 shock (index 21) should be much higher than before shock
    assert var_shock[21] > var_shock[20] * 3.0
    # Volatility should slowly decay after the shock (clustering effect)
    assert var_shock[22] < var_shock[21]
    assert var_shock[30] < var_shock[22]


def test_forecast_garch11_next():
    omega = 0.0001
    alpha = 0.1
    beta = 0.85
    last_sigma2 = 0.002
    last_return = 0.05
    next_var = forecast_garch11_next(last_sigma2, last_return, omega, alpha, beta)
    expected = omega + alpha * (last_return ** 2) + beta * last_sigma2
    assert pytest.approx(next_var, 1e-7) == expected


def test_estimate_garch11_parameters():
    np.random.seed(42)
    # Generate synthetic GARCH(1,1) series
    true_omega = 0.00005
    true_alpha = 0.12
    true_beta = 0.82
    n = 600
    returns = [0.0]
    sigma2 = true_omega / (1.0 - true_alpha - true_beta)
    for _ in range(n):
        sigma2 = true_omega + true_alpha * (returns[-1] ** 2) + true_beta * sigma2
        r = np.random.normal(0, math.sqrt(sigma2))
        returns.append(r)

    params = estimate_garch11_parameters(returns)
    assert "omega" in params
    assert "alpha" in params
    assert "beta" in params
    assert "persistence" in params
    assert "long_run_vol" in params
    assert 0.0 < params["persistence"] < 1.0
    assert params["omega"] > 0.0
