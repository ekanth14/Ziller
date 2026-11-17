"""AI overlay for the Action Desk: runs the project's own decision systems on the latest closed bar.

Systems linked (all in-process, all fed with real candles and the desk's own risk numbers):
- SMC + Laya   : cryptoscope.autotrader.decision.FastDecisionLayer (Tier 1 rules + Laya Tier 2 classifier)
- Committee    : core.agents.hedge_fund_committee.HedgeFundCommittee (personas + risk officer)
- THX-02       : core.agents.thx02_decision_engine.THX02DecisionEngine (inside the committee)
- Ollama       : local LLM explainer (status only; it never votes)

Safety rule: the overlay can only make the desk MORE conservative. It may veto a rule-PM BUY
(turning it into HOLD); it can never create a BUY or increase size on its own.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Sequence

DAY = 86400.0


def _kelly(trades: Sequence[Dict[str, Any]]) -> float:
    """Kelly fraction from the desk's own closed paper trades (0 when there is no evidence)."""
    wins = [t["net_pct"] for t in trades if t["net_pct"] > 0]
    losses = [-t["net_pct"] for t in trades if t["net_pct"] <= 0]
    if not wins or not losses:
        return 0.0
    p = len(wins) / (len(wins) + len(losses))
    b = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
    return max(0.0, p - (1 - p) / b) if b > 0 else 0.0


def _smc_laya(candles: List[Dict[str, Any]], symbol: str, layer, bar_seconds: float = DAY) -> Dict[str, Any]:
    started = time.perf_counter()
    rows = [dict(c, close_time=c["open_time"] + bar_seconds, taker_buy_volume=c.get("taker_buy_volume", 0.0)) for c in candles]
    res = layer.decide(rows, symbol)
    t1, t2 = res["tier1"], res["tier2"]
    action = {"LONG": "BUY", "SHORT": "SELL"}.get(res["final_action"], "HOLD")
    return {
        "key": "smc_laya", "label": "SMC + Laya", "status": "OK", "action": action,
        "tier1": {"action": t1.get("action"), "score": t1.get("score"), "setup": t1.get("setup_type"),
                  "reasons": t1.get("reasons", [])[:4]},
        "tier2": {"status": t2.get("status"), "agreed": t2.get("agreed"), "label": t2.get("label"), "reason": t2.get("reason")},
        "thesis": res.get("thesis"), "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _committee(candles, symbol, desk) -> Dict[str, Any]:
    from core.agents.hedge_fund_committee import HedgeFundCommittee
    from core.agents.thx02_decision_engine import THX02DecisionEngine
    from core.quant.factors.alpha158 import Alpha158FactorEngine

    started = time.perf_counter()
    closes = [c["close"] for c in candles]
    last, prev = candles[-1], candles[-2]
    agents = desk["equity"]["agents"]
    book_dd = agents[-1] / max(agents) - 1 if agents else 0.0
    context = {
        "symbol": symbol,
        "price": last["close"],
        "closes": closes[-120:],
        "factors": Alpha158FactorEngine().compute_latest_features(candles[-120:]),
        # Order-flow is not part of daily klines; passed as neutral rather than invented.
        "order_flow": {"cvd": 0.0, "imbalance": 0.0},
        "market_data": {"price": last["close"], "volume_24h": last["volume"] * last["close"],
                        "change_24h": (last["close"] / prev["close"] - 1) * 100},
        "risk_metrics": {"var_95_pct": abs(desk["risk"]["var95_1d"]), "current_drawdown_pct": abs(book_dd),
                         "liquidation_distance_pct": 1.0,  # spot, no leverage
                         "kelly_fraction": _kelly(desk.get("all_trades", desk["trades"]))},
    }
    d = HedgeFundCommittee(decision_engine=THX02DecisionEngine()).deliberate_sync(symbol, context)
    thx = d.thx02_decision
    return {
        "key": "committee", "label": "Hedge-fund committee", "status": "OK",
        "action": "BUY" if d.action in {"BUY", "LONG"} else "SELL" if d.action in {"SELL", "SHORT"} else "HOLD",
        "raw_action": d.action, "conviction": d.conviction_score, "risk_veto": d.risk_veto,
        "risk_veto_reason": d.risk_veto_reason,
        "personas": [{"persona": v.persona, "action": v.action, "confidence": v.confidence, "weight": v.weight,
                      "thesis": v.thesis} for v in d.persona_votes],
        "thx02": None if thx is None else {"action": thx.action, "regime": thx.regime, "conviction": thx.conviction,
                                           "risk_cleared": thx.risk_cleared, "thought": thx.thought},
        "inputs": {"book_drawdown": book_dd, "var95": context["risk_metrics"]["var_95_pct"],
                   "kelly": context["risk_metrics"]["kelly_fraction"]},
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def ai_overlay(candles: List[Dict[str, Any]], symbol: str, desk: Dict[str, Any], layer=None,
               ollama_status=None, bar_seconds: float = DAY) -> Dict[str, Any]:
    """Run every linked system on closed bars only and combine with the rule PM (veto-only)."""
    systems: List[Dict[str, Any]] = []
    try:
        if layer is None:
            from cryptoscope.autotrader.decision import FastDecisionLayer
            layer = FastDecisionLayer()
        systems.append(_smc_laya(candles, symbol, layer, bar_seconds))
    except Exception as exc:  # one failing system must not take the desk down
        systems.append({"key": "smc_laya", "label": "SMC + Laya", "status": "ERROR", "action": "HOLD", "error": type(exc).__name__})
    try:
        systems.append(_committee(candles, symbol, desk))
    except Exception as exc:
        systems.append({"key": "committee", "label": "Hedge-fund committee", "status": "ERROR", "action": "HOLD", "error": type(exc).__name__})

    pm = desk["decision"]["action"]
    vetoes = []
    if pm == "BUY":
        for s in systems:
            if s["status"] != "OK":
                continue
            if s.get("risk_veto"):
                vetoes.append(f"{s['label']}: {s.get('risk_veto_reason') or 'risk veto'}")
            elif s["action"] == "SELL":
                vetoes.append(f"{s['label']} says SELL")
    final = "HOLD" if vetoes else pm
    return {
        "systems": systems,
        "ollama": ollama_status or {"status": "unknown"},
        "rule_pm": pm,
        "final_action": final,
        "vetoes": vetoes,
        "policy": "AI systems can veto a rule-PM BUY; they never create or enlarge a position.",
    }
