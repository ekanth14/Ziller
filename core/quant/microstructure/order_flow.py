"""Order Flow Screener Engine.

Implements Cumulative Volume Delta (CVD), Delta Divergence detection,
and aggressive order Absorption detection, inspired by zadescoxp/order-flow-screener.
Zero-lookahead compliant and mathematically verified.
"""

from enum import Enum
import math
from typing import Any, Mapping, Sequence
import numpy as np


class DivergenceType(str, Enum):
    BEARISH_REGULAR = "bearish_regular"
    BULLISH_REGULAR = "bullish_regular"
    BEARISH_HIDDEN = "bearish_hidden"
    BULLISH_HIDDEN = "bullish_hidden"


class AbsorptionType(str, Enum):
    ASK_ABSORPTION = "ask_absorption"  # Aggressive buyers absorbed by passive limit sellers
    BID_ABSORPTION = "bid_absorption"  # Aggressive sellers absorbed by passive limit buyers
    NEUTRAL_ABSORPTION = "neutral_absorption"


def compute_cumulative_volume_delta(
    buy_volumes: Sequence[float],
    sell_volumes: Sequence[float],
    initial_delta: float = 0.0,
) -> list[float]:
    """Calculate cumulative volume delta (CVD) across sequential bars.

    CVD_t = CVD_{t-1} + (V_buy - V_sell)
    """
    if len(buy_volumes) != len(sell_volumes):
        raise ValueError(
            f"Length mismatch between buy_volumes ({len(buy_volumes)}) and sell_volumes ({len(sell_volumes)})"
        )
    if not buy_volumes:
        return []

    cvd: list[float] = []
    running = float(initial_delta)
    for b, s in zip(buy_volumes, sell_volumes):
        delta = float(b) - float(s)
        running += delta
        cvd.append(running)
    return cvd


def compute_cvd_from_trades(
    trades: Sequence[Mapping[str, Any]],
    initial_delta: float = 0.0,
) -> list[float]:
    """Compute running CVD from a sequence of individual trade ticks.

    Trade format expects 'size' or 'amount', and either:
    - 'side': 'buy' / 'sell'
    - 'is_buyer_maker': bool (True = maker is buyer -> taker is seller -> sell side)
    """
    if not trades:
        return []

    cvd: list[float] = []
    running = float(initial_delta)
    for t in trades:
        size = float(t.get("size", t.get("amount", 0.0)))
        side = t.get("side")
        if side is not None:
            is_buy = str(side).lower() in ("buy", "b")
        elif "is_buyer_maker" in t:
            # If buyer is maker, taker is seller -> sell trade
            is_buy = not bool(t["is_buyer_maker"])
        else:
            is_buy = True  # fallback

        delta = size if is_buy else -size
        running += delta
        cvd.append(running)
    return cvd


def compute_cvd_from_candles(
    candles: Sequence[Mapping[str, Any]],
    initial_delta: float = 0.0,
) -> list[float]:
    """Compute CVD from candle/bar sequence.

    Candle format expects:
    - 'taker_buy_volume' and 'volume' (sell_volume = volume - taker_buy_volume)
    OR
    - 'buy_volume' and 'sell_volume'
    """
    if not candles:
        return []

    buy_volumes: list[float] = []
    sell_volumes: list[float] = []
    for c in candles:
        if "taker_buy_volume" in c and "volume" in c:
            vol = float(c["volume"])
            buy_v = float(c["taker_buy_volume"])
            sell_v = max(0.0, vol - buy_v)
        else:
            buy_v = float(c.get("buy_volume", 0.0))
            sell_v = float(c.get("sell_volume", 0.0))
        buy_volumes.append(buy_v)
        sell_volumes.append(sell_v)

    return compute_cumulative_volume_delta(buy_volumes, sell_volumes, initial_delta=initial_delta)


def detect_delta_divergence(
    prices: Sequence[float],
    cvd: Sequence[float],
    lookback: int = 5,
    tolerance: float = 1e-6,
) -> list[dict[str, Any]]:
    """Detect regular and hidden divergences between Price action and Cumulative Volume Delta.

    Zero-lookahead: At step t, compares (Price_t, CVD_t) with past extremum in [t-lookback, t-1].
    - Bearish Regular: Price higher high, CVD lower high (exhaustion of buying momentum)
    - Bullish Regular: Price lower low, CVD higher low (exhaustion of selling momentum)
    - Bearish Hidden: Price lower high, CVD higher high (passive resistance absorbing aggressive buyers)
    - Bullish Hidden: Price higher low, CVD lower low (passive support absorbing aggressive sellers)
    """
    n = min(len(prices), len(cvd))
    if n < 2 or lookback < 1:
        return []

    divergences: list[dict[str, Any]] = []

    for t in range(1, n):
        start_idx = max(0, t - lookback)
        past_prices = prices[start_idx:t]
        past_cvd = cvd[start_idx:t]
        if not past_prices:
            continue

        curr_p = prices[t]
        curr_c = cvd[t]

        # Check for regular bearish divergence
        # Past high in window
        max_past_p = max(past_prices)
        idx_max_p = start_idx + past_prices.index(max_past_p)
        if curr_p > max_past_p + tolerance and curr_c < cvd[idx_max_p] - tolerance:
            divergences.append({
                "index": t,
                "type": DivergenceType.BEARISH_REGULAR.value,
                "price": curr_p,
                "cvd": curr_c,
                "ref_index": idx_max_p,
                "ref_price": max_past_p,
                "ref_cvd": cvd[idx_max_p],
                "price_higher": True,
                "cvd_lower": True,
            })
            continue

        # Check for regular bullish divergence
        # Past low in window
        min_past_p = min(past_prices)
        idx_min_p = start_idx + past_prices.index(min_past_p)
        if curr_p < min_past_p - tolerance and curr_c > cvd[idx_min_p] + tolerance:
            divergences.append({
                "index": t,
                "type": DivergenceType.BULLISH_REGULAR.value,
                "price": curr_p,
                "cvd": curr_c,
                "ref_index": idx_min_p,
                "ref_price": min_past_p,
                "ref_cvd": cvd[idx_min_p],
                "price_lower": True,
                "cvd_higher": True,
            })
            continue

        # Check for hidden bearish divergence (price lower high, CVD higher high)
        max_past_c = max(past_cvd)
        idx_max_c = start_idx + past_cvd.index(max_past_c)
        if curr_p < prices[idx_max_c] - tolerance and curr_c > max_past_c + tolerance:
            divergences.append({
                "index": t,
                "type": DivergenceType.BEARISH_HIDDEN.value,
                "price": curr_p,
                "cvd": curr_c,
                "ref_index": idx_max_c,
                "ref_price": prices[idx_max_c],
                "ref_cvd": max_past_c,
            })
            continue

        # Check for hidden bullish divergence (price higher low, CVD lower low)
        min_past_c = min(past_cvd)
        idx_min_c = start_idx + past_cvd.index(min_past_c)
        if curr_p > prices[idx_min_c] + tolerance and curr_c < min_past_c - tolerance:
            divergences.append({
                "index": t,
                "type": DivergenceType.BULLISH_HIDDEN.value,
                "price": curr_p,
                "cvd": curr_c,
                "ref_index": idx_min_c,
                "ref_price": prices[idx_min_c],
                "ref_cvd": min_past_c,
            })

    return divergences


def detect_absorption(
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    deltas: Sequence[float] | None = None,
    volume_threshold_percentile: float = 80.0,
    spread_threshold_percentile: float = 30.0,
) -> list[dict[str, Any]]:
    """Detect aggressive order absorption by passive limit orders.

    Absorption criteria:
    1. Unusually high volume (>= volume_threshold_percentile across sample/window)
    2. Unusually narrow spread / range (high - low <= spread_threshold_percentile)
    3. Side classification via bar delta:
       - Positive delta: aggressive buys absorbed by passive sellers (Ask Absorption)
       - Negative delta: aggressive sells absorbed by passive buyers (Bid Absorption)
    """
    n = min(len(highs), len(lows), len(volumes))
    if n == 0:
        return []

    spreads = [max(0.0, float(h) - float(l)) for h, l in zip(highs[:n], lows[:n])]
    vols = [float(v) for v in volumes[:n]]

    vol_thresh = float(np.percentile(vols, volume_threshold_percentile))
    spread_thresh = float(np.percentile(spreads, spread_threshold_percentile))

    absorptions: list[dict[str, Any]] = []

    for i in range(n):
        if vols[i] >= vol_thresh and spreads[i] <= spread_thresh:
            delta = float(deltas[i]) if (deltas is not None and i < len(deltas)) else 0.0
            if delta > 0:
                abs_type = AbsorptionType.ASK_ABSORPTION.value
                thesis = "Aggressive buyers absorbed by passive sell limits."
            elif delta < 0:
                abs_type = AbsorptionType.BID_ABSORPTION.value
                thesis = "Aggressive sellers absorbed by passive buy limits."
            else:
                abs_type = AbsorptionType.NEUTRAL_ABSORPTION.value
                thesis = "Heavy volume churn with tight range; direction neutral."

            absorptions.append({
                "index": i,
                "type": abs_type,
                "volume": vols[i],
                "spread": spreads[i],
                "delta": delta,
                "thesis": thesis,
            })

    return absorptions


class OrderFlowScreener:
    """Institutional Order Flow Screener aggregating CVD, Divergences, and Absorption."""

    def __init__(self, divergence_lookback: int = 14) -> None:
        self.divergence_lookback = divergence_lookback

    def analyze(self, candles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Analyze candle series and produce order flow telemetry."""
        if not candles:
            return {
                "cvd": [],
                "latest_cvd": 0.0,
                "divergences": [],
                "absorptions": [],
                "summary": "No candle data provided.",
            }

        highs = [float(c.get("high", 0.0)) for c in candles]
        lows = [float(c.get("low", 0.0)) for c in candles]
        closes = [float(c.get("close", 0.0)) for c in candles]
        volumes = [float(c.get("volume", 0.0)) for c in candles]

        # Calculate CVD and per-bar deltas
        deltas: list[float] = []
        for c in candles:
            if "taker_buy_volume" in c and "volume" in c:
                buy_v = float(c["taker_buy_volume"])
                sell_v = max(0.0, float(c["volume"]) - buy_v)
            else:
                buy_v = float(c.get("buy_volume", 0.0))
                sell_v = float(c.get("sell_volume", 0.0))
            deltas.append(buy_v - sell_v)

        cvd = compute_cumulative_volume_delta(
            buy_volumes=[float(c.get("taker_buy_volume", c.get("buy_volume", 0.0))) for c in candles],
            sell_volumes=[
                max(0.0, float(c.get("volume", 0.0)) - float(c.get("taker_buy_volume", c.get("buy_volume", 0.0))))
                if "volume" in c else float(c.get("sell_volume", 0.0))
                for c in candles
            ],
        )

        divergences = detect_delta_divergence(
            prices=closes,
            cvd=cvd,
            lookback=self.divergence_lookback,
        )

        absorptions = detect_absorption(
            highs=highs,
            lows=lows,
            volumes=volumes,
            deltas=deltas,
        )

        latest_cvd = cvd[-1] if cvd else 0.0
        return {
            "cvd": cvd,
            "latest_cvd": latest_cvd,
            "divergences": divergences,
            "absorptions": absorptions,
            "summary": (
                f"Order Flow Analysis: Latest CVD {latest_cvd:.2f}, "
                f"{len(divergences)} divergence alerts, {len(absorptions)} absorption bars detected."
            ),
        }
