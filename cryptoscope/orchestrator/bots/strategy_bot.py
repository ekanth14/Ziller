"""StrategyBot: Evaluates composite signals and submits TradeIntent proposals."""

import logging
import time
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, MarketUpdate, Signal, TradeIntent

logger = logging.getLogger("cryptoscope.orchestrator.strategy_bot")


class StrategyBot(BaseBot):
    """Orchestrates algorithmic strategy execution and proposes TradeIntent.

    Consumes Signal and MarketUpdate events. Formulates entry, protective stop-loss,
    and take-profit targets, submitting proposals to the Debate layer.
    """

    def __init__(self, bus: EventBus, name: str = "strategy_bot", min_confidence: float = 0.65):
        super().__init__(name, bus)
        self.min_confidence = min_confidence
        self.is_paused: bool = False
        self.pause_reason: str = ""
        self.latest_prices: Dict[str, float] = {}
        self.proposed_intents_count: int = 0

        self.subscribe(MarketUpdate)
        self.subscribe(Signal)

    def pause(self, reason: str = "Operator paused") -> None:
        self.is_paused = True
        self.pause_reason = reason
        logger.warning("[%s] Paused: %s", self.name, reason)

    def resume(self) -> None:
        self.is_paused = False
        self.pause_reason = ""
        logger.info("[%s] Resumed operations.", self.name)

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, MarketUpdate):
            self.latest_prices[event.symbol] = event.price
        elif isinstance(event, Signal):
            await self._evaluate_signal(event)

    async def _evaluate_signal(self, sig: Signal) -> None:
        if self.is_paused:
            logger.debug("[%s] Signal discarded: strategy bot paused (%s)", self.name, self.pause_reason)
            return

        if sig.direction not in {"BUY", "SELL"}:
            return

        if sig.confidence < self.min_confidence:
            return

        price = sig.indicators.get("price") or self.latest_prices.get(sig.symbol)
        if not price or price <= 0:
            return

        atr = sig.indicators.get("atr", price * 0.015)
        # Ensure minimum stop distance of 0.5%
        risk_distance = max(atr * 1.5, price * 0.005)

        if sig.direction == "BUY":
            entry = price
            stop = round(entry - risk_distance, 4)
            target = round(entry + (risk_distance * 2.0), 4)  # 2:1 RR
        else:
            entry = price
            stop = round(entry + risk_distance, 4)
            target = round(entry - (risk_distance * 2.0), 4)

        intent = TradeIntent(
            strategy_id=sig.strategy_id,
            symbol=sig.symbol,
            direction=sig.direction,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            horizon_bars=48,
            reasons=sig.reasons + [f"Signal confidence {sig.confidence:.2f}"]
        )
        self.proposed_intents_count += 1
        logger.info("[%s] Proposing %s %s @ %.4f (SL: %.4f, TP: %.4f)", self.name, intent.direction, intent.symbol, entry, stop, target)
        await self.emit(intent)

    def get_health_details(self) -> Dict[str, Any]:
        return {
            "is_paused": self.is_paused,
            "pause_reason": self.pause_reason,
            "proposed_intents_count": self.proposed_intents_count
        }
