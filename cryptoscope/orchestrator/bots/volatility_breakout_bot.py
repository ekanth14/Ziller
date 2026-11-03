"""VolatilityBreakoutBot: Autonomous strategy bot trading volatility compression breakouts."""

import logging
import time
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, MarketUpdate, Signal
from cryptoscope.autotrader.strategies.volatility_breakout import VolatilityCompressionBreakoutStrategy

logger = logging.getLogger("cryptoscope.orchestrator.volatility_breakout_bot")


class VolatilityBreakoutBot(BaseBot):
    """Detects volatility compression squeezes and emits momentum breakout signals."""

    def __init__(
        self,
        bus: EventBus,
        name: str = "volatility_breakout_bot",
        compression_threshold: float = 0.70,
        lookback_bars: int = 24,
        cooldown_sec: float = 10.0,
    ):
        super().__init__(name, bus)
        self.strategy = VolatilityCompressionBreakoutStrategy(
            compression_threshold=compression_threshold,
            lookback_bars=lookback_bars,
        )
        self.cooldown_sec = cooldown_sec
        self.last_signal_time: Dict[str, float] = {}
        self.signals_generated_count: int = 0
        self.is_paused: bool = False

        self.subscribe(MarketUpdate)

    def pause(self, reason: str = "") -> None:
        self.is_paused = True
        logger.warning("[%s] Paused: %s", self.name, reason)

    def resume(self) -> None:
        self.is_paused = False
        logger.info("[%s] Resumed operations", self.name)

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, MarketUpdate):
            await self._evaluate_market_update(event)

    async def _evaluate_market_update(self, update: MarketUpdate) -> None:
        if self.is_paused:
            return

        candles = update.candles
        if not candles or len(candles) < 30:
            return

        now = time.time()
        if (now - self.last_signal_time.get(update.symbol, 0.0)) < self.cooldown_sec:
            return

        try:
            res = self.strategy.evaluate(candles)
            if not res:
                return

            direction = res.get("side", "HOLD")
            if direction not in {"BUY", "SELL"}:
                return

            self.last_signal_time[update.symbol] = now
            self.signals_generated_count += 1

            sig = Signal(
                strategy_id="volatility_breakout",
                symbol=update.symbol,
                timeframe="15m",
                direction=direction,
                confidence=float(res.get("confidence", 0.75)),
                indicators={
                    "price": res.get("entry_price", update.price),
                    "stop_loss": res.get("stop_loss"),
                    "take_profit": res.get("take_profit"),
                    "volatility_regime": res.get("volatility_regime"),
                    "compression_ratio": res.get("compression_ratio"),
                },
                reasons=[res.get("reason", "Volatility compression breakout detected")],
            )
            logger.info(
                "[%s] Signal generated for %s: %s (Confidence: %.2f)",
                self.name, update.symbol, direction, sig.confidence
            )
            await self.emit(sig)

        except Exception as exc:
            logger.error("[%s] Evaluation error for %s: %s", self.name, update.symbol, exc)

    def get_health_details(self) -> Dict[str, Any]:
        return {
            "signals_generated_count": self.signals_generated_count,
            "is_paused": self.is_paused,
        }
