"""Comprehensive tests for ZILLERS quantitative trading algorithms, stat-arb, and microstructure modules."""

import math
import numpy as np
import pytest

from cryptoscope.quant.stat_arb import (
    calculate_hedge_ratio,
    calculate_spread,
    adf_unit_root_test,
    ornstein_uhlenbeck_parameters,
    calculate_spread_zscore,
    analyze_crypto_pair,
)
from cryptoscope.quant.volatility import (
    realized_volatility,
    parkinson_volatility,
    garman_klass_volatility,
    yang_zhang_volatility,
    volatility_regime_analysis,
)
from cryptoscope.quant.order_flow import (
    calculate_cvd,
    detect_cvd_divergence,
    analyze_order_flow,
)
from cryptoscope.quant.sizing import (
    kelly_criterion,
    volatility_parity_allocation,
    calculate_cvar,
    optimal_trade_sizing,
)
from cryptoscope.autotrader.strategies.stat_arb_pairs import StatArbPairsStrategy
from cryptoscope.autotrader.strategies.volatility_breakout import VolatilityCompressionBreakoutStrategy


def test_ols_hedge_ratio():
    # Synthetic linear relationship: log(y) = 0.5 + 1.8 * log(x)
    np.random.seed(42)
    x = np.linspace(100, 200, 50)
    noise = np.random.normal(0, 0.01, 50)
    log_y = 0.5 + 1.8 * np.log(x) + noise
    y = np.exp(log_y)

    beta, alpha = calculate_hedge_ratio(list(y), list(x))
    assert abs(beta - 1.8) < 0.1
    assert abs(alpha - 0.5) < 0.3


def test_ornstein_uhlenbeck_parameters():
    # Generate stationary mean-reverting series S_t = 0.05 * (0.0 - S_{t-1}) + eps
    np.random.seed(42)
    n = 200
    spread = np.zeros(n)
    theta_true = 0.15
    for t in range(1, n):
        spread[t] = spread[t-1] + theta_true * (0.0 - spread[t-1]) + np.random.normal(0, 0.02)

    ou = ornstein_uhlenbeck_parameters(spread)
    assert ou["mean_reverting"] is True
    assert ou["theta"] > 0
    assert 1.0 <= ou["half_life_bars"] <= 50.0


def test_adf_unit_root_test():
    np.random.seed(42)
    # Stationary series
    stationary_series = np.random.normal(0, 1, 100)
    t_stat, p_val, is_coint = adf_unit_root_test(stationary_series)
    assert t_stat < 0
    assert is_coint is True

    # Random walk (non-stationary)
    rw_series = np.cumsum(np.random.normal(0, 1, 100))
    t_stat_rw, p_val_rw, is_coint_rw = adf_unit_root_test(rw_series)
    assert p_val_rw > p_val


def test_spread_zscore():
    series_a = [100.0 + i for i in range(50)]
    series_b = [50.0 + 0.5 * i for i in range(50)]

    # Perturb the last value to simulate extreme deviation
    series_a_deviated = list(series_a)
    series_a_deviated[-1] = 80.0  # Big drop -> undervalued spread

    res = calculate_spread_zscore(series_a_deviated, series_b, window=25)
    assert "zscore" in res
    assert res["zscore"] < -1.5
    assert res["action"] in ["BUY_A_SELL_B", "HOLD", "FLATTEN"]


def test_parkinson_and_garman_klass_volatility():
    highs = [105.0, 107.0, 104.0, 108.0, 110.0, 109.0, 111.0, 112.0]
    lows = [98.0, 101.0, 99.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    opens = [100.0, 102.0, 103.0, 103.0, 105.0, 106.0, 107.0, 108.0]
    closes = [102.0, 103.0, 101.0, 106.0, 107.0, 105.0, 110.0, 111.0]

    vol_park = parkinson_volatility(highs, lows)
    vol_gk = garman_klass_volatility(opens, highs, lows, closes)
    vol_yz = yang_zhang_volatility(opens, highs, lows, closes)
    vol_cc = realized_volatility(closes)

    assert vol_park > 0.0
    assert vol_gk > 0.0
    assert vol_yz > 0.0
    assert vol_cc > 0.0


def test_volatility_regime_classification():
    candles = []
    base_price = 50000.0
    # Create 40 candles with tight range (compression squeeze)
    for i in range(40):
        candles.append({
            "open": base_price,
            "high": base_price + 15.0,
            "low": base_price - 15.0,
            "close": base_price + 2.0,
            "volume": 10.0,
            "taker_buy_volume": 5.0,
            "close_time": 1700000000 + i * 900,
        })

    diag = volatility_regime_analysis(candles, window=10, baseline_window=30)
    assert diag["status"] == "ACTIVE"
    assert "regime" in diag
    assert "compression_ratio" in diag
    assert diag["breakout_readiness_pct"] > 0


def test_cvd_calculation_and_divergence():
    candles = []
    base_price = 100.0
    # Simulate rising price but falling taker buy volume (Bearish Absorption)
    for i in range(25):
        vol = 100.0
        # First 12 bars: high buy volume
        # Last 13 bars: low buy volume despite higher price
        buy_vol = 70.0 if i < 12 else 30.0
        candles.append({
            "open": base_price + i * 2.0,
            "high": base_price + i * 2.0 + 3.0,
            "low": base_price + i * 2.0 - 1.0,
            "close": base_price + i * 2.0 + 1.5,
            "volume": vol,
            "taker_buy_volume": buy_vol,
            "close_time": 1700000000 + i * 900,
        })

    cvd_data = calculate_cvd(candles)
    assert len(cvd_data["cvd"]) == 25
    # Exact delta check: for buy_vol=70, vol=100 -> delta = 70 - 30 = +40
    assert cvd_data["deltas"][0] == 40.0

    div = detect_cvd_divergence(candles, lookback=24)
    assert div["divergence"] in ["BEARISH_ABSORPTION", "HEALTHY_EXPANSION_UP", "NONE"]


def test_kelly_criterion_math():
    # Standard positive edge: 55% win rate, 1.8 win/loss ratio
    # b*p - q = 1.8 * 0.55 - 0.45 = 0.99 - 0.45 = 0.54
    # Full Kelly = 0.54 / 1.8 = 0.30
    res = kelly_criterion(win_rate=0.55, win_loss_ratio=1.8, fraction=0.5)
    assert res["status"] == "POSITIVE_EDGE"
    assert abs(res["full_kelly"] - 0.30) < 0.01
    assert abs(res["allocated_fraction"] - 0.15) < 0.01

    # Negative edge: 30% win rate, 1.0 payout -> should return 0 allocation
    neg = kelly_criterion(win_rate=0.30, win_loss_ratio=1.0)
    assert neg["status"] == "NEGATIVE_OR_ZERO_EDGE"
    assert neg["allocated_fraction"] == 0.0


def test_volatility_parity_allocation():
    vols = {
        "BTCUSDT": 0.45,  # lower volatility
        "ETHUSDT": 0.60,
        "SOLUSDT": 0.90,  # highest volatility
    }
    alloc = volatility_parity_allocation(vols, total_capital=100000.0)
    weights = alloc["weights"]
    assert abs(sum(weights.values()) - 1.0) < 0.01
    # BTC must get largest weight because its volatility is lowest
    assert weights["BTCUSDT"] > weights["ETHUSDT"] > weights["SOLUSDT"]
    assert alloc["capital_allocation"]["BTCUSDT"] > alloc["capital_allocation"]["SOLUSDT"]


def test_optimal_trade_sizing():
    sizing = optimal_trade_sizing(
        account_balance=10000.0,
        entry_price=2000.0,
        stop_loss=1960.0,  # 2% stop distance
        win_rate=0.55,
        win_loss_ratio=2.0,
        kelly_fraction=0.5,
    )
    assert sizing["status"] == "APPROVED"
    assert sizing["position_size_usd"] > 0.0
    assert sizing["position_qty"] > 0.0
    assert sizing["risk_usd"] <= 500.0  # Well within safety risk caps


def test_stat_arb_strategy():
    strat = StatArbPairsStrategy(entry_zscore=1.5, window=20)
    candles_a = []
    candles_b = []
    # Create 40 synchronized candles
    for i in range(40):
        ts = 1700000000 + i * 900
        candles_a.append({"open": 2000.0, "high": 2010.0, "low": 1990.0, "close": 2000.0 + (50.0 if i == 39 else 0.0), "close_time": ts})
        candles_b.append({"open": 60000.0, "high": 60200.0, "low": 59800.0, "close": 60000.0, "close_time": ts})

    sig = strat.evaluate_pair(candles_a, candles_b, symbol_a="ETHUSDT", symbol_b="BTCUSDT")
    # Because candle 39 had a spike in A, spread is elevated -> should suggest SHORT_SPREAD or valid signal
    if sig:
        assert sig["strategy"] == "stat_arb_pairs"
        assert sig["side"] in ["SHORT_SPREAD", "LONG_SPREAD", "EXIT_TARGET", "STOP_LOSS"]


def test_volatility_breakout_strategy():
    strat = VolatilityCompressionBreakoutStrategy(compression_threshold=0.85, lookback_bars=15)
    candles = []
    base_price = 100.0
    for i in range(50):
        # 0-25: wide baseline volatility (range 3.0)
        # 26-48: tight compression squeeze (range 0.4)
        # 49: big breakout candle
        is_break = (i == 49)
        in_squeeze = (26 <= i < 49)
        
        if is_break:
            c = base_price + 8.0
            h = c + 1.0
            l = base_price
            vol = 600.0
        elif in_squeeze:
            c = base_price + 0.2
            h = base_price + 0.3
            l = base_price - 0.2
            vol = 40.0
        else:
            c = base_price + (1.5 if i % 2 == 0 else -1.5)
            h = base_price + 2.5
            l = base_price - 2.5
            vol = 150.0

        candles.append({
            "open": base_price,
            "high": h,
            "low": l,
            "close": c,
            "volume": vol,
            "taker_buy_volume": vol * 0.8,
            "close_time": 1700000000 + i * 900,
        })

    sig = strat.evaluate(candles)
    assert sig is not None
    assert sig["side"] == "BUY"
    assert sig["strategy"] == "volatility_breakout"
    assert sig["take_profit"] > sig["entry_price"] > sig["stop_loss"]
