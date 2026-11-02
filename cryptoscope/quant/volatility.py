"""High-Precision Quantitative Volatility Estimators and Regime Detection Engine.

Provides continuous intra-bar volatility estimators:
1. Parkinson (1980) High-Low Volatility (5x efficiency over close-to-close).
2. Garman-Klass (1980) OHLC Volatility (~8x efficiency).
3. Yang-Zhang (2000) Jump & Drift-Independent Volatility.
4. Volatility Regime Classification: Squeeze / Compression Detection, Normal Flow, and Explosive Expansion.
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional
import numpy as np


def realized_volatility(closes: List[float], annualize_factor: float = 365 * 24 * 4) -> float:
    """Standard close-to-close realized volatility: std(log returns) * sqrt(periods_per_year)."""
    if len(closes) < 3:
        return 0.0
    c = np.array(closes, dtype=float)
    c = np.maximum(c, 1e-8)
    returns = np.diff(np.log(c))
    if len(returns) < 2:
        return 0.0
    vol = float(np.std(returns, ddof=1)) * math.sqrt(annualize_factor)
    return round(vol, 6)


def parkinson_volatility(
    highs: List[float],
    lows: List[float],
    annualize_factor: float = 365 * 24 * 4,
) -> float:
    """Parkinson (1980) High-Low volatility estimator.
    
    sigma_P = sqrt( 1 / (4 * ln(2) * N) * sum( (ln(H_i / L_i))^2 ) ) * sqrt(T)
    """
    n = min(len(highs), len(lows))
    if n < 3:
        return 0.0

    h = np.maximum(np.array(highs[-n:], dtype=float), 1e-8)
    l = np.maximum(np.array(lows[-n:], dtype=float), 1e-8)

    # Ratio H/L must be >= 1.0
    hl_ratio = np.maximum(h / l, 1.0)
    log_hl = np.log(hl_ratio)

    factor = 1.0 / (4.0 * math.log(2.0) * n)
    variance = factor * np.sum(log_hl ** 2)

    vol = math.sqrt(max(0.0, variance)) * math.sqrt(annualize_factor)
    return round(vol, 6)


def garman_klass_volatility(
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    annualize_factor: float = 365 * 24 * 4,
) -> float:
    """Garman-Klass (1980) OHLC volatility estimator.
    
    sigma_GK = sqrt( 1/N * sum[ 0.5 * (ln(H/L))^2 - (2*ln(2) - 1) * (ln(C/O))^2 ] ) * sqrt(T)
    """
    n = min(len(opens), len(highs), len(lows), len(closes))
    if n < 3:
        return 0.0

    o = np.maximum(np.array(opens[-n:], dtype=float), 1e-8)
    h = np.maximum(np.array(highs[-n:], dtype=float), 1e-8)
    l = np.maximum(np.array(lows[-n:], dtype=float), 1e-8)
    c = np.maximum(np.array(closes[-n:], dtype=float), 1e-8)

    hl_ratio = np.maximum(h / l, 1.0)
    log_hl = np.log(hl_ratio)
    log_co = np.log(c / o)

    term1 = 0.5 * (log_hl ** 2)
    term2 = (2.0 * math.log(2.0) - 1.0) * (log_co ** 2)

    variance = (1.0 / n) * np.sum(term1 - term2)
    vol = math.sqrt(max(0.0, variance)) * math.sqrt(annualize_factor)
    return round(vol, 6)


def yang_zhang_volatility(
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    annualize_factor: float = 365 * 24 * 4,
) -> float:
    """Yang-Zhang (2000) drift-independent and overnight-jump robust volatility estimator.
    
    sigma_YZ = sqrt( sigma_o^2 + k * sigma_c^2 + (1 - k) * sigma_RS^2 ) * sqrt(T)
    """
    n = min(len(opens), len(highs), len(lows), len(closes))
    if n < 5:
        # Fallback to Garman-Klass if length is short
        return garman_klass_volatility(opens, highs, lows, closes, annualize_factor)

    o = np.maximum(np.array(opens[-n:], dtype=float), 1e-8)
    h = np.maximum(np.array(highs[-n:], dtype=float), 1e-8)
    l = np.maximum(np.array(lows[-n:], dtype=float), 1e-8)
    c = np.maximum(np.array(closes[-n:], dtype=float), 1e-8)

    # Overnight jump: log(O_t / C_{t-1})
    log_oc = np.log(o[1:] / c[:-1])
    var_o = float(np.var(log_oc, ddof=1)) if len(log_oc) > 1 else 0.0

    # Open-to-close: log(C_t / O_t)
    log_co = np.log(c[1:] / o[1:])
    var_c = float(np.var(log_co, ddof=1)) if len(log_co) > 1 else 0.0

    # Rogers-Satchell variance on intraday
    log_ho = np.log(h[1:] / o[1:])
    log_lo = np.log(l[1:] / o[1:])
    log_hc = np.log(h[1:] / c[1:])
    log_lc = np.log(l[1:] / c[1:])

    var_rs = float(np.mean(log_ho * log_hc + log_lo * log_lc))

    # Weighting constant k
    k = 0.34 / (1.34 + (n + 1) / max(n - 1, 1))

    total_var = var_o + k * var_c + (1.0 - k) * max(0.0, var_rs)
    vol = math.sqrt(max(0.0, total_var)) * math.sqrt(annualize_factor)
    return round(vol, 6)


def volatility_regime_analysis(
    candles: List[Dict[str, Any]],
    window: int = 20,
    baseline_window: int = 60,
    interval: str = "15m",
) -> Dict[str, Any]:
    """Classify current market volatility regime:
    - COMPRESSION_SQUEEZE: Volatility compressed well below baseline; imminent expansion.
    - NORMAL_FLOW: Volatility in typical historical range.
    - EXPANSION_VOLATILE: Strong volatility surge (trending impulse or capitulation).
    """
    if not candles or len(candles) < 10:
        return {
            "status": "INSUFFICIENT_DATA",
            "regime": "UNKNOWN",
            "compression_ratio": 1.0,
            "parkinson_vol": 0.0,
            "garman_klass_vol": 0.0,
            "yang_zhang_vol": 0.0,
            "realized_vol": 0.0,
            "breakout_readiness_pct": 50.0,
        }

    # Annualization factor calculation based on interval
    interval_factor_map = {
        "1m": 365 * 24 * 60,
        "5m": 365 * 24 * 12,
        "15m": 365 * 24 * 4,
        "1h": 365 * 24,
        "4h": 365 * 6,
        "1d": 365,
    }
    ann_factor = interval_factor_map.get(interval, 365 * 24 * 4)

    opens = [float(c["open"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    closes = [float(c["close"]) for c in candles]

    # Current window volatility
    curr_w = min(window, len(candles))
    vol_cc = realized_volatility(closes[-curr_w:], ann_factor)
    vol_park = parkinson_volatility(highs[-curr_w:], lows[-curr_w:], ann_factor)
    vol_gk = garman_klass_volatility(opens[-curr_w:], highs[-curr_w:], lows[-curr_w:], closes[-curr_w:], ann_factor)
    vol_yz = yang_zhang_volatility(opens[-curr_w:], highs[-curr_w:], lows[-curr_w:], closes[-curr_w:], ann_factor)

    # Baseline longer-term window
    base_w = min(baseline_window, len(candles))
    base_gk = garman_klass_volatility(opens[-base_w:], highs[-base_w:], lows[-base_w:], closes[-base_w:], ann_factor)

    # Compression ratio: current short-term GK vs longer-term baseline GK
    if base_gk > 1e-6:
        compression_ratio = round(vol_gk / base_gk, 4)
    else:
        compression_ratio = 1.0

    # ATR calculation for distance reference
    tr_list = []
    for i in range(1, len(candles)):
        c_prev = closes[i - 1]
        h_i = highs[i]
        l_i = lows[i]
        tr = max(h_i - l_i, abs(h_i - c_prev), abs(l_i - c_prev))
        tr_list.append(tr)
    atr = float(np.mean(tr_list[-14:])) if tr_list else (highs[-1] - lows[-1])
    atr_pct = round((atr / closes[-1]) * 100.0, 3) if closes[-1] > 0 else 0.0

    # Regime decision
    if compression_ratio < 0.65:
        regime = "COMPRESSION_SQUEEZE"
        state_label = "Squeeze: Breakout Imminent"
        breakout_readiness = round(min(98.0, 70.0 + (0.65 - compression_ratio) * 100.0), 1)
    elif compression_ratio > 1.45:
        regime = "EXPANSION_VOLATILE"
        state_label = "High Volatility Expansion"
        breakout_readiness = round(max(20.0, 100.0 - (compression_ratio - 1.45) * 40.0), 1)
    else:
        regime = "NORMAL_FLOW"
        state_label = "Steady Equilibrium"
        breakout_readiness = round(40.0 + (1.0 - abs(compression_ratio - 1.0)) * 20.0, 1)

    return {
        "status": "ACTIVE",
        "regime": regime,
        "state_label": state_label,
        "compression_ratio": compression_ratio,
        "breakout_readiness_pct": breakout_readiness,
        "estimators": {
            "parkinson_annualized": vol_park,
            "garman_klass_annualized": vol_gk,
            "yang_zhang_annualized": vol_yz,
            "realized_annualized": vol_cc,
        },
        "metrics": {
            "atr": round(atr, 4),
            "atr_pct": atr_pct,
            "current_close": closes[-1],
            "sample_bars": len(candles),
        },
    }
