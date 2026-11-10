import pytest
from core.quant.stage8_validate import (
    compute_sharpe_ratio,
    compute_sharpe_tstat,
    compute_multiple_testing_p_false,
    compute_best_of_n_noise_expected_sharpe,
    generate_walk_forward_windows,
    run_monte_carlo_drawdown,
)

def test_sharpe_ratio_annualized():
    # Mean return 0.001, sigma 0.01 -> daily SR = 0.1 -> annualized (365) = 0.1 * sqrt(365) ≈ 1.91
    # 252 days: 0.1 * sqrt(252) ≈ 1.587
    returns = [0.001 + (0.01 if i % 2 == 0 else -0.01) for i in range(100)]
    sr_252 = compute_sharpe_ratio(returns, rf=0.0, bars_per_year=252)
    assert sr_252 > 1.2

def test_sharpe_tstat():
    # SR 1.0 over 4 years: t = 1.0 * sqrt(4) = 2.0
    t = compute_sharpe_tstat(sharpe=1.0, years=4.0)
    assert pytest.approx(t, 1e-4) == 2.0

def test_multiple_testing_p_false():
    # 20 tests at alpha=0.05: 1 - (1-0.05)^20 = 1 - 0.95^20 ≈ 64.15%
    p_false = compute_multiple_testing_p_false(alpha=0.05, n_tests=20)
    assert pytest.approx(p_false, 1e-3) == 0.6415

def test_best_of_n_noise():
    # Expected max SR from pure noise for N trials: sigma_SR * sqrt(2 * ln(N))
    # 1,000 tries on sigma=0.5: 0.5 * sqrt(2 * ln(1000)) ≈ 0.5 * sqrt(13.8155) ≈ 1.858
    noise_sr = compute_best_of_n_noise_expected_sharpe(n_tests=1000, sigma_sharpe=0.5)
    assert pytest.approx(noise_sr, 0.05) == 1.858

def test_walk_forward_splits():
    splits = generate_walk_forward_windows(total_bars=1000, train_bars=600, test_bars=200)
    assert len(splits) == 2
    # Check that test windows roll forward
    train1, test1 = splits[0]
    train2, test2 = splits[1]
    assert test1.stop <= test2.start

def test_monte_carlo_drawdown_shuffling():
    # 100 trades with some wins and losses
    pnls = [100.0, -80.0, 120.0, -50.0, 90.0, -110.0] * 20
    mc_dd = run_monte_carlo_drawdown(pnls, iterations=500, confidence=0.95, seed=42)
    assert mc_dd > 0.0
    assert mc_dd < 1.0  # Fraction between 0 and 1
