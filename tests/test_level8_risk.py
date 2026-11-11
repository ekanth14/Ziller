import math
import pytest
from core.quant.levels.level8_risk import (
    compute_capm_beta,
    compute_capm_expected_return,
    compute_capm,
    compute_fama_french_3factor,
    compute_sharpe_ratio,
    compute_annualized_risk_adjusted_metrics,
    compute_discrete_kelly,
    compute_continuous_kelly,
    compute_parametric_var,
    compute_expected_shortfall,
    compute_historical_var_cvar,
    compute_max_drawdown,
)

# ---------------------------------------------------------
# Formula 8.1: CAPM
# ---------------------------------------------------------
def test_capm_beta_and_expected_return():
    # Asset with exact 1.5x beta to market
    # Market returns: [-0.02, 0.01, 0.03, -0.01, 0.04]
    mkt = [-0.02, 0.01, 0.03, -0.01, 0.04]
    asset = [1.5 * r for r in mkt]
    beta = compute_capm_beta(asset, mkt)
    assert pytest.approx(beta, 1e-5) == 1.5

    # Expected return via SML: E[R] = Rf + beta * (E[Rm] - Rf)
    # Rf = 0.03 (3%), Rm = 0.10 (10%), beta = 1.2 -> 0.03 + 1.2 * 0.07 = 0.114 (11.4%)
    exp_ret = compute_capm_expected_return(rf=0.03, beta=1.2, market_return=0.10)
    assert pytest.approx(exp_ret, 1e-5) == 0.114

def test_capm_full_decomposition():
    # Asset with beta 1.0 and positive alpha 0.02
    mkt = [0.01, -0.02, 0.03, 0.00, 0.04]
    asset = [r + 0.02 for r in mkt]
    res = compute_capm(asset, mkt, rf=0.0)
    assert pytest.approx(res["beta"], 1e-4) == 1.0
    assert pytest.approx(res["alpha"], 1e-4) == 0.02
    assert res["r_squared"] > 0.99

def test_capm_zero_variance_guard():
    # Flat market (zero variance)
    mkt = [0.01, 0.01, 0.01]
    asset = [0.02, 0.03, 0.01]
    res = compute_capm(asset, mkt, rf=0.0)
    assert res["beta"] == 0.0
    assert res["alpha"] == 0.0

# ---------------------------------------------------------
# Formula 8.2: Fama-French 3-Factor Model
# ---------------------------------------------------------
def test_fama_french_3factor_synthetic():
    # Y = alpha + 0.8 * MKT + 0.5 * SMB - 0.3 * HML
    n = 50
    mkt = [0.01 * (i % 7 - 3) for i in range(n)]
    smb = [0.005 * (i % 5 - 2) for i in range(n)]
    hml = [0.008 * (i % 3 - 1) for i in range(n)]
    alpha_true = 0.002
    asset = [
        alpha_true + 0.8 * mkt[i] + 0.5 * smb[i] - 0.3 * hml[i]
        for i in range(n)
    ]

    ff_res = compute_fama_french_3factor(asset, mkt, smb, hml, rf=0.0)
    assert pytest.approx(ff_res["alpha"], 1e-4) == alpha_true
    assert pytest.approx(ff_res["beta_mkt"], 1e-4) == 0.8
    assert pytest.approx(ff_res["beta_smb"], 1e-4) == 0.5
    assert pytest.approx(ff_res["beta_hml"], 1e-4) == -0.3
    assert pytest.approx(ff_res["r_squared"], 1e-4) == 1.0
    assert pytest.approx(ff_res["residual_variance"], 1e-6) == 0.0

def test_fama_french_insufficient_data():
    # Fewer than 4 data points
    res = compute_fama_french_3factor([0.01], [0.02], [0.01], [0.01])
    assert res["alpha"] == 0.0
    assert res["beta_mkt"] == 0.0
    assert res["r_squared"] == 0.0

# ---------------------------------------------------------
# Formula 8.3: Sharpe Ratio
# ---------------------------------------------------------
def test_sharpe_ratio_annualized():
    # Daily returns with mean 0.001 and std 0.01 -> daily SR = 0.1
    # Annualized (365 days): 0.1 * sqrt(365) ≈ 1.910497
    returns = [0.001 + (0.01 if i % 2 == 0 else -0.01) for i in range(100)]
    sr_365 = compute_sharpe_ratio(returns, rf=0.0, bars_per_year=365)
    sr_252 = compute_sharpe_ratio(returns, rf=0.0, bars_per_year=252)

    assert sr_365 > sr_252
    assert sr_365 > 1.8

    metrics = compute_annualized_risk_adjusted_metrics(returns, rf=0.0, bars_per_year=365)
    assert pytest.approx(metrics["sharpe_ratio"], 1e-4) == sr_365
    assert metrics["annualized_vol"] > 0.0

def test_sharpe_zero_vol_edge_case():
    assert compute_sharpe_ratio([]) == 0.0
    assert compute_sharpe_ratio([0.05]) == 0.0
    assert compute_sharpe_ratio([0.01, 0.01, 0.01]) == 0.0

# ---------------------------------------------------------
# Formula 8.4: Kelly Criterion (Discrete & Continuous)
# ---------------------------------------------------------
def test_discrete_kelly():
    # p = 0.6, b = 2.0 (2-to-1 payoff)
    # f* = (b*p - q) / b = (2.0 * 0.6 - 0.4) / 2.0 = (1.2 - 0.4) / 2.0 = 0.8 / 2.0 = 0.40 (40%)
    f_full = compute_discrete_kelly(win_prob=0.6, payoff_ratio=2.0, half_kelly=False)
    assert pytest.approx(f_full, 1e-4) == 0.40

    # Half-Kelly should be 20%
    f_half = compute_discrete_kelly(win_prob=0.6, payoff_ratio=2.0, half_kelly=True)
    assert pytest.approx(f_half, 1e-4) == 0.20

    # Negative edge should return 0.0
    f_neg = compute_discrete_kelly(win_prob=0.3, payoff_ratio=1.0)
    assert f_neg == 0.0

def test_continuous_kelly():
    # mu = 0.12 (12%), rf = 0.02 (2%), excess = 0.10, sigma = 0.20 (20%)
    # var = 0.04
    # f* = (mu - rf) / sigma^2 = 0.10 / 0.04 = 2.5
    f_cont = compute_continuous_kelly(mean_return=0.12, vol=0.20, rf=0.02, half_kelly=False, max_leverage=5.0)
    assert pytest.approx(f_cont, 1e-4) == 2.5

    # Half-Kelly continuous
    f_cont_half = compute_continuous_kelly(mean_return=0.12, vol=0.20, rf=0.02, half_kelly=True, max_leverage=5.0)
    assert pytest.approx(f_cont_half, 1e-4) == 1.25

    # Clamping by max_leverage
    f_clamped = compute_continuous_kelly(mean_return=0.50, vol=0.10, rf=0.0, max_leverage=2.0)
    assert f_clamped == 2.0

# ---------------------------------------------------------
# Formula 8.5: VaR, Expected Shortfall (CVaR) & Drawdown
# ---------------------------------------------------------
def test_parametric_var_and_cvar():
    # V = $1,000,000, 1-day vol = 0.02 (2%), 95% confidence
    # VaR_95 = 1.64485 * 0.02 * 1,000,000 = $32,897
    v = 1_000_000.0
    vol = 0.02
    var_95 = compute_parametric_var(portfolio_value=v, vol=vol, confidence=0.95)
    assert pytest.approx(var_95, 100.0) == 32897.0

    # Parametric ES: ES_95 = (sigma * phi(1.64485) / 0.05) * V
    # phi(1.64485) ≈ 0.103135 -> ES_95 ≈ (0.02 * 0.103135 / 0.05) * 1M = 41254.0
    cvar_95 = compute_expected_shortfall(portfolio_value=v, vol=vol, confidence=0.95)
    assert cvar_95 > var_95
    assert pytest.approx(cvar_95, 200.0) == 41254.0

def test_historical_var_cvar():
    # 100 observations: 95 normal returns (0.01), 5 tail losses (-0.05, -0.06, -0.07, -0.08, -0.10)
    returns = [0.01] * 95 + [-0.05, -0.06, -0.07, -0.08, -0.10]
    v = 100_000.0
    var_hist, cvar_hist = compute_historical_var_cvar(returns, portfolio_value=v, confidence=0.95)
    # 95th percentile worst loss is at least $5,000
    assert var_hist >= 5000.0
    # CVaR is average of losses exceeding or equal to VaR -> average of 5k, 6k, 7k, 8k, 10k = 7.2k
    assert cvar_hist >= var_hist
    assert pytest.approx(cvar_hist, 100.0) == 7200.0

def test_max_drawdown():
    series = [100.0, 150.0, 120.0, 90.0, 130.0, 80.0, 110.0]
    # Peak is 150, lowest trough after 150 is 80 -> DD = (150 - 80) / 150 = 70 / 150 ≈ 0.4667 (46.67%)
    mdd, peak, trough = compute_max_drawdown(series)
    assert pytest.approx(mdd, 1e-4) == 70.0 / 150.0
    assert peak == 150.0
    assert trough == 80.0
