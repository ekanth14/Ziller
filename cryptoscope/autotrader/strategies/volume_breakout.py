"""Volume Breakout Strategy (放量突破) adapted for 24/7 crypto markets.

Triggers when price cleanly breaks above a 20-period swing resistance on heavy volume
(>= 1.5x 20-period moving average volume) confirmed by EMA trend and non-overbought RSI.
"""
from typing import Any, Dict, List, Optional


class VolumeBreakoutStrategy:
    name = "volume_breakout"
    display_name = "Volume Breakout (放量突破)"

    def __init__(self, volume_multiplier: float = 1.5, lookback: int = 20, min_rsi: float = 50.0, max_rsi: float = 75.0):
        self.volume_multiplier = volume_multiplier
        self.lookback = lookback
        self.min_rsi = min_rsi
        self.max_rsi = max_rsi

    def evaluate(self, candles: List[Dict[str, Any]], indicators: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not candles or len(candles) < self.lookback + 5:
            return None

        recent = candles[-(self.lookback + 1):-1]
        current = candles[-1]

        swing_high = max(float(c["high"]) for c in recent)
        avg_volume = sum(float(c["volume"]) for c in recent) / len(recent)

        current_close = float(current["close"])
        current_open = float(current["open"])
        current_low = float(current["low"])
        current_volume = float(current["volume"])

        # 1. Price breakout confirmation
        price_breakout = current_close > swing_high and current_close > current_open

        # 2. Volume expansion confirmation
        volume_expansion = avg_volume > 0 and current_volume >= (self.volume_multiplier * avg_volume)

        # 3. Optional indicator filters if provided
        rsi = float(indicators.get("rsi14", 55.0)) if indicators else 55.0
        ema20 = float(indicators.get("ema20", 0.0)) if indicators else 0.0
        ema50 = float(indicators.get("ema50", 0.0)) if indicators else 0.0
        atr14 = float(indicators.get("atr14", current_close * 0.02)) if indicators else current_close * 0.02

        rsi_valid = self.min_rsi <= rsi <= self.max_rsi
        trend_valid = (ema20 >= ema50) if (ema20 > 0 and ema50 > 0) else True

        if price_breakout and volume_expansion and rsi_valid and trend_valid:
            # Entry at current close
            entry_price = current_close
            # Stop loss just below the breakout candle low or swing resistance
            stop_loss = min(current_low * 0.998, swing_high * 0.99)
            # Take profit at 2x risk distance
            risk_dist = entry_price - stop_loss
            take_profit = entry_price + (risk_dist * 2.0)

            vol_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            confidence = min(0.95, 0.65 + (vol_ratio - 1.5) * 0.1)

            return {
                "strategy": self.name,
                "display_name": self.display_name,
                "side": "BUY",
                "entry_price": round(entry_price, 4),
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
                "risk_reward_ratio": 2.0,
                "confidence": round(confidence, 3),
                "reason": (
                    f"Clean breakout above 20-bar resistance ({swing_high:.2f}) with "
                    f"{vol_ratio:.1f}x volume surge. RSI at {rsi:.1f}."
                ),
                "metadata": {
                    "swing_high": swing_high,
                    "avg_volume": avg_volume,
                    "volume_ratio": round(vol_ratio, 2),
                    "rsi": round(rsi, 2),
                },
            }

        return None
