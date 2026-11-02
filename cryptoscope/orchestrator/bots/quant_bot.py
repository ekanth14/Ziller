"""QuantBot: Statistical volatility regimes, CVD order-flow absorption, and cointegration edge."""

import logging
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, MarketUpdate, Signal
from cryptoscope.quant.volatility import volatility_regime_analysis
from cryptoscope.quant.order_flow import analyze_order_flow

logger = logging.getLogger("cryptoscope.orchestrator.quant_bot")


class QuantBot(BaseBot):
    """Quantitative risk, volatility regime, and order-flow alpha bot.

    Calculates institutional volatility estimators (Parkinson, Garman-Klass, Yang-Zhang),
    compression ratios, and Cumulative Volume Delta (CVD) divergences.
    """

    def __init__(self, bus: EventBus, name: str = "quant_bot"):
        super().__init__(name, bus)
        self.subscribe(MarketUpdate)
        self.latest_regimes: Dict[str, Dict[str, Any]] = {}

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, MarketUpdate):
            await self._compute_quant_metrics(event)

    async def _compute_quant_metrics(self, update: MarketUpdate) -> None:
        candles = update.candles
        if len(candles) < 20:
            return

        try:
            vol_metrics = volatility_regime_analysis(candles)
            flow_metrics = analyze_order_flow(candles)

            regime = vol_metrics.get("regime", "NORMAL")
            compression = vol_metrics.get("compression_ratio", 1.0)
            breakout_ready = vol_metrics.get("breakout_readiness_pct", 0.0)

            divergence = flow_metrics.get("divergence", {})
            has_absorption_buy = divergence.get("bullish_absorption", False)
            has_absorption_sell = divergence.get("bearish_exhaustion", False)

            direction = "HOLD"
            confidence = 0.50
            reasons = []

            if regime in {"EXTREME_COMPRESSION", "COMPRESSION"} and breakout_ready > 60:
                reasons.append(f"Volatility compression ({compression:.2f}) with high breakout readiness ({breakout_ready}%)")
                if has_absorption_buy:
                    direction = "BUY"
                    confidence = 0.80
                    reasons.append("Bullish institutional absorption divergence detected on CVD")
                elif has_absorption_sell:
                    direction = "SELL"
                    confidence = 0.80
                    reasons.append("Bearish exhaustion divergence detected on CVD")
            elif has_absorption_buy:
                direction = "BUY"
                confidence = 0.70
                reasons.append("Bullish volume delta divergence")
            elif has_absorption_sell:
                direction = "SELL"
                confidence = 0.70
                reasons.append("Bearish volume delta divergence")

            sig = Signal(
                strategy_id="quant_alpha",
                symbol=update.symbol,
                timeframe="15m",
                direction=direction,
                confidence=confidence,
                indicators={
                    "regime": regime,
                    "compression_ratio": round(compression, 3),
                    "breakout_readiness_pct": breakout_ready,
                    "buy_volume_ratio": flow_metrics.get("buy_volume_ratio", 0.5),
                    "taker_dominance": flow_metrics.get("taker_dominance", "BALANCED"),
                },
                reasons=reasons
            )
            self.latest_regimes[update.symbol] = {
                "regime": regime,
                "compression": compression,
                "direction": direction
            }
            if direction != "HOLD":
                await self.emit(sig)

        except Exception as exc:
            logger.error("[%s] Quant metrics failed for %s: %s", self.name, update.symbol, exc)

    def get_health_details(self) -> Dict[str, Any]:
        return {"latest_regimes": self.latest_regimes}
