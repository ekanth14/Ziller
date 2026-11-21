"""Order-flow toxicity, book imbalance and volatility regime: RISK-ONLY inputs (they can shrink a trade, never add one).

Research basis (see docs/ALGORITHMS_AND_DECISION_ARCHITECTURE.md §14):
- VPIN (Easley, López de Prado, O'Hara) is better at warning of volatility / jumps than at predicting
  direction, so it is used only to cut size when flow is unusually one-sided.
- Order-flow / book imbalance predicts very short horizons; here it is a feature for the THX-02 / Laya
  meta-label check, not a trade trigger.
- Volatility regime: position size is cut when short-term volatility runs well above its own norm
  (volatility targeting; Moskowitz-Ooi-Pedersen, Baltas-Kosowski).

Approximations, stated plainly:
- "Bar VPIN" uses Binance's taker-buy volume per kline instead of trade-by-trade volume buckets, so it
  is a coarser estimate than tick VPIN. It is judged against the coin's own recent history (percentile),
  not a fixed threshold, because VPIN's level depends heavily on bucket size.
- The regime is a volatility ratio, not an HMM: the fleet keeps ~60 bars, too few to fit a hidden
  Markov model without fitting noise.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

VPIN_WINDOW = 20           # bars per VPIN estimate (~5 h of 15m bars)
VPIN_TOXIC_PCTILE = 0.90   # current VPIN in the top 10% of its own recent history...
VPIN_JUMP = 1.5            # ...and at least 1.5x its own median -> toxic
REGIME_HIGH, REGIME_EXTREME = 1.5, 2.5   # short/long volatility ratio


def bar_imbalance(candle: Dict[str, Any]) -> Optional[float]:
    """|taker buy - taker sell| volume for one bar (None when the bar has no taker split)."""
    try:
        vol = float(candle.get("volume") or 0.0)
        buy = candle.get("taker_buy_volume")
        if buy is None or vol <= 0:
            return None
        buy = min(max(float(buy), 0.0), vol)
        return abs(2 * buy - vol)
    except (TypeError, ValueError):
        return None


def vpin_series(candles: Sequence[Dict[str, Any]], window: int = VPIN_WINDOW) -> List[float]:
    """Rolling bar-VPIN: sum|buy - sell| / sum(volume) over `window` bars, one value per complete window."""
    imb, vol = [], []
    for c in candles:
        i = bar_imbalance(c)
        if i is None:
            continue
        imb.append(i)
        vol.append(float(c.get("volume") or 0.0))
    out = []
    for end in range(window, len(imb) + 1):
        v = sum(vol[end - window:end])
        if v > 0:
            out.append(sum(imb[end - window:end]) / v)
    return out


def vpin_state(candles: Sequence[Dict[str, Any]], window: int = VPIN_WINDOW) -> Dict[str, Any]:
    """Current bar-VPIN, its percentile within the available history, and whether it is 'toxic'."""
    s = vpin_series(candles, window)
    if not s:
        return {"vpin": None, "vpin_pctile": None, "toxic": False}
    cur = s[-1]
    pct = sum(1 for x in s if x <= cur) / len(s)
    median = sorted(s)[len(s) // 2]
    # A percentile alone flags ~10% of ordinary bars; also require a clear jump over the coin's own median.
    toxic = len(s) >= 10 and pct >= VPIN_TOXIC_PCTILE and cur >= VPIN_JUMP * median
    return {"vpin": round(cur, 4), "vpin_pctile": round(pct, 3), "toxic": toxic}


def vol_regime(candles: Sequence[Dict[str, Any]], short: int = 20) -> Dict[str, Any]:
    """Short-window vs whole-window volatility of log returns -> NORMAL / HIGH / EXTREME."""
    closes = []
    for c in candles:
        try:
            closes.append(float(c["close"]))
        except (KeyError, TypeError, ValueError):
            continue
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    if len(rets) < short + 10:
        return {"regime": None, "vol_ratio": None}

    def sd(x):
        m = sum(x) / len(x)
        return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1)) if len(x) > 1 else 0.0
    long_sd = sd(rets)
    ratio = sd(rets[-short:]) / long_sd if long_sd > 0 else None
    if ratio is None:
        return {"regime": None, "vol_ratio": None}
    regime = "EXTREME_VOL" if ratio >= REGIME_EXTREME else "HIGH_VOL" if ratio >= REGIME_HIGH else "NORMAL"
    return {"regime": regime, "vol_ratio": round(ratio, 3)}


def size_multiplier(features: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Risk-only scaling in (0, 1]: toxic flow halves size; high / extreme volatility -> x0.5 / x0.25.

    The smallest applicable factor wins; unknown inputs leave size unchanged. Never above 1.
    """
    f = features or {}
    mult, why = 1.0, []
    if f.get("vpin_toxic"):
        mult, why = min(mult, 0.5), why + [f"VPIN in top {100 - int(VPIN_TOXIC_PCTILE * 100)}% of its history"]
    regime = f.get("regime")
    if regime == "EXTREME_VOL":
        mult, why = min(mult, 0.25), why + ["extreme volatility regime"]
    elif regime == "HIGH_VOL":
        mult, why = min(mult, 0.5), why + ["high volatility regime"]
    return {"multiplier": mult, "reasons": why}


def book_imbalance(depth: Dict[str, Any], band: float = 0.005) -> Optional[float]:
    """(bid USDT - ask USDT) / total within +/-band of mid, from a depth snapshot. +1 all bids, -1 all asks."""
    try:
        bids = [(float(p), float(q)) for p, q in depth.get("bids", [])]
        asks = [(float(p), float(q)) for p, q in depth.get("asks", [])]
    except (TypeError, ValueError):
        return None
    if not bids or not asks:
        return None
    mid = (bids[0][0] + asks[0][0]) / 2
    b = sum(p * q for p, q in bids if p >= mid * (1 - band))
    a = sum(p * q for p, q in asks if p <= mid * (1 + band))
    return round((b - a) / (b + a), 4) if (a + b) > 0 else None
