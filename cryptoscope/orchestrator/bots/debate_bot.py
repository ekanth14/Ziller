"""DebateBot: Multi-agent adversarial deliberation, conviction scoring, and fail-closed safety."""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, DebateResult, RiskPreApproved, SystemAlert, TradeIntent
from cryptoscope.agents.consensus import DeliberationConsensusEngine

logger = logging.getLogger("cryptoscope.orchestrator.debate_bot")


class DebateBot(BaseBot):
    """Adversarial research deliberation layer.

    Evaluates TradeIntent proposals using combined single-call Bull, Bear, and Risk Moderator perspectives.
    Executes strictly after Tier 1 and Risk pre-checks pass.
    Enforces strict fail-closed protocol: if LLM inference times out (default 35s from measured p95)
    or encounters an error/invalid JSON, it defaults to REJECT.
    """

    def __init__(
        self,
        bus: EventBus,
        name: str = "debate_bot",
        timeout_seconds: Optional[float] = None,
        timeout_sec: Optional[float] = None,
        min_conviction_threshold: float = 6.0,
        risk_bot=None,
    ):
        super().__init__(name, bus)
        default_budget = float(os.environ.get("DEBATE_TIMEOUT_SEC", "35.0"))
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else (timeout_sec if timeout_sec is not None else default_budget)
        self.min_conviction_threshold = min_conviction_threshold
        self.risk_bot = risk_bot
        self.deliberation_engine = DeliberationConsensusEngine()
        self.debates_evaluated_count: int = 0
        self.fallbacks_count: int = 0
        self.skipped_busy_count: int = 0
        # Ollama answers one prompt at a time; queued debates would only time out behind each other.
        self._busy = asyncio.Lock()
        # THX-02 / Laya meta-labeler (separate sidecar process). No sidecar -> "no opinion", instantly.
        from cryptoscope.agents.decision_models import MetaLabeler
        self.meta_labeler = MetaLabeler(timeout=float(os.environ.get("ZILLERS_META_TIMEOUT_SEC", "20")))
        self.meta_timeout = float(os.environ.get("ZILLERS_META_TIMEOUT_SEC", "20")) + 5.0
        self.meta_answered_count: int = 0

        self.subscribe(RiskPreApproved)
        self.subscribe(TradeIntent)

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, RiskPreApproved):
            await self._deliberate_pre_approved(event)
        elif isinstance(event, TradeIntent):
            await self._deliberate_intent(event)

    def _check_risk_pre_conditions(self, intent: TradeIntent) -> Tuple[bool, List[str]]:
        """Verify deterministic risk constraints before launching expensive LLM debate."""
        if self.risk_bot and hasattr(self.risk_bot, "check_pre_trade_risk"):
            return self.risk_bot.check_pre_trade_risk(intent)
        stop_dist = abs(intent.entry_price - intent.stop_loss) / (intent.entry_price or 1.0)
        if stop_dist < 0.005:
            return False, ["STOP_TOO_TIGHT: Stop distance below minimum 0.50%"]
        return True, []

    async def _deliberate_pre_approved(self, pre: RiskPreApproved) -> None:
        """Run single combined debate call after risk pre-checks pass."""
        if self._busy.locked():
            self.skipped_busy_count += 1
            logger.info("[%s] Debate model busy; skipping %s %s (it will be re-proposed).", self.name, pre.symbol, pre.intent_id)
            await self.emit(DebateResult(intent_id=pre.intent_id, symbol=pre.symbol, conviction_score=0.0, verdict="REJECT",
                                         bull_thesis="Skipped - debate model busy", bear_thesis="DEBATE_BUSY",
                                         risk_summary="DEBATE_BUSY: another trade is being debated", latency_ms=0.0,
                                         fallback_used=True))
            return
        async with self._busy:
            await self._run_debate(pre)

    @staticmethod
    def _book_imbalance(symbol: str):
        """Public depth snapshot -> bid/ask USDT imbalance within +/-0.5% (feature only; None on any error)."""
        try:
            from cryptoscope.desk.scanner import fetch_depth
            from cryptoscope.quant.flow_risk import book_imbalance
            return book_imbalance(fetch_depth(symbol))
        except Exception:
            return None

    async def _meta_assess(self, pre: RiskPreApproved) -> Dict[str, Any]:
        """Ask THX-02 and Laya 'take or skip?'. Returns {} -style 'no opinion' fields on any problem."""
        from cryptoscope.agents.decision_models import enforce_enabled
        features = dict((pre.intent.metadata or {}).get("features") or {}) if pre.intent else {}
        horizon_h = (pre.intent.horizon_bars / 4.0) if pre.intent else 4.0   # 15m bars
        if self.meta_labeler._endpoint()[0] and "book_imbalance" not in features:
            features["book_imbalance"] = await asyncio.to_thread(self._book_imbalance, pre.symbol)
        try:
            meta = await asyncio.to_thread(self.meta_labeler.assess, pre.symbol, pre.direction, pre.entry_price,
                                           pre.stop_loss, pre.take_profit, horizon_h, features)
        except Exception as exc:   # assess() already never raises; belt and braces
            meta = {"mean_p": None, "errors": {"sidecar": type(exc).__name__}}
        from cryptoscope.agents.decision_models import veto_reason
        meta["enforced"] = enforce_enabled()
        meta["vetoed"] = veto_reason(meta) is not None
        if meta.get("mean_p") is not None:
            self.meta_answered_count += 1
        return meta

    async def _run_debate(self, pre: RiskPreApproved) -> None:
        t0 = time.time()
        self.debates_evaluated_count += 1
        intent_id = pre.intent_id
        symbol = pre.symbol

        indicators = {
            "price": pre.entry_price,
            "direction": pre.direction,
            "stop": pre.stop_loss,
            "target": pre.take_profit,
            "strategy": pre.strategy_id,
        }
        # Offline replay keys must bind to the exact information available at
        # the decision bar. This optional context carries no sizing authority.
        if pre.intent and 'debate_context' in pre.intent.metadata:
            indicators['replay_context'] = pre.intent.metadata['debate_context']

        # THX-02 / Laya meta-label check runs alongside the LLM debate; it never delays or blocks it.
        meta_task = asyncio.ensure_future(self._meta_assess(pre))

        try:
            debate_task = asyncio.to_thread(
                self.deliberation_engine.deliberate_combined,
                symbol=symbol,
                direction=pre.direction,
                entry=pre.entry_price,
                stop=pre.stop_loss,
                target=pre.take_profit,
                indicators=indicators,
                timeout_sec=self.timeout_seconds,
            )
            raw_res = await asyncio.wait_for(debate_task, timeout=self.timeout_seconds)
            verdict = raw_res.get("verdict", "REJECT")
            conviction = float(raw_res.get("conviction_score", 0.0))
            bull = str(raw_res.get("bull_thesis", ""))
            bear = str(raw_res.get("bear_thesis", ""))
            risk = str(raw_res.get("reason", ""))
            fallback_used = raw_res.get("fallback_used", False)
            if fallback_used:
                self.fallbacks_count += 1

        except (asyncio.TimeoutError, TimeoutError):
            self.fallbacks_count += 1
            verdict = "REJECT"
            conviction = 0.0
            bull = "Timeout during combined perspective evaluation."
            bear = f"Debate latency exceeded safety deadline (>{self.timeout_seconds:.1f}s)."
            risk = f"Timed out. Fail-closed safety veto: STAND_ASIDE on inference timeout."
            fallback_used = True
            logger.warning("[%s] Deliberation timed out (>%.2fs) for intent %s. Defaulting to REJECT.", self.name, self.timeout_seconds, intent_id)

        except Exception as exc:
            self.fallbacks_count += 1
            verdict = "REJECT"
            conviction = 0.0
            bull = "LLM/model error encountered."
            bear = str(exc)
            risk = f"Fail-closed safety veto: {exc}"
            fallback_used = True
            logger.error("[%s] Deliberation error for %s: %s. Defaulting to REJECT.", self.name, symbol, exc)

        latency_ms = (time.time() - t0) * 1000.0
        try:
            meta = await asyncio.wait_for(meta_task, timeout=max(1.0, self.meta_timeout - (time.time() - t0)))
        except Exception:
            meta_task.cancel()
            meta = {"errors": {"sidecar": "timeout"}}
        result_event = DebateResult(
            intent_id=intent_id,
            symbol=symbol,
            conviction_score=conviction,
            verdict=verdict,
            bull_thesis=bull,
            bear_thesis=bear,
            risk_summary=risk,
            latency_ms=round(latency_ms, 2),
            fallback_used=fallback_used,
            meta=meta,
        )
        logger.info(
            "[%s] Deliberation completed for %s (%s): %s (Conviction: %.1f, Latency: %.1fms)",
            self.name, intent_id, symbol, verdict, conviction, latency_ms
        )
        await self.emit(result_event)

    async def _deliberate_intent(self, intent: TradeIntent) -> None:
        """Run risk pre-checks before LLM debate on TradeIntent."""
        passed, reasons = self._check_risk_pre_conditions(intent)
        if not passed:
            self.debates_evaluated_count += 1
            self.fallbacks_count += 1
            logger.info("[%s] Intent %s failed risk pre-checks (%s). Skipping LLM debate.", self.name, intent.intent_id, reasons)
            await self.emit(DebateResult(
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                conviction_score=0.0,
                verdict="REJECT",
                bull_thesis="Bypassed - risk pre-check vetoed",
                bear_thesis=reasons[0] if reasons else "Risk pre-check failed",
                risk_summary=f"Risk pre-checks failed: {reasons}",
                latency_ms=0.0,
                fallback_used=True,
            ))
            return

        pre = RiskPreApproved(
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            direction=intent.direction,
            entry_price=intent.entry_price,
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
            strategy_id=intent.strategy_id,
            intent=intent,
        )
        await self._deliberate_pre_approved(pre)

    def get_health_details(self) -> Dict[str, Any]:
        return {
            "debates_evaluated": self.debates_evaluated_count,
            "fallbacks_triggered": self.fallbacks_count,
            "timeout_seconds": self.timeout_seconds,
            "skipped_busy": self.skipped_busy_count,
            "meta_answered": self.meta_answered_count,
        }
