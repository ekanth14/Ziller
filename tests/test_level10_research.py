import pytest
import numpy as np
from core.quant.levels.level10_research import (
    audit_backtest_biases,
    generate_walk_forward_windows,
    compute_walk_forward_efficiency,
    compute_deflated_sharpe_ratio,
    compute_classification_metrics,
    GaussianRegimeHMM,
    detect_regimes_hmm,
)

# ---------------------------------------------------------
# Formula 10.1: Backtest Biases Audit
# ---------------------------------------------------------
def test_backtest_biases_clean_case():
    # Healthy backtest: signals generated before execution, realistic fees and slippage
    sig_times = [100.0, 200.0, 300.0]
    exec_times = [101.0, 201.0, 301.0]
    audit = audit_backtest_biases(
        signal_timestamps=sig_times,
        execution_timestamps=exec_times,
        fee_rate=0.0005,
        slippage=0.0002,
        universe_has_delisted=True,
        num_trials=1,
    )
    assert audit["passed"] is True
    assert audit["lookahead_bias"] is False
    assert audit["zero_fee_warning"] is False
    assert audit["zero_slippage_warning"] is False
    assert audit["survivorship_bias"] is False
    assert len(audit["issues"]) == 0

def test_backtest_biases_lookahead_and_zero_fee_detected():
    # Signal timestamp is AFTER execution timestamp -> lookahead bias!
    sig_times = [105.0, 200.0]
    exec_times = [100.0, 201.0]
    audit = audit_backtest_biases(
        signal_timestamps=sig_times,
        execution_timestamps=exec_times,
        fee_rate=0.0,
        slippage=0.0,
        universe_has_delisted=False,
        num_trials=50,
    )
    assert audit["passed"] is False
    assert audit["lookahead_bias"] is True
    assert audit["zero_fee_warning"] is True
    assert audit["zero_slippage_warning"] is True
    assert audit["survivorship_bias"] is True
    assert audit["snooping_warning"] is True
    assert len(audit["issues"]) >= 4

# ---------------------------------------------------------
# Formula 10.2: Walk-Forward Validation
# ---------------------------------------------------------
def test_walk_forward_windows():
    # 1000 bars total, train 500 bars, test 200 bars, step 200 bars
    windows = generate_walk_forward_windows(
        total_bars=1000,
        train_bars=500,
        test_bars=200,
        step_bars=200,
        anchored=False,
    )
    assert len(windows) == 2

    train1, test1 = windows[0]
    train2, test2 = windows[1]

    # Verify zero-lookahead (train stops before or at test start)
    assert train1.stop <= test1.start
    assert train2.stop <= test2.start
    # Rolling forward
    assert train2.start > train1.start

def test_walk_forward_anchored_windows():
    # Anchored: train window expands from 0
    windows = generate_walk_forward_windows(
        total_bars=1000,
        train_bars=400,
        test_bars=200,
        step_bars=200,
        anchored=True,
    )
    assert len(windows) == 3
    assert windows[0][0].start == 0
    assert windows[1][0].start == 0
    assert windows[2][0].start == 0
    assert windows[1][0].stop > windows[0][0].stop

def test_walk_forward_efficiency():
    # In-sample Sharpe: 2.0, Out-of-sample Sharpe: 1.2
    # WFE = 1.2 / 2.0 = 0.60 (60% efficiency)
    wfe = compute_walk_forward_efficiency(
        in_sample_metrics=[2.0, 2.2, 1.8],
        out_of_sample_metrics=[1.2, 1.3, 1.1],
    )
    assert pytest.approx(wfe, 1e-4) == 0.60

# ---------------------------------------------------------
# Formula 10.3: Deflated Sharpe Ratio (DSR)
# ---------------------------------------------------------
def test_deflated_sharpe_ratio_single_trial():
    # Single trial with normal returns and SR = 2.0 over 250 bars: high significance
    dsr = compute_deflated_sharpe_ratio(
        estimated_sr=2.0,
        n_trials=1,
        sample_length=250,
        skewness=0.0,
        kurtosis=3.0,
    )
    assert dsr > 0.95

def test_deflated_sharpe_ratio_deflation_with_multiple_trials():
    # Same SR=1.5 tested across N=1 vs N=100 trials
    # When N=100, the expected maximum Sharpe under null hypothesis increases,
    # so DSR must drop significantly (deflation)
    dsr_1 = compute_deflated_sharpe_ratio(
        estimated_sr=1.5,
        n_trials=1,
        sample_length=200,
        var_sharpe=0.25,
    )
    dsr_100 = compute_deflated_sharpe_ratio(
        estimated_sr=1.5,
        n_trials=100,
        sample_length=200,
        var_sharpe=0.25,
    )
    assert dsr_100 < dsr_1

def test_deflated_sharpe_ratio_non_normal_tails():
    # Negative skewness and fat kurtosis reduces confidence compared to Gaussian
    dsr_normal = compute_deflated_sharpe_ratio(
        estimated_sr=1.2,
        n_trials=10,
        sample_length=150,
        skewness=0.0,
        kurtosis=3.0,
    )
    dsr_fat_tails = compute_deflated_sharpe_ratio(
        estimated_sr=1.2,
        n_trials=10,
        sample_length=150,
        skewness=-1.0,
        kurtosis=6.0,
    )
    assert dsr_fat_tails < dsr_normal

# ---------------------------------------------------------
# Formula 10.4: Classification Metrics
# ---------------------------------------------------------
def test_classification_metrics():
    # True: [1, 1, 1, 0, 0, 0]
    # Pred: [1, 1, 0, 0, 0, 1]
    # TP: 2 (indices 0, 1)
    # FN: 1 (index 2)
    # TN: 2 (indices 3, 4)
    # FP: 1 (index 5)
    # Precision = 2 / (2 + 1) = 2/3 ≈ 0.6667
    # Recall = 2 / (2 + 1) = 2/3 ≈ 0.6667
    # F1 = 2/3 ≈ 0.6667
    # Accuracy = 4 / 6 = 2/3 ≈ 0.6667
    y_true = [1, 1, 1, 0, 0, 0]
    y_pred = [1, 1, 0, 0, 0, 1]
    metrics = compute_classification_metrics(y_true, y_pred)
    assert metrics["tp"] == 2
    assert metrics["fp"] == 1
    assert metrics["tn"] == 2
    assert metrics["fn"] == 1
    assert pytest.approx(metrics["precision"], 1e-4) == 2.0 / 3.0
    assert pytest.approx(metrics["recall"], 1e-4) == 2.0 / 3.0
    assert pytest.approx(metrics["f1"], 1e-4) == 2.0 / 3.0
    assert pytest.approx(metrics["accuracy"], 1e-4) == 4.0 / 6.0

def test_classification_metrics_edge_cases():
    # All negative predictions
    metrics = compute_classification_metrics([1, 1], [0, 0])
    assert metrics["tp"] == 0
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["f1"] == 0.0

# ---------------------------------------------------------
# Formula 10.5: Regime Models (HMM / Volatility Clusters)
# ---------------------------------------------------------
def test_regime_model_hmm():
    np.random.seed(42)
    # Regime 0: Low vol (std = 0.005)
    r0 = np.random.normal(0.001, 0.005, 100)
    # Regime 1: High vol (std = 0.030)
    r1 = np.random.normal(-0.002, 0.030, 100)
    # Combined series: low vol period followed by high vol period
    series = np.concatenate([r0, r1]).tolist()

    res = detect_regimes_hmm(series, n_states=2, max_iter=25)
    assert "states" in res
    assert len(res["states"]) == 200
    assert "state_stds" in res
    assert len(res["state_stds"]) == 2
    # Ensure one state has lower vol than the other
    min_std = min(res["state_stds"])
    max_std = max(res["state_stds"])
    assert max_std > 2.0 * min_std

    # Check that early period has different dominant state than late period
    early_states = res["states"][:100]
    late_states = res["states"][100:]
    assert sum(early_states) != sum(late_states)

def test_regime_model_insufficient_data():
    res = detect_regimes_hmm([0.01, 0.02], n_states=2)
    assert len(res["states"]) == 2
    assert res["current_regime"] in [0, 1]
