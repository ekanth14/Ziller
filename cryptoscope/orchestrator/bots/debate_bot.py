"""DebateBot: Multi-agent adversarial deliberation, conviction scoring, and fail-closed safety."""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, DebateResult, SystemAlert, TradeIntent
from cryptoscope.agents.consensus import DeliberationConsensusEngine

logger = logging.getLogger("cryptoscope.orchestrator.debate_bot")


class DebateBot(BaseBot):
    """Adversarial research deliberation layer.

    Evaluates TradeIntent proposals using Bull, Bear, and Tri-Risk perspective debate.
    Enforces strict fail-closed protocol: if LLM inference times out (>200ms default
    or configured timeout) or encounters an error, it defaults to REJECT.
    """

    def __init__(
        self,
        bus: EventBus,
        name: str = "debate_bot",
        timeout_seconds: float = 0.20,
        min_conviction_threshold: float = 10.0
    ):
        super().__init__(name, bus)
        self.timeout_seconds = timeout_seconds
        self.min_conviction_threshold = min_conviction_threshold
        self.deliberation_engine = DeliberationConsensusEngine()
        self.debates_evaluated_count: int = 0
        self.fallbacks_count: int = 0

        self.subscribe(TradeIntent)

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, TradeIntent):
            await self._deliberate_intent(event)

    async def _deliberate_intent(self, intent: TradeIntent) -> None:
        t0 = time.time()
        fallback_triggered = False
        verdict = "REJECT"
        conviction = 0.0
        bull = ""
        bear = ""
        risk = ""

        try:
            indicators = {
                "price": intent.entry_price,
                "directional_score": 35.0 if intent.direction == "BUY" else -35.0,
                "atr": abs(intent.entry_price - intent.stop_loss),
                "rsi_14": 55.0 if intent.direction == "BUY" else 45.0,
                "macd_histogram": 0.001 if intent.direction == "BUY" else -0.001
            }

            debate_task = asyncio.to_thread(
                self.deliberation_engine.deliberate,
                symbol=intent.symbol,
                indicators=indicators,
                balance=10000.0
            )
            raw_res = await asyncio.wait_for(debate_task, timeout=self.timeout_seconds)

            conviction = float(raw_res.get("conviction_score", 0.0))
            bull = str(raw_res.get("bull_thesis", ""))
            bear = str(raw_res.get("bear_thesis", ""))
            risk = str(raw_res.get("risk_debate", ""))
            action = str(raw_res.get("action", "STAND_ASIDE"))

            if action in {"BUY", "SELL"} and conviction >= self.min_conviction_threshold:
                verdict = "APPROVE"
            else:
                verdict = "REJECT"

        except (asyncio.TimeoutError, TimeoutError):
            fallback_triggered = True
            self.fallbacks_count += 1
            verdict = "REJECT"
            conviction = 0.0
            bull = "Timeout during bull perspective evaluation."
            bear = "Debate latency exceeded safety deadline (>200ms)."
            risk = "Fail-closed safety veto: STAND_ASIDE on inference timeout."
            logger.warning("[%s] Deliberation timed out (>%.2fs) for intent %s. Defaulting to REJECT.", self.name, self.timeout_seconds, intent.intent_id)

        except Exception as exc:
            fallback_triggered = True
            self.fallbacks_count += 1
            verdict = "REJECT"
            conviction = 0.0
            bull = "LLM/model error encountered."
            bear = str(exc)
            risk = "Fail-closed safety veto: STAND_ASIDE on model failure."
            logger.error("[%s] Deliberation error for %s: %s. Defaulting to REJECT.", self.name, intent.symbol, exc)

        dt_ms = (time.time() - t0) * 1000.0
        self.debates_evaluated_count += 1

        result = DebateResult(
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            conviction_score=conviction,
            verdict=verdict,
            bull_thesis=bull,
            bear_thesis=bear,
            risk_summary=risk,
            latency_ms=round(dt_ms, 2),
            fallback_used=fallback_triggered
        )

        logger.info(
            "[%s] Intent %s (%s) Debate Verdict: %s (Conviction: %.1f, Latency: %.1fms, Fallback: %s)",
            self.name, intent.intent_id, intent.symbol, verdict, conviction, dt_ms, fallback_triggered
        )
        await self.emit(result)

    def get_health_details(self) -> Dict[str, Any]:
        return {
            "debates_evaluated": self.debates_evaluated_count,
            "fallbacks_triggered": self.fallbacks_count,
            "timeout_seconds": self.timeout_seconds
        }
