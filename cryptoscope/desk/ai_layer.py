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


def _strategy_indicators(candles: List[Dict[str, Any]]) -> Dict[str, float]:
    closes = [c["close"] for c in candles]

    def ema(n):
        k, out = 2 / (n + 1), closes[0]
        for v in closes[1:]:
            out = k * v + (1 - k) * out
        return out

    gains = losses = 0.0
    for i in range(len(closes) - 14, len(closes)):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    rsi = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
    trs = [max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"]))
           for p, c in zip(candles[-15:-1], candles[-14:])]
    return {"ema20": ema(20), "ema50": ema(50), "rsi14": rsi, "atr14": sum(trs) / len(trs)}


def _strategies(candles: List[Dict[str, Any]], bar_seconds: float) -> Dict[str, Any]:
    """The autotrader strategy library on the same closed bars (stat-arb needs a pair, so it is listed only)."""
    from cryptoscope.autotrader.strategies import (BoxOscillationStrategy, ShrinkPullbackStrategy,
                                                    VolatilityCompressionBreakoutStrategy, VolumeBreakoutStrategy)
    started = time.perf_counter()
    rows = [dict(c, close_time=c["open_time"] + bar_seconds) for c in candles[-200:]]
    ind = _strategy_indicators(rows)
    signals = []
    for strat in (VolumeBreakoutStrategy(), ShrinkPullbackStrategy(), BoxOscillationStrategy(),
                  VolatilityCompressionBreakoutStrategy()):
        name = getattr(strat, "display_name", type(strat).__name__)
        try:
            sig = strat.evaluate(rows, ind)
        except Exception as exc:
            signals.append({"name": name, "action": "ERROR", "reason": type(exc).__name__})
            continue
        side = (sig or {}).get("side")
        signals.append({"name": name, "action": side if side in {"BUY", "SELL"} else "NONE",
                        "confidence": (sig or {}).get("confidence"), "reason": (sig or {}).get("reason")})
    acts = [x["action"] for x in signals]
    action = "SELL" if "SELL" in acts else "BUY" if "BUY" in acts else "HOLD"
    return {"key": "strategies", "label": "Strategy library", "status": "OK", "action": action, "signals": signals,
            "not_run": ["Stat-arb pairs (needs a second symbol)"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 2)}


def ai_overlay(candles: List[Dict[str, Any]], symbol: str, desk: Dict[str, Any], layer=None,
               ollama_status=None, bar_seconds: float = DAY, llm_panel=None, interval: str = "1d") -> Dict[str, Any]:
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
    try:
        systems.append(_strategies(candles, bar_seconds))
    except Exception as exc:
        systems.append({"key": "strategies", "label": "Strategy library", "status": "ERROR", "action": "HOLD", "error": type(exc).__name__})
    llm = None
    if llm_panel is not None:
        try:
            llm = llm_panel.request(symbol, interval, candles[-1]["open_time"], desk)
            if llm.get("halted"):
                llm["note"] = "paused: kill switch engaged or the autotrader fleet is using Ollama"
            if llm["panel_action"]:
                systems.append({"key": "llm_panel", "label": f"LLM panel ({llm['ready']}/{llm['total']})", "status": "OK",
                                "action": llm["panel_action"], "detail": "majority of answered local models"})
        except Exception as exc:
            llm = {"available": False, "error": type(exc).__name__, "models": []}

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
        "llm": llm,
        "rule_pm": pm,
        "final_action": final,
        "vetoes": vetoes,
        "policy": "AI systems can veto a rule-PM BUY; they never create or enlarge a position.",
    }
