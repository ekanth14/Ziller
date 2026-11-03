"""Consensus and Multi-Agent Decision Synthesizer.

Aggregates adversarial Bull vs Bear debate and Tri-Perspective Risk debate into a unified
institutional conviction score (-100 to +100) and actionable execution directive.
"""
from typing import Any, Dict, List, Optional
from cryptoscope.agents.researchers.bull_researcher import BullResearcher
from cryptoscope.agents.researchers.bear_researcher import BearResearcher
from cryptoscope.agents.risk.tri_debate import run_tri_risk_debate
from cryptoscope.simulation.time_machine import simulate_trade_odds


class DeliberationConsensusEngine:
    """Orchestrates adversarial multi-agent debate and compiles institutional consensus."""

    def __init__(self):
        self.bull_agent = BullResearcher()
        self.bear_agent = BearResearcher()

    def deliberate_combined(
        self,
        symbol: str,
        direction: str,
        entry: float,
        stop: float,
        target: float,
        indicators: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execute ONE combined multi-agent adversarial debate (Bull, Bear, Risk Moderator in one call).

        Strict fail-closed: If LLM call times out, encounters an error, or returns invalid JSON,
        verdict defaults to REJECT and action defaults to STAND_ASIDE.
        """
        import os, json, urllib.request, time, logging
        log = logging.getLogger("cryptoscope.agents.consensus")
        t0 = time.perf_counter()

        model_name = model or os.environ.get("OLLAMA_DEBATE_MODEL", "gemma4:12b")
        deadline = timeout_sec or float(os.environ.get("DEBATE_TIMEOUT_SEC", "35.0"))
        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")

        ind = indicators or {}
        context_str = ", ".join(f"{k}={v}" for k, v in ind.items() if not isinstance(v, (list, dict)))

        system_prompt = (
            "You are an institutional quantitative crypto debate committee. "
            "Deliberate the proposed trade from Bull, Bear, and Risk Moderator perspectives simultaneously. "
            "Respond STRICTLY in JSON format with exactly these keys: "
            "bull_thesis (string, max 15 words), "
            "bear_thesis (string, max 15 words), "
            "risk_verdict (string: APPROVE or VETO), "
            "conviction (integer 1 to 10), "
            "consensus_action (string: BUY, SELL, or STAND_ASIDE), "
            "reason (string, max 15 words)."
        )

        user_prompt = (
            f"PROPOSED TRADE:\n"
            f"Symbol: {symbol} | Direction: {direction} | Entry: {entry} | Stop: {stop} | Target: {target}\n"
            f"Context: {context_str}\n\n"
            f"JSON OUTPUT:"
        )

        payload = {
            "model": model_name,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "think": False,
            "format": "json",
            "stream": False,
            "keep_alive": "15m",
            "options": {
                "temperature": 0.0,
                "num_predict": 140,
            }
        }

        try:
            req = urllib.request.Request(
                f"{host}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=deadline) as resp:
                raw_json = json.loads(resp.read().decode("utf-8"))

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            response_text = raw_json.get("response", "")
            parsed = json.loads(response_text)

            required_keys = ["bull_thesis", "bear_thesis", "risk_verdict", "conviction", "consensus_action", "reason"]
            if not all(k in parsed for k in required_keys):
                raise ValueError(f"Incomplete JSON keys from model: {list(parsed.keys())}")

            conv = float(parsed["conviction"])
            action = str(parsed["consensus_action"]).upper()
            risk_v = str(parsed["risk_verdict"]).upper()

            # Fail-closed validation
            if action not in {"BUY", "SELL", "STAND_ASIDE"}:
                action = "STAND_ASIDE"
            if risk_v not in {"APPROVE", "VETO"}:
                risk_v = "VETO"

            is_approved = (risk_v == "APPROVE" and action in {"BUY", "SELL"} and conv >= 6.0)

            return {
                "symbol": symbol,
                "action": action if is_approved else "STAND_ASIDE",
                "verdict": "APPROVE" if is_approved else "REJECT",
                "risk_verdict": risk_v,
                "conviction_score": conv,
                "bull_thesis": parsed.get("bull_thesis", ""),
                "bear_thesis": parsed.get("bear_thesis", ""),
                "reason": parsed.get("reason", ""),
                "latency_ms": round(elapsed_ms, 2),
                "fallback_used": False,
                "model": model_name,
            }

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            log.warning("Debate LLM failed/timed out (%s). Failing closed to STAND_ASIDE.", exc)
            return {
                "symbol": symbol,
                "action": "STAND_ASIDE",
                "verdict": "REJECT",
                "risk_verdict": "VETO",
                "conviction_score": 0.0,
                "bull_thesis": "Inference unavailable/timed out",
                "bear_thesis": str(exc),
                "reason": f"Fail-closed fallback: {exc}",
                "latency_ms": round(elapsed_ms, 2),
                "fallback_used": True,
                "model": model_name,
            }

    def deliberate(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        candles: Optional[List[Dict[str, Any]]] = None,
        order_blocks: Optional[List[Dict[str, Any]]] = None,
        balance: float = 10000.0,
        provider: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute full adversarial debate and return consensus verdict."""
        # 1. Round 1: Bull presents thesis
        bull_round1 = self.bull_agent.formulate_thesis(
            symbol=symbol,
            indicators=indicators,
            order_blocks=order_blocks,
            provider=provider,
        )

        # 2. Round 2: Bear presents counter-thesis answering Bull
        bear_round1 = self.bear_agent.formulate_thesis(
            symbol=symbol,
            indicators=indicators,
            order_blocks=order_blocks,
            opponent_argument=bull_round1["thesis"],
            provider=provider,
        )

        # 3. Round 3: Bull rebuts Bear concerns
        bull_round2 = self.bull_agent.formulate_thesis(
            symbol=symbol,
            indicators=indicators,
            order_blocks=order_blocks,
            opponent_argument=bear_round1["thesis"],
            provider=provider,
        )

        close = float(indicators.get("close", 50000.0))
        atr14 = float(indicators.get("atr14", close * 0.02))

        # Setup parameters
        entry = close
        stop = entry - (1.5 * atr14)
        target = entry + (3.0 * atr14)  # 2.0R

        setup = {
            "symbol": symbol,
            "entry_price": entry,
            "stop_loss": stop,
            "take_profit": target,
            "risk_reward_ratio": 2.0,
        }

        # 4. Tri-Risk Governance Debate
        risk_debate = run_tri_risk_debate(setup, balance=balance)

        # 5. Monte Carlo Odds Verification
        sim_odds = simulate_trade_odds(
            symbol=symbol,
            entry=entry,
            stop=stop,
            target=target,
            candles=candles,
            replays=1000,
        )

        # 6. Calculate Institutional Conviction Score (-100 to +100)
        bull_conv = bull_round2.get("conviction", 0.6)
        bear_conv = bear_round1.get("conviction", 0.5)
        win_rate = sim_odds.get("empirical_win_rate", 0.5)

        # Directional Score components:
        # Technical indicators directional (-100 to +100)
        tech_score = float(indicators.get("directional_score", 0.0))

        # Multi-agent balance: (bull_conv - bear_conv) scaled to -50..+50
        agent_score = (bull_conv - bear_conv) * 100.0

        # Monte Carlo edge: (win_rate - 0.50) scaled to -50..+50
        sim_score = (win_rate - 0.50) * 100.0

        composite_conviction = (0.40 * tech_score) + (0.35 * agent_score) + (0.25 * sim_score)
        composite_conviction = max(-100.0, min(100.0, composite_conviction))

        # 7. Action Directive
        if composite_conviction >= 25.0 and sim_odds.get("verdict_code") in ["STRONG_FAVORABLE", "MODERATE_FAVORABLE"]:
            action = "BUY"
            verdict = "APPROVED (High-Conviction Long Alignment)"
        elif composite_conviction <= -25.0:
            action = "SELL"
            verdict = "APPROVED (High-Conviction Short Alignment)"
        else:
            action = "STAND_ASIDE"
            verdict = "STAND ASIDE (Conflicting Signals / Insufficient Edge)"

        return {
            "symbol": symbol,
            "action": action,
            "verdict": verdict,
            "conviction_score": round(composite_conviction, 2),
            "bull_thesis": bull_round2["thesis"],
            "bull_evidence": bull_round2["evidence"],
            "bear_thesis": bear_round1["thesis"],
            "bear_evidence": bear_round1["evidence"],
            "risk_debate": risk_debate,
            "simulation_odds": {
                "empirical_win_rate": sim_odds.get("empirical_win_rate"),
                "expected_r": sim_odds.get("expected_r"),
                "verdict": sim_odds.get("verdict"),
            },
            "trade_parameters": {
                "entry": round(entry, 4),
                "stop_loss": round(stop, 4),
                "take_profit": round(target, 4),
                "approved_risk_pct": risk_debate["approved_risk_pct"],
                "max_position_size": risk_debate["max_position_size"],
            },
        }
