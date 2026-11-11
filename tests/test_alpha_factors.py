import pytest
import math
from core.quant.factors.alpha158 import (
    compute_rolling_sma,
    compute_rolling_ema,
    compute_roc,
    compute_alpha158_features,
    compute_cross_sectional_zscore,
    compute_rolling_zscore,
    Alpha158FactorEngine,
)

def test_rolling_sma_and_ema():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0]
    sma3 = compute_rolling_sma(prices, window=3)
    # At index 0: 10.0
    # At index 1: (10 + 11) / 2 = 10.5
    # At index 2: (10 + 11 + 12) / 3 = 11.0
    # At index 3: (11 + 12 + 13) / 3 = 12.0
    # At index 4: (12 + 13 + 14) / 3 = 13.0
    assert sma3 == pytest.approx([10.0, 10.5, 11.0, 12.0, 13.0])

    ema = compute_rolling_ema(prices, span=3)
    assert len(ema) == len(prices)
    assert ema[-1] > ema[0]

def test_roc_momentum():
    prices = [100.0, 105.0, 110.0, 115.0, 120.0, 125.0]
    roc5 = compute_roc(prices, period=5)
    # At index 0..4, period not met: fallback 0.0
    # At index 5: (125 - 100) / 100 = 0.25 (25%)
    assert roc5[0] == 0.0
    assert roc5[5] == pytest.approx(0.25)

def test_alpha158_features_computation():
    # Generate 65 synthetic bars to verify all windows (5, 10, 20, 60)
    bars = []
    base_price = 100.0
    for i in range(70):
        p = base_price + i * 0.5 + (1.0 if i % 2 == 0 else -1.0)
        bars.append({
            "open": p - 0.2,
            "high": p + 1.0,
            "low": p - 1.0,
            "close": p,
            "volume": 1000.0 + (i * 10.0),
        })

    features = compute_alpha158_features(bars)

    expected_keys = [
        "ROC5", "ROC10", "ROC20", "ROC60",
        "MA5_RATIO", "MA10_RATIO", "MA20_RATIO", "MA60_RATIO",
        "SMA_RATIO_5_20", "EMA_RATIO_12_26",
        "PRICE_VOLATILITY_20",
        "VOL_MA5_RATIO", "VOL_MA20_RATIO", "VOL_CV20",
        "RANGE_BETA", "SHADOW_UPPER", "SHADOW_LOWER",
    ]
    for k in expected_keys:
        assert k in features, f"Missing key {k}"
        assert len(features[k]) == len(bars), f"Length mismatch for {k}"
        # No NaNs or infinities
        assert all(not math.isnan(x) and not math.isinf(x) for x in features[k]), f"NaN or Inf in {k}"

def test_cross_sectional_zscore():
    # 4 symbols with different factor values
    factors = {
        "BTCUSDT": 0.10,
        "ETHUSDT": 0.05,
        "SOLUSDT": -0.05,
        "BNBUSDT": 0.00,
    }
    z = compute_cross_sectional_zscore(factors)
    # Mean of [0.10, 0.05, -0.05, 0.00] is 0.025
    # Standard deviation > 0
    # Sum of z-scores should be approximately 0.0
    assert sum(z.values()) == pytest.approx(0.0, abs=1e-5)
    assert z["BTCUSDT"] > z["ETHUSDT"] > z["BNBUSDT"] > z["SOLUSDT"]

def test_cross_sectional_zscore_identical():
    factors = {"A": 5.0, "B": 5.0, "C": 5.0}
    z = compute_cross_sectional_zscore(factors)
    # If all values are identical, std is 0 -> fallback to 0.0 z-score
    assert z == {"A": 0.0, "B": 0.0, "C": 0.0}

def test_alpha158_engine_latest_features():
    engine = Alpha158FactorEngine()
    bars = [
        {"open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 500}
        for i in range(30)
    ]
    latest = engine.compute_latest_features(bars)
    assert isinstance(latest, dict)
    assert "ROC5" in latest
    assert "MA5_RATIO" in latest
    assert "VOL_MA5_RATIO" in latest
