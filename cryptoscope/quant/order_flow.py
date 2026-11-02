"""Order Flow Imbalance, Cumulative Volume Delta (CVD), and Absorption Divergence Engine.

Analyzes trade execution microstructure from Binance candle feeds:
- Exact volume delta from `taker_buy_volume` and `total_volume`.
- Cumulative Volume Delta (CVD) trajectory and slope.
- Bullish/Bearish Delta Divergence detection (institutional absorption vs exhaustion).
- Order Flow Imbalance (OFI) buy/sell pressure ratio.
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional
import numpy as np


def calculate_cvd(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate per-candle delta and Cumulative Volume Delta (CVD).
    
    Delta = taker_buy_volume - (total_volume - taker_buy_volume)
          = 2 * taker_buy_volume - total_volume
    """
    if not candles:
        return {"deltas": [], "cvd": [], "total_buy_vol": 0.0, "total_sell_vol": 0.0, "total_vol": 0.0}

    deltas = []
    cvd_series = []
    running_cvd = 0.0
    tot_buy = 0.0
    tot_sell = 0.0
    tot_vol = 0.0

    for c in candles:
        vol = float(c.get("volume", 0.0))
        buy_vol = float(c.get("taker_buy_volume", vol * 0.5))
        sell_vol = max(0.0, vol - buy_vol)
        delta = buy_vol - sell_vol

        running_cvd += delta
        deltas.append(round(delta, 4))
        cvd_series.append(round(running_cvd, 4))

        tot_buy += buy_vol
        tot_sell += sell_vol
        tot_vol += vol

    return {
        "deltas": deltas,
        "cvd": cvd_series,
        "total_buy_vol": round(tot_buy, 4),
        "total_sell_vol": round(tot_sell, 4),
        "total_vol": round(tot_vol, 4),
        "buy_ratio": round(tot_buy / max(tot_vol, 1e-6), 4),
    }


def detect_cvd_divergence(
    candles: List[Dict[str, Any]],
    lookback: int = 24,
) -> Dict[str, Any]:
    """Detect Order Flow Divergences over recent lookback bars:
    - BEARISH_ABSORPTION: Price pushed higher, but CVD printed a lower high (sellers absorbing market buys).
    - BULLISH_ABSORPTION: Price made a lower low, but CVD made a higher low (buyers soaking market sells).
    - CONCURRENT_BULLISH: Both Price and CVD making higher highs (strong aggressive momentum).
    - CONCURRENT_BEARISH: Both Price and CVD making lower lows (strong aggressive dumping).
    """
    if not candles or len(candles) < 10:
        return {
            "divergence": "NONE",
            "state": "INSUFFICIENT_DATA",
            "confidence": 0.0,
            "cvd_slope": 0.0,
            "details": "Insufficient candle depth for order flow divergence",
        }

    sub = candles[-lookback:]
    closes = np.array([float(c["close"]) for c in sub])
    cvd_data = calculate_cvd(sub)
    cvd = np.array(cvd_data["cvd"])

    n = len(closes)
    mid = n // 2

    # Compare first half vs second half extremes
    first_half_close_max = np.max(closes[:mid])
    first_half_close_min = np.min(closes[:mid])
    second_half_close_max = np.max(closes[mid:])
    second_half_close_min = np.min(closes[mid:])

    first_half_cvd_max = np.max(cvd[:mid])
    first_half_cvd_min = np.min(cvd[:mid])
    second_half_cvd_max = np.max(cvd[mid:])
    second_half_cvd_min = np.min(cvd[mid:])

    # Linear trend slope of CVD
    x = np.arange(n)
    if np.var(x) > 0:
        cvd_slope = float(np.polyfit(x, cvd, 1)[0])
        price_slope = float(np.polyfit(x, closes, 1)[0])
    else:
        cvd_slope = 0.0
        price_slope = 0.0

    divergence = "NONE"
    state = "NEUTRAL"
    confidence = 0.5
    details = "Price and order flow moving in standard tandem"

    # Bearish Divergence: Higher high in price, lower high in CVD
    if second_half_close_max > first_half_close_max and second_half_cvd_max < first_half_cvd_max:
        divergence = "BEARISH_ABSORPTION"
        state = "EXHAUSTION_SELL_ALERT"
        confidence = 0.82
        details = "Price reached a higher peak, but Cumulative Volume Delta made a lower high. Market buying absorbed by passive limit sellers."

    # Bullish Divergence: Lower low in price, higher low in CVD
    elif second_half_close_min < first_half_close_min and second_half_cvd_min > first_half_cvd_min:
        divergence = "BULLISH_ABSORPTION"
        state = "ACCUMULATION_BUY_ALERT"
        confidence = 0.85
        details = "Price dipped to a lower low, but Cumulative Volume Delta formed a higher floor. Aggressive market selling absorbed by institutional bids."

    # Strong Trend confirmation
    elif price_slope > 0 and cvd_slope > 0:
        divergence = "CONCURRENT_BULLISH"
        state = "HEALTHY_EXPANSION_UP"
        confidence = 0.75
        details = "Both price and aggressive taker buy delta expanding synchronously."
    elif price_slope < 0 and cvd_slope < 0:
        divergence = "CONCURRENT_BEARISH"
        state = "HEALTHY_EXPANSION_DOWN"
        confidence = 0.75
        details = "Both price and aggressive taker sell delta descending synchronously."

    return {
        "divergence": divergence,
        "state": state,
        "confidence": confidence,
        "cvd_slope": round(cvd_slope, 4),
        "price_slope": round(price_slope, 4),
        "recent_delta": cvd_data["deltas"][-1] if cvd_data["deltas"] else 0.0,
        "buy_ratio": cvd_data["buy_ratio"],
        "details": details,
    }


def analyze_order_flow(candles: List[Dict[str, Any]], lookback: int = 40) -> Dict[str, Any]:
    """Produce comprehensive Order Flow microstructural diagnostic."""
    if not candles:
        return {"status": "EMPTY"}

    sub = candles[-lookback:]
    cvd_data = calculate_cvd(sub)
    div_data = detect_cvd_divergence(sub, lookback=min(lookback, len(sub)))

    recent_deltas = cvd_data["deltas"][-10:]
    pos_deltas = sum(1 for d in recent_deltas if d > 0)
    neg_deltas = len(recent_deltas) - pos_deltas

    dominance = "BUYERS" if cvd_data["buy_ratio"] > 0.52 else "SELLERS" if cvd_data["buy_ratio"] < 0.48 else "BALANCED"

    return {
        "status": "OK",
        "sample_bars": len(sub),
        "total_volume": cvd_data["total_vol"],
        "buy_volume": cvd_data["total_buy_vol"],
        "sell_volume": cvd_data["total_sell_vol"],
        "buy_volume_ratio": cvd_data["buy_ratio"],
        "taker_dominance": dominance,
        "cumulative_delta": cvd_data["cvd"][-1] if cvd_data["cvd"] else 0.0,
        "recent_delta": cvd_data["deltas"][-1] if cvd_data["deltas"] else 0.0,
        "last_10_bars_delta_count": {"positive": pos_deltas, "negative": neg_deltas},
        "divergence": div_data,
    }
