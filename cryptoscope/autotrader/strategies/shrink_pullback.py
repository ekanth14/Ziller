"""Shrink Pullback Strategy (缩量回踩) adapted for 24/7 crypto markets.

Identifies exhaustion pullbacks into moving average support during established crypto uptrends.
Triggers when volume dries up during the retracement and price reacts with a bullish bounce.
"""
from typing import Any, Dict, List, Optional


class ShrinkPullbackStrategy:
    name = "shrink_pullback"
    display_name = "Shrink Pullback (缩量回踩)"

    def __init__(self, max_pullback_vol_ratio: float = 0.75, lookback: int = 20):
        self.max_pullback_vol_ratio = max_pullback_vol_ratio
        self.lookback = lookback

    def evaluate(self, candles: List[Dict[str, Any]], indicators: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not candles or len(candles) < self.lookback + 5:
            return None

        recent = candles[-(self.lookback + 1):-1]
        current = candles[-1]
        prev_candle = candles[-2]

        avg_volume = sum(float(c["volume"]) for c in recent) / len(recent)

        current_close = float(current["close"])
        current_open = float(current["open"])
        current_low = float(current["low"])
        prev_close = float(prev_candle["close"])
        prev_low = float(prev_candle["low"])
        prev_volume = float(prev_candle["volume"])

        # Indicators
        ema20 = float(indicators.get("ema20", 0.0)) if indicators else 0.0
        ema50 = float(indicators.get("ema50", 0.0)) if indicators else 0.0
        rsi = float(indicators.get("rsi14", 50.0)) if indicators else 50.0

        if ema20 <= 0 or ema50 <= 0:
            return None

        # 1. Macro Trend: EMA20 must be above EMA50
        uptrend = ema20 > ema50

        # 2. Pullback test: Previous or current bar low tested near EMA20 (within 1.2%)
        tested_ema = abs(prev_low - ema20) / ema20 <= 0.015 or abs(current_low - ema20) / ema20 <= 0.015

        # 3. Shrinking volume on pullback: previous candle volume was below average (lack of aggressive selling)
        volume_exhausted = avg_volume > 0 and prev_volume <= (self.max_pullback_vol_ratio * avg_volume)

        # 4. Bullish rejection / rebound candle
        bullish_rebound = current_close > current_open and current_close > prev_close and rsi >= 42

        if uptrend and tested_ema and volume_exhausted and bullish_rebound:
            entry_price = current_close
            stop_loss = min(current_low, prev_low) * 0.995  # Stop below support wick
            risk_dist = max(entry_price * 0.01, entry_price - stop_loss)
            take_profit = entry_price + (risk_dist * 2.2)  # Favorable 2.2R target

            vol_ratio = prev_volume / avg_volume if avg_volume > 0 else 1.0
            confidence = min(0.92, 0.70 + (0.75 - vol_ratio) * 0.2)

            return {
                "strategy": self.name,
                "display_name": self.display_name,
                "side": "BUY",
                "entry_price": round(entry_price, 4),
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
                "risk_reward_ratio": 2.2,
                "confidence": round(confidence, 3),
                "reason": (
                    f"Low-volume exhaustion pullback to EMA20 support ({ema20:.2f}) with "
                    f"{vol_ratio:.1f}x volume dry-up, followed by bullish rebound."
                ),
                "metadata": {
                    "ema20": ema20,
                    "ema50": ema50,
                    "pullback_vol_ratio": round(vol_ratio, 2),
                    "rsi": round(rsi, 2),
                },
            }

        return None
