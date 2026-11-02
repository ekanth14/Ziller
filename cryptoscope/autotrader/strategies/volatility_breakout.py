"""Volatility Compression Breakout Strategy (波动率压缩突破).

Identifies volatility squeeze regimes using Parkinson and Garman-Klass
volatility estimators. Enters directional momentum breakout when price
violates the consolidation bounds with volume and CVD delta confirmation.
"""

from typing import Any, Dict, List, Optional
from cryptoscope.quant.volatility import volatility_regime_analysis
from cryptoscope.quant.order_flow import calculate_cvd


class VolatilityCompressionBreakoutStrategy:
    name = "volatility_breakout"
    display_name = "Volatility Compression Breakout (波动率压缩突破)"

    def __init__(
        self,
        compression_threshold: float = 0.70,
        lookback_bars: int = 24,
        atr_risk_multiple: float = 1.5,
        target_risk_multiple: float = 2.5,
    ):
        self.compression_threshold = compression_threshold
        self.lookback_bars = lookback_bars
        self.atr_risk_multiple = atr_risk_multiple
        self.target_risk_multiple = target_risk_multiple

    def evaluate(
        self,
        candles: List[Dict[str, Any]],
        indicators: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not candles or len(candles) < self.lookback_bars + 15:
            return None

        # 1. Evaluate Volatility Regime on pre-breakout consolidation (candles[:-1])
        vol_diag = volatility_regime_analysis(
            candles[:-1],
            window=min(20, len(candles) // 2),
            baseline_window=min(60, len(candles) - 2),
        )

        compression_ratio = vol_diag.get("compression_ratio", 1.0)
        atr = vol_diag.get("metrics", {}).get("atr", 0.0)
        if atr <= 0:
            atr = float(candles[-1]["high"]) - float(candles[-1]["low"])

        # 2. Consolidation Box calculation
        recent = candles[-self.lookback_bars : -1]
        current = candles[-1]

        box_high = max(float(c["high"]) for c in recent)
        box_low = min(float(c["low"]) for c in recent)

        curr_close = float(current["close"])
        curr_open = float(current["open"])
        curr_vol = float(current.get("volume", 0.0))

        avg_vol = sum(float(c.get("volume", 0.0)) for c in recent) / len(recent)
        vol_factor = (curr_vol / avg_vol) if avg_vol > 0 else 1.0

        # Order flow CVD delta for confirmation
        cvd_info = calculate_cvd(candles[-10:])
        recent_delta = cvd_info["deltas"][-1] if cvd_info["deltas"] else 0.0

        # Bullish Breakout condition
        is_bull_break = (
            curr_close > box_high
            and curr_close > curr_open
            and (compression_ratio <= self.compression_threshold or vol_diag["regime"] == "COMPRESSION_SQUEEZE")
            and (vol_factor >= 1.2 or recent_delta > 0)
        )

        # Bearish Breakdown condition
        is_bear_break = (
            curr_close < box_low
            and curr_close < curr_open
            and (compression_ratio <= self.compression_threshold or vol_diag["regime"] == "COMPRESSION_SQUEEZE")
            and (vol_factor >= 1.2 or recent_delta < 0)
        )

        stop_distance = max(atr * self.atr_risk_multiple, abs(curr_close - curr_open) * 1.2)

        if is_bull_break:
            stop_loss = curr_close - stop_distance
            take_profit = curr_close + (stop_distance * self.target_risk_multiple)
            conf = min(0.95, 0.70 + (0.70 - compression_ratio) * 0.4 + (vol_factor - 1.0) * 0.05)

            return {
                "strategy": self.name,
                "display_name": self.display_name,
                "side": "BUY",
                "entry_price": round(curr_close, 4),
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
                "risk_reward_ratio": self.target_risk_multiple,
                "confidence": round(conf, 3),
                "volatility_regime": vol_diag["regime"],
                "compression_ratio": compression_ratio,
                "reason": (
                    f"Volatility squeeze breakout above {box_high:.2f} with compression ratio {compression_ratio:.2f} "
                    f"and volume expansion {vol_factor:.2f}x."
                ),
            }

        elif is_bear_break:
            stop_loss = curr_close + stop_distance
            take_profit = curr_close - (stop_distance * self.target_risk_multiple)
            conf = min(0.95, 0.70 + (0.70 - compression_ratio) * 0.4 + (vol_factor - 1.0) * 0.05)

            return {
                "strategy": self.name,
                "display_name": self.display_name,
                "side": "SELL",
                "entry_price": round(curr_close, 4),
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
                "risk_reward_ratio": self.target_risk_multiple,
                "confidence": round(conf, 3),
                "volatility_regime": vol_diag["regime"],
                "compression_ratio": compression_ratio,
                "reason": (
                    f"Volatility squeeze breakdown below {box_low:.2f} with compression ratio {compression_ratio:.2f} "
                    f"and volume expansion {vol_factor:.2f}x."
                ),
            }

        return None
