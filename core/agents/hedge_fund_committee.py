"""Async Multi-Agent Hedge Fund Deliberation Committee.

Systemizes institutional investment committee deliberation inspired by:
- virattt/ai-hedge-fund
- TauricResearch/TradingAgents
- xbtlin/ai-berkshire

Personas:
1. Jim Simons (Quant & Stat-Arb): Evaluates factor z-scores, momentum, volatility persistence.
2. Cathie Wood (Disruptive Growth): Evaluates momentum acceleration, volume surges, breakout strength.
3. Warren Buffett & Li Lu (Value, Moat & Governance): Audits network moats, intrinsic value, margin of safety, and governance integrity via BerkshireCommittee.
4. Risk Officer (Deterministic Risk Gates): Strict veto power over VaR breaches, drawdown limits, and margin/liquidation proximity.
5. Portfolio Arbiter (Consensus Aggregator): Aggregates votes into final action, conviction score, sizing, and synthesis memo.
"""

import asyncio
from dataclasses import dataclass, field
import json
import time
from typing import Any, Mapping
from core.quant.berkshire_committee import BerkshireCommittee


@dataclass
class PersonaVote:
    persona: str
    action: str  # "BUY", "SELL", "HOLD"
    confidence: float  # 0.0 to 1.0
    weight: float
    thesis: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommitteeDecision:
    symbol: str
    action: str  # "BUY", "SELL", "HOLD"
    conviction_score: float  # 0.0 to 1.0
    suggested_sizing_pct: float  # 0.0 to 1.0
    risk_veto: bool
    risk_veto_reason: str | None
    persona_votes: list[PersonaVote]
    synthesis_memo: str
    timestamp: float


class HedgeFundCommittee:
    """Async Multi-Agent Hedge Fund Deliberation Committee."""

    def __init__(
        self,
        max_var_limit: float = 0.05,
        max_drawdown_limit: float = 0.15,
        min_liquidation_distance: float = 0.10,
        cache_ttl_seconds: float = 30.0,
        berkshire_committee: BerkshireCommittee | None = None,
    ) -> None:
        self.max_var_limit = max_var_limit
        self.max_drawdown_limit = max_drawdown_limit
        self.min_liquidation_distance = min_liquidation_distance
        self.cache_ttl_seconds = cache_ttl_seconds
        self.berkshire_committee = berkshire_committee or BerkshireCommittee()
        self._cache: dict[str, tuple[float, CommitteeDecision]] = {}

    def _get_cache_key(self, symbol: str, context: Mapping[str, Any]) -> str:
        try:
            serialized = json.dumps(context, sort_keys=True, default=str)
            return f"{symbol}:{serialized}"
        except Exception:
            return f"{symbol}:{time.time()}"

    async def deliberate(
        self,
        symbol: str,
        market_context: Mapping[str, Any],
    ) -> CommitteeDecision:
        """Asynchronously deliberate on an asset and return committee consensus."""
        cache_key = self._get_cache_key(symbol, market_context)
        now = time.time()
        if cache_key in self._cache:
            cached_time, cached_decision = self._cache[cache_key]
            if (now - cached_time) < self.cache_ttl_seconds:
                return cached_decision

        factors = market_context.get("factors", {})
        berkshire_data = market_context.get("berkshire_data", {})
        risk_metrics = market_context.get("risk_metrics", {})

        # Evaluate all personas
        simons_vote = self._evaluate_jim_simons(factors)
        wood_vote = self._evaluate_cathie_wood(factors)
        buffett_vote = self._evaluate_buffett_lilu(symbol, berkshire_data)
        risk_vote, risk_veto, veto_reason = self._evaluate_risk_officer(risk_metrics)

        all_votes = [simons_vote, wood_vote, buffett_vote, risk_vote]

        decision = self._arbitrate(
            symbol=symbol,
            votes=all_votes,
            risk_veto=risk_veto,
            risk_veto_reason=veto_reason,
            risk_metrics=risk_metrics,
            now=now,
        )

        self._cache[cache_key] = (now, decision)
        return decision

    def deliberate_sync(
        self,
        symbol: str,
        market_context: Mapping[str, Any],
    ) -> CommitteeDecision:
        """Synchronous wrapper for deliberate."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If called from within an active asyncio event loop in tests/harness
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(self.deliberate(symbol, market_context))).result()
        else:
            return asyncio.run(self.deliberate(symbol, market_context))

    def _evaluate_jim_simons(self, factors: Mapping[str, Any]) -> PersonaVote:
        """Jim Simons: Quantitative Factor Edge & Stat-Arb."""
        zscore = float(factors.get("zscore", factors.get("ROC20", 0.0)))
        roc20 = float(factors.get("ROC20", 0.0))
        vol_ratio = float(factors.get("VOL_MA5_RATIO", 1.0))

        if zscore >= 1.0 and vol_ratio >= 1.0:
            action = "BUY"
            confidence = min(0.95, 0.60 + 0.15 * min(2.0, zscore))
            thesis = (
                f"Stat-Arb z-score ({zscore:.2f}) indicates robust momentum persistence with "
                f"volume expansion ({vol_ratio:.2f}x). Favorable predictive distribution."
            )
        elif zscore <= -1.0:
            action = "SELL"
            confidence = min(0.95, 0.60 + 0.15 * min(2.0, abs(zscore)))
            thesis = (
                f"Stat-Arb z-score ({zscore:.2f}) breached negative threshold. Distribution skew "
                f"favors risk reduction or short positioning."
            )
        else:
            action = "HOLD"
            confidence = 0.50
            thesis = (
                f"Quantitative factor z-score ({zscore:.2f}) within neutral noise bounds (|z| < 1.0). "
                f"Insufficient statistical edge."
            )

        return PersonaVote(
            persona="Jim Simons",
            action=action,
            confidence=confidence,
            weight=0.35,
            thesis=thesis,
            metrics={"zscore": zscore, "roc20": roc20, "vol_ratio": vol_ratio},
        )

    def _evaluate_cathie_wood(self, factors: Mapping[str, Any]) -> PersonaVote:
        """Cathie Wood: Disruptive Growth & Momentum Surge."""
        roc5 = float(factors.get("ROC5", 0.0))
        roc20 = float(factors.get("ROC20", 0.0))
        vol_ratio = float(factors.get("VOL_MA5_RATIO", 1.0))

        if roc5 > 0.03 and vol_ratio > 1.5:
            action = "BUY"
            confidence = min(0.95, 0.70 + 0.10 * min(2.5, vol_ratio))
            thesis = (
                f"Aggressive momentum acceleration (ROC5: +{roc5*100:.1f}%) supported by parabolic "
                f"volume surge ({vol_ratio:.1f}x). Strong disruptive breakout trajectory."
            )
        elif roc5 < -0.05 and vol_ratio > 1.5:
            action = "SELL"
            confidence = 0.75
            thesis = f"Sharp downward momentum breakdown with high volume turnover ({vol_ratio:.1f}x)."
        else:
            action = "HOLD"
            confidence = 0.45
            thesis = "Momentum trajectory is consolidating without clear catalytic volume acceleration."

        return PersonaVote(
            persona="Cathie Wood",
            action=action,
            confidence=confidence,
            weight=0.25,
            thesis=thesis,
            metrics={"roc5": roc5, "roc20": roc20, "vol_ratio": vol_ratio},
        )

    def _evaluate_buffett_lilu(self, symbol: str, berkshire_data: Mapping[str, Any]) -> PersonaVote:
        """Warren Buffett & Li Lu: Moat Durability, DCF Margin of Safety & Governance."""
        audit = self.berkshire_committee.audit_asset(symbol, berkshire_data)
        passed = audit.get("rigor_passed", False)
        score = float(audit.get("composite_conviction_score", 0.0))

        if not passed or score < 40.0:
            action = "HOLD" if not passed else "SELL"
            confidence = 0.30 if not passed else 0.70
            thesis = (
                f"Berkshire moat audit failed or scored low ({score}/100). "
                f"Lacks durable economic fee moats or suffers from centralization/speculation risk."
            )
        elif score >= 70.0:
            action = "BUY"
            confidence = min(0.95, score / 100.0)
            thesis = (
                f"Outstanding economic moat and governance integrity ({score}/100). "
                f"Attractive cash/fee generation with substantial margin of safety."
            )
        else:
            action = "HOLD"
            confidence = score / 100.0
            thesis = (
                f"Fair fundamental valuation ({score}/100). Established utility, "
                f"but valuation provides modest margin of safety."
            )

        return PersonaVote(
            persona="Warren Buffett & Li Lu",
            action=action,
            confidence=confidence,
            weight=0.40,
            thesis=thesis,
            metrics={"berkshire_score": score, "rigor_passed": passed},
        )

    def _evaluate_risk_officer(
        self,
        risk_metrics: Mapping[str, Any],
    ) -> tuple[PersonaVote, bool, str | None]:
        """Risk Officer: Deterministic Risk Gates & Absolute Veto Power."""
        if not risk_metrics:
            return (
                PersonaVote(
                    persona="Risk Officer",
                    action="HOLD",
                    confidence=0.50,
                    weight=1.0,
                    thesis="No risk metrics provided. Precautionary hold.",
                    metrics={},
                ),
                False,
                None,
            )

        var_95 = float(risk_metrics.get("var_95_pct", 0.0))
        drawdown = float(risk_metrics.get("current_drawdown_pct", 0.0))
        liq_distance = float(risk_metrics.get("liquidation_distance_pct", 1.0))
        kelly = float(risk_metrics.get("kelly_fraction", 0.0))

        # Check deterministic gates
        veto_reasons: list[str] = []
        if var_95 > self.max_var_limit:
            veto_reasons.append(f"Parametric VaR95 ({var_95*100:.2f}%) exceeds hard limit ({self.max_var_limit*100:.2f}%)")
        if drawdown > self.max_drawdown_limit:
            veto_reasons.append(f"Current portfolio drawdown ({drawdown*100:.2f}%) breaches max threshold ({self.max_drawdown_limit*100:.2f}%)")
        if liq_distance < self.min_liquidation_distance:
            veto_reasons.append(f"Proximity to liquidation ({liq_distance*100:.2f}%) is dangerously thin (< {self.min_liquidation_distance*100:.2f}%)")
        if kelly <= 0.0:
            veto_reasons.append("Kelly optimal betting fraction is <= 0.0 (negative or zero expectancy)")

        if veto_reasons:
            full_veto_str = "; ".join(veto_reasons)
            vote = PersonaVote(
                persona="Risk Officer",
                action="HOLD",
                confidence=0.0,
                weight=1.0,
                thesis=f"VETO TRIGGERED: {full_veto_str}",
                metrics={"var_95": var_95, "drawdown": drawdown, "liq_distance": liq_distance, "kelly": kelly},
            )
            return vote, True, full_veto_str

        # Safe conditions approved
        safe_sizing = min(0.25, max(0.01, kelly * 0.5))
        vote = PersonaVote(
            persona="Risk Officer",
            action="BUY",
            confidence=1.0,
            weight=1.0,
            thesis=f"All deterministic risk gates passed. Safe allocation ceiling: {safe_sizing*100:.1f}%.",
            metrics={"safe_sizing": safe_sizing, "var_95": var_95, "drawdown": drawdown},
        )
        return vote, False, None

    def _arbitrate(
        self,
        symbol: str,
        votes: list[PersonaVote],
        risk_veto: bool,
        risk_veto_reason: str | None,
        risk_metrics: Mapping[str, Any],
        now: float,
    ) -> CommitteeDecision:
        """Consensus Arbiter synthesizing persona recommendations."""
        if risk_veto:
            memo = (
                f"### Institutional Investment Committee Deliberation: {symbol}\n"
                f"**Consensus Verdict: HOLD (RISK VETO ACTIVE)**\n"
                f"**Veto Reason:** {risk_veto_reason}\n\n"
                f"**Committee Voting Breakdown:**\n"
            )
            for v in votes:
                memo += f"- **{v.persona}**: {v.action} (Confidence: {v.confidence*100:.1f}%) — {v.thesis}\n"
            memo += "\n**Capital Allocation:** 0.0% (Trading locked by Risk Officer)."

            return CommitteeDecision(
                symbol=symbol,
                action="HOLD",
                conviction_score=0.0,
                suggested_sizing_pct=0.0,
                risk_veto=True,
                risk_veto_reason=risk_veto_reason,
                persona_votes=votes,
                synthesis_memo=memo,
                timestamp=now,
            )

        # Calculate voting score among non-risk members
        score_map = {"BUY": 1.0, "HOLD": 0.0, "SELL": -1.0}
        total_weight = 0.0
        weighted_score = 0.0
        weighted_confidence = 0.0

        for v in votes:
            if v.persona == "Risk Officer":
                continue
            total_weight += v.weight
            weighted_score += score_map.get(v.action, 0.0) * v.weight * v.confidence
            weighted_confidence += v.confidence * v.weight

        norm_score = weighted_score / total_weight if total_weight > 0 else 0.0
        avg_confidence = weighted_confidence / total_weight if total_weight > 0 else 0.0

        if norm_score > 0.25:
            final_action = "BUY"
        elif norm_score < -0.25:
            final_action = "SELL"
        else:
            final_action = "HOLD"

        # Calculate suggested sizing using half-Kelly risk ceiling
        kelly = float(risk_metrics.get("kelly_fraction", 0.10)) if risk_metrics else 0.10
        base_size = min(0.25, max(0.02, kelly * 0.5))
        sizing = base_size * avg_confidence if final_action == "BUY" else 0.0

        memo = (
            f"### Institutional Investment Committee Deliberation: {symbol}\n"
            f"**Consensus Verdict: {final_action}** (Conviction: {avg_confidence*100:.1f}%)\n"
            f"**Suggested Capital Allocation:** {sizing*100:.1f}%\n\n"
            f"**Committee Deliberation Summary:**\n"
        )
        for v in votes:
            memo += f"- **{v.persona}**: {v.action} (Confidence: {v.confidence*100:.1f}%) — {v.thesis}\n"

        return CommitteeDecision(
            symbol=symbol,
            action=final_action,
            conviction_score=round(avg_confidence, 3),
            suggested_sizing_pct=round(sizing, 3),
            risk_veto=False,
            risk_veto_reason=None,
            persona_votes=votes,
            synthesis_memo=memo,
            timestamp=now,
        )
