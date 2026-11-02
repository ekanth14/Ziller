"""Box Oscillation Strategy (箱体震荡) adapted for 24/7 crypto markets.

Exploits range-bound consolidation regimes by buying near lower box support with tight stops
and targeting mean-reversion to the upper box boundary.
"""
from typing import Any, Dict, List, Optional


class BoxOscillationStrategy:
    name = "box_oscillation"
    display_name = "Box Oscillation (箱体震荡)"

    def __init__(
        self,
        lookback: int = 30,
        min_height_pct: float = 0.025,
        max_height_pct: float = 0.09,
        min_risk_reward: float = 1.2,
    ):
        self.lookback = lookback
        self.min_height_pct = min_height_pct
        self.max_height_pct = max_height_pct
        self.min_risk_reward = min_risk_reward

    def evaluate(self, candles: List[Dict[str, Any]], indicators: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not candles or len(candles) < self.lookback + 1:
            return None

        recent = candles[-self.lookback:]
        current = candles[-1]

        box_high = max(float(c["high"]) for c in recent[:-1])
        box_low = min(float(c["low"]) for c in recent[:-1])

        if box_low <= 0:
            return None

        box_height = (box_high - box_low) / box_low

        # 1. Filter: Range must be defined (between min_height_pct and max_height_pct)
        if not (self.min_height_pct <= box_height <= self.max_height_pct):
            return None

        current_close = float(current["close"])
        current_open = float(current["open"])
        current_low = float(current["low"])

        # 2. Entry condition: price in lower 25% of the box
        box_range = box_high - box_low
        position_in_box = (current_close - box_low) / box_range

        # 3. Support reaction: tested box_low and closed higher
        tested_support = current_low <= (box_low + 0.25 * box_range)
        rejection_candle = current_close > current_open

        rsi = float(indicators.get("rsi14", 45.0)) if indicators else 45.0

        if position_in_box <= 0.25 and tested_support and rejection_candle and rsi <= 50.0:
            entry_price = current_close
            stop_loss = box_low * 0.992  # Below box floor
            take_profit = box_high * 0.988  # Near upper box boundary

            risk_dist = max(entry_price * 0.005, entry_price - stop_loss)
            reward_dist = take_profit - entry_price

            if risk_dist <= 0 or reward_dist <= 0:
                return None

            rr = reward_dist / risk_dist
            if rr < self.min_risk_reward:
                return None

            return {
                "strategy": self.name,
                "display_name": self.display_name,
                "side": "BUY",
                "entry_price": round(entry_price, 4),
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
                "risk_reward_ratio": round(rr, 2),
                "confidence": 0.72,
                "reason": (
                    f"Bounce at box support floor ({box_low:.2f}) in a {box_height*100:.1f}% range. "
                    f"Targeting upper resistance ({box_high:.2f}) with {rr:.1f}R."
                ),
                "metadata": {
                    "box_high": box_high,
                    "box_low": box_low,
                    "box_height_pct": round(box_height * 100, 2),
                    "position_in_box": round(position_in_box, 2),
                    "rsi": round(rsi, 2),
                },
            }

        return None
