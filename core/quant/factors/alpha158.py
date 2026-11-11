"""Alpha158 Factor Engine.

Inspired by Microsoft Qlib's Alpha158 institutional feature set.
Computes price momentum, moving average cross ratios, rolling volume volatility,
and cross-sectional factor z-scores with strict zero-lookahead safety.
"""

import math
from typing import Any, Mapping, Sequence
import numpy as np


def compute_rolling_sma(values: Sequence[float], window: int) -> list[float]:
    """Calculate rolling simple moving average with expanding window at start.

    Zero-lookahead: At index t, uses values in [max(0, t - window + 1) .. t].
    """
    if not values:
        return []
    w = max(1, int(window))
    result: list[float] = []
    running_sum = 0.0
    for i, v in enumerate(values):
        running_sum += float(v)
        if i >= w:
            running_sum -= float(values[i - w])
            result.append(running_sum / w)
        else:
            result.append(running_sum / (i + 1))
    return result


def compute_rolling_ema(values: Sequence[float], span: int) -> list[float]:
    """Calculate exponential moving average (EMA) with span parameter."""
    if not values:
        return []
    s = max(1, int(span))
    alpha = 2.0 / (s + 1.0)
    result: list[float] = []
    ema = float(values[0])
    result.append(ema)
    for v in values[1:]:
        ema = alpha * float(v) + (1.0 - alpha) * ema
        result.append(ema)
    return result


def compute_roc(values: Sequence[float], period: int) -> list[float]:
    """Rate of Change (momentum) over given period: (P_t / P_{t - period}) - 1."""
    if not values:
        return []
    p = max(1, int(period))
    result: list[float] = []
    for i in range(len(values)):
        if i < p:
            result.append(0.0)
        else:
            past = float(values[i - p])
            curr = float(values[i])
            if abs(past) < 1e-12:
                result.append(0.0)
            else:
                result.append((curr - past) / past)
    return result


def compute_rolling_std(values: Sequence[float], window: int) -> list[float]:
    """Calculate rolling standard deviation with expanding window at start."""
    if not values:
        return []
    w = max(2, int(window))
    result: list[float] = []
    for i in range(len(values)):
        start = max(0, i - w + 1)
        sub = [float(x) for x in values[start : i + 1]]
        if len(sub) < 2:
            result.append(0.0)
        else:
            mean = sum(sub) / len(sub)
            var = sum((x - mean) ** 2 for x in sub) / (len(sub) - 1)
            result.append(math.sqrt(max(0.0, var)))
    return result


def compute_alpha158_features(candles: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    """Compute rolling Alpha158-style factors across OHLCV candles.

    Includes:
    - ROC5, ROC10, ROC20, ROC60 (price momentum)
    - MA5_RATIO, MA10_RATIO, MA20_RATIO, MA60_RATIO (price to moving average)
    - SMA_RATIO_5_20, EMA_RATIO_12_26 (moving average crossovers)
    - PRICE_VOLATILITY_20 (rolling return volatility)
    - VOL_MA5_RATIO, VOL_MA20_RATIO, VOL_CV20 (volume spikes and volatility)
    - RANGE_BETA, SHADOW_UPPER, SHADOW_LOWER (candle geometry)
    """
    if not candles:
        return {}

    opens = [float(c.get("open", 0.0)) for c in candles]
    highs = [float(c.get("high", 0.0)) for c in candles]
    lows = [float(c.get("low", 0.0)) for c in candles]
    closes = [float(c.get("close", 0.0)) for c in candles]
    volumes = [float(c.get("volume", 0.0)) for c in candles]
    n = len(candles)

    # Momentum ROC
    roc5 = compute_roc(closes, 5)
    roc10 = compute_roc(closes, 10)
    roc20 = compute_roc(closes, 20)
    roc60 = compute_roc(closes, 60)

    # Simple Moving Averages
    sma5 = compute_rolling_sma(closes, 5)
    sma10 = compute_rolling_sma(closes, 10)
    sma20 = compute_rolling_sma(closes, 20)
    sma60 = compute_rolling_sma(closes, 60)

    # Exponential Moving Averages
    ema12 = compute_rolling_ema(closes, 12)
    ema26 = compute_rolling_ema(closes, 26)

    # MA Ratios
    ma5_ratio = [closes[i] / (sma5[i] if sma5[i] > 1e-12 else 1.0) for i in range(n)]
    ma10_ratio = [closes[i] / (sma10[i] if sma10[i] > 1e-12 else 1.0) for i in range(n)]
    ma20_ratio = [closes[i] / (sma20[i] if sma20[i] > 1e-12 else 1.0) for i in range(n)]
    ma60_ratio = [closes[i] / (sma60[i] if sma60[i] > 1e-12 else 1.0) for i in range(n)]
    sma_ratio_5_20 = [sma5[i] / (sma20[i] if sma20[i] > 1e-12 else 1.0) for i in range(n)]
    ema_ratio_12_26 = [ema12[i] / (ema26[i] if ema26[i] > 1e-12 else 1.0) for i in range(n)]

    # Returns & Return Volatility
    returns: list[float] = [0.0]
    for i in range(1, n):
        prev = closes[i - 1]
        returns.append((closes[i] - prev) / prev if prev > 1e-12 else 0.0)
    price_vol_20 = compute_rolling_std(returns, 20)

    # Volume Ratios & Volatility
    vol_sma5 = compute_rolling_sma(volumes, 5)
    vol_sma20 = compute_rolling_sma(volumes, 20)
    vol_ma5_ratio = [volumes[i] / (vol_sma5[i] if vol_sma5[i] > 1e-12 else 1.0) for i in range(n)]
    vol_ma20_ratio = [volumes[i] / (vol_sma20[i] if vol_sma20[i] > 1e-12 else 1.0) for i in range(n)]
    vol_std20 = compute_rolling_std(volumes, 20)
    vol_cv20 = [vol_std20[i] / (vol_sma20[i] if vol_sma20[i] > 1e-12 else 1.0) for i in range(n)]

    # Candle Geometry
    range_beta: list[float] = []
    shadow_upper: list[float] = []
    shadow_lower: list[float] = []
    for i in range(n):
        c = closes[i] if closes[i] > 1e-12 else 1.0
        h = highs[i]
        l = lows[i]
        o = opens[i]

        range_beta.append(max(0.0, h - l) / c)
        upper_body = max(o, closes[i])
        lower_body = min(o, closes[i])
        shadow_upper.append(max(0.0, h - upper_body) / c)
        shadow_lower.append(max(0.0, lower_body - l) / c)

    return {
        "ROC5": roc5,
        "ROC10": roc10,
        "ROC20": roc20,
        "ROC60": roc60,
        "MA5_RATIO": ma5_ratio,
        "MA10_RATIO": ma10_ratio,
        "MA20_RATIO": ma20_ratio,
        "MA60_RATIO": ma60_ratio,
        "SMA_RATIO_5_20": sma_ratio_5_20,
        "EMA_RATIO_12_26": ema_ratio_12_26,
        "PRICE_VOLATILITY_20": price_vol_20,
        "VOL_MA5_RATIO": vol_ma5_ratio,
        "VOL_MA20_RATIO": vol_ma20_ratio,
        "VOL_CV20": vol_cv20,
        "RANGE_BETA": range_beta,
        "SHADOW_UPPER": shadow_upper,
        "SHADOW_LOWER": shadow_lower,
    }


def compute_cross_sectional_zscore(factor_values: Mapping[str, float]) -> dict[str, float]:
    """Compute cross-sectional Z-score normalization for a factor across multiple assets.

    Z = (X_i - mu) / sigma
    If sigma == 0, returns 0.0 for all assets.
    """
    if not factor_values:
        return {}
    keys = list(factor_values.keys())
    vals = [float(factor_values[k]) for k in keys]
    n = len(vals)
    if n < 2:
        return {k: 0.0 for k in keys}

    mean = sum(vals) / n
    variance = sum((x - mean) ** 2 for x in vals) / (n - 1)
    std = math.sqrt(variance)

    if std < 1e-12:
        return {k: 0.0 for k in keys}

    return {k: (float(factor_values[k]) - mean) / std for k in keys}


def compute_rolling_zscore(values: Sequence[float], window: int = 20) -> list[float]:
    """Compute rolling time-series Z-score for a single asset series."""
    if not values:
        return []
    w = max(2, int(window))
    result: list[float] = []
    for i in range(len(values)):
        start = max(0, i - w + 1)
        sub = [float(x) for x in values[start : i + 1]]
        if len(sub) < 2:
            result.append(0.0)
            continue
        mean = sum(sub) / len(sub)
        var = sum((x - mean) ** 2 for x in sub) / (len(sub) - 1)
        std = math.sqrt(max(0.0, var))
        if std < 1e-12:
            result.append(0.0)
        else:
            result.append((float(values[i]) - mean) / std)
    return result


class Alpha158FactorEngine:
    """Institutional Factor Engine producing Qlib-compatible alpha features."""

    def compute_features(self, candles: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
        return compute_alpha158_features(candles)

    def compute_latest_features(self, candles: Sequence[Mapping[str, Any]]) -> dict[str, float]:
        features = compute_alpha158_features(candles)
        latest: dict[str, float] = {}
        for k, v in features.items():
            latest[k] = v[-1] if v else 0.0
        return latest
