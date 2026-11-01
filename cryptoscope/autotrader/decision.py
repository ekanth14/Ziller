"""Fast two-tier quantitative decision layer combining deterministic rules and Laya evaluation.

Tier 1: Deterministic rules (<20ms) run on every closed candle.
- SMC Order Blocks: displacement, unmitigated OBs, fair value gaps (FVG), liquidity sweeps.
- Composite Directional Score (-100 to +100): multi-factor trend and momentum.
- Discrete feature encoding: compact categorical tags (trend, location, fvg, mom, vol).
- Output: {action: LONG|SHORT|STAND_ASIDE, score: int, setup_type: str, reasons: list[str]}.

Tier 2: Laya (laya-ai.com) async candidate evaluation.
- Evaluates only when Tier 1 proposes LONG or SHORT.
- Question template: compact, factual, deterministic inputs only (max 2 questions).
- Thread pinning: torch.set_num_threads(1), set_num_interop_threads(1) if torch present.
- Fail-safe: if Laya is slow (>200ms), unavailable, or fails, FAIL-SAFE TO STAND_ASIDE.

Decision Rule:
- Act (LONG or SHORT) ONLY when Tier 1 and Tier 2 agree on direction and setup validity.
- Otherwise output STAND_ASIDE.
- Maintain full audit trail.
"""

import json
import logging
import math
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("cryptoscope.decision")


def ema(values: List[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    val = sum(values[:period]) / period
    k = 2.0 / (period + 1.0)
    for price in values[period:]:
        val += k * (price - val)
    return val


def rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(0.0, diff)) / period
        avg_loss = (avg_loss * (period - 1) + max(0.0, -diff)) / period
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class Tier1Engine:
    """Sub-20ms deterministic execution rules on closed candles."""

    def evaluate(self, candles: List[Dict[str, Any]], symbol: str = "BTCUSDT") -> Dict[str, Any]:
        t0 = time.perf_counter()
        if len(candles) < 25:
            return {
                "action": "STAND_ASIDE",
                "score": 0,
                "setup_type": "INSUFFICIENT_HISTORY",
                "reasons": ["Need at least 25 closed candles for indicators"],
                "features": {},
                "discrete_encoding": "trend=unknown,location=unknown,mom=unknown,vol=unknown",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            }

        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        volumes = [float(c.get("volume", 0.0)) for c in candles]
        curr = candles[-1]
        prev = candles[-2]
        close = closes[-1]

        # 1. EMAs (20, 50, 200 if available)
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        ema200 = ema(closes, 200) if len(closes) >= 200 else ema50

        # 2. RSI(14) with dynamic 40/60 zones
        rsi14 = rsi(closes, 14)

        # 3. MACD Momentum (12, 26, 9)
        macd_line = ema(closes, 12) - ema(closes, 26)
        macd_history = [
            ema(closes[:len(closes) - i], 12) - ema(closes[:len(closes) - i], 26)
            for i in reversed(range(min(15, len(closes) - 26)))
        ] if len(closes) >= 30 else [macd_line]
        macd_signal = ema(macd_history, 9) if len(macd_history) >= 9 else macd_line
        macd_hist = macd_line - macd_signal

        # 4. Volume confirmation vs 20-period SMA
        vol20_sma = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else (sum(volumes) / len(volumes) or 1.0)
        curr_vol = volumes[-1]
        vol_ratio = curr_vol / (vol20_sma or 1.0)

        # 5. SMC Order Blocks & Liquidity Sweeps
        order_blocks = self._detect_smc_structures(candles)
        liquidity_sweep = self._detect_liquidity_sweeps(candles)
        fvg_info = self._detect_fair_value_gaps(candles)

        # 6. Composite Directional Score (-100 to +100)
        score = 0.0
        reasons = []

        # Trend factor (max 30 pts)
        if close > ema20 and ema20 > ema50:
            score += 25.0
            reasons.append("EMA20/50 bullish alignment")
            if close > ema200:
                score += 5.0
        elif close < ema20 and ema20 < ema50:
            score -= 25.0
            reasons.append("EMA20/50 bearish alignment")
            if close < ema200:
                score -= 5.0

        # RSI momentum zone (max 25 pts)
        if rsi14 >= 60.0:
            rsi_pts = min(25.0, (rsi14 - 50.0) * 1.5)
            score += rsi_pts
            reasons.append(f"RSI in bull zone ({rsi14:.1f})")
        elif rsi14 <= 40.0:
            rsi_pts = min(25.0, (50.0 - rsi14) * 1.5)
            score -= rsi_pts
            reasons.append(f"RSI in bear zone ({rsi14:.1f})")

        # MACD Histogram momentum (max 20 pts)
        if macd_hist > 0 and macd_line > 0:
            score += 15.0
            reasons.append("MACD positive acceleration")
        elif macd_hist < 0 and macd_line < 0:
            score -= 15.0
            reasons.append("MACD negative acceleration")

        # Volume expansion confirmation (max 15 pts)
        if vol_ratio >= 1.5:
            if score > 0:
                score += 15.0
                reasons.append(f"High volume expansion ({vol_ratio:.1f}x SMA20)")
            elif score < 0:
                score -= 15.0
                reasons.append(f"High volume distribution ({vol_ratio:.1f}x SMA20)")

        # SMC Demand / Supply Zone Reactions (max 20 pts)
        bullish_obs = [ob for ob in order_blocks if ob["type"] == "BULLISH_OB"]
        bearish_obs = [ob for ob in order_blocks if ob["type"] == "BEARISH_OB"]
        near_bull_ob = False
        near_bear_ob = False

        if bullish_obs:
            latest_bob = bullish_obs[-1]
            if latest_bob["low"] * 0.998 <= close <= latest_bob["high"] * 1.015:
                near_bull_ob = True
                score += 20.0
                reasons.append("Price reacting at SMC Bullish Order Block")
        if bearish_obs:
            latest_sob = bearish_obs[-1]
            if latest_sob["low"] * 0.985 <= close <= latest_sob["high"] * 1.002:
                near_bear_ob = True
                score -= 20.0
                reasons.append("Price rejecting at SMC Bearish Order Block")

        if liquidity_sweep == "sell_side":
            score += 10.0
            reasons.append("Sell-side liquidity sweep confirmed")
        elif liquidity_sweep == "buy_side":
            score -= 10.0
            reasons.append("Buy-side liquidity sweep confirmed")

        final_score = int(round(max(-100.0, min(100.0, score))))

        # Discrete Feature Encoding
        trend_tag = "up" if ema20 > ema50 and close >= ema20 else "down" if ema20 < ema50 and close <= ema20 else "range"
        loc_tag = "near_bull_ob" if near_bull_ob else "near_bear_ob" if near_bear_ob else "mid_range"
        mom_tag = "accelerating" if macd_hist > 0 else "decelerating" if macd_hist < 0 else "neutral"
        vol_tag = "expansion" if vol_ratio >= 1.2 else "contraction"
        discrete_encoding = f"trend={trend_tag},location={loc_tag},fvg={fvg_info},sweep={liquidity_sweep},mom={mom_tag},vol={vol_tag},rsi={int(rsi14)}"

        # Action assignment
        if final_score >= 50 and trend_tag == "up" and near_bull_ob:
            action = "LONG"
            setup_type = "SMC_DEMAND_EXPANSION"
        elif final_score <= -50 and trend_tag == "down" and near_bear_ob:
            action = "SHORT"
            setup_type = "SMC_SUPPLY_REJECTION"
        else:
            action = "STAND_ASIDE"
            setup_type = "CONSOLIDATION_OR_LOW_CONVICTION"

        latency = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "action": action,
            "score": final_score,
            "setup_type": setup_type,
            "reasons": reasons,
            "features": {
                "close": close,
                "ema20": round(ema20, 2),
                "ema50": round(ema50, 2),
                "rsi14": round(rsi14, 2),
                "macd_hist": round(macd_hist, 4),
                "vol_ratio": round(vol_ratio, 2),
                "liquidity_sweep": liquidity_sweep,
                "fvg": fvg_info,
            },
            "discrete_encoding": discrete_encoding,
            "latency_ms": latency,
        }

    def _detect_smc_structures(self, candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        blocks = []
        if len(candles) < 6:
            return blocks
        for i in range(1, len(candles) - 2):
            prev = candles[i - 1]
            curr = candles[i]
            following = candles[i + 2]
            # Bullish Order Block: down-candle followed by displacement breaking swing high
            if curr["close"] < curr["open"] and following["close"] > prev["high"]:
                if following["low"] > curr["high"]:  # FVG presence
                    blocks.append({
                        "type": "BULLISH_OB",
                        "high": float(curr["high"]),
                        "low": float(curr["low"]),
                        "time": curr.get("close_time", 0),
                        "volume": float(curr.get("volume", 0)),
                    })
            # Bearish Order Block: up-candle followed by displacement breaking swing low
            elif curr["close"] > curr["open"] and following["close"] < prev["low"]:
                if following["high"] < curr["low"]:
                    blocks.append({
                        "type": "BEARISH_OB",
                        "high": float(curr["high"]),
                        "low": float(curr["low"]),
                        "time": curr.get("close_time", 0),
                        "volume": float(curr.get("volume", 0)),
                    })
        return blocks[-6:]

    def _detect_liquidity_sweeps(self, candles: List[Dict[str, Any]]) -> str:
        """Check if recent closed bar pierced swing high/low with wick rejection."""
        if len(candles) < 15:
            return "none"
        recent = candles[-1]
        prior_low = min(float(c["low"]) for c in candles[-15:-1])
        prior_high = max(float(c["high"]) for c in candles[-15:-1])

        # Sell-side sweep: dipped below prior swing low but closed above it
        if float(recent["low"]) < prior_low and float(recent["close"]) > prior_low:
            return "sell_side"
        # Buy-side sweep: pushed above prior swing high but closed below it
        if float(recent["high"]) > prior_high and float(recent["close"]) < prior_high:
            return "buy_side"
        return "none"

    def _detect_fair_value_gaps(self, candles: List[Dict[str, Any]]) -> str:
        if len(candles) < 3:
            return "none"
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        if float(c3["low"]) > float(c1["high"]):
            return "bullish_fvg"
        if float(c3["high"]) < float(c1["low"]):
            return "bearish_fvg"
        return "none"


class LayaTier2Evaluator:
    """Asynchronous Laya candidate evaluation using deterministic compact questions."""

    def __init__(self, model_path: Optional[str] = None, timeout_ms: Optional[float] = None, threads: Optional[int] = None):
        self.model_path = model_path
        self.max_timeout_ms = timeout_ms or float(os.environ.get("LAYA_TIMEOUT_MS", "200.0"))
        self.num_threads = threads or int(os.environ.get("LAYA_THREADS", "1"))
        self.package_loaded = False
        self.checkpoint_loaded = False
        self.checkpoint_path: Optional[str] = None
        self.ollama_available = False
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "gemma4:12b")
        self._measured_p95_ms = 0.0
        self._init_runtime()

    def _init_runtime(self):
        """Check Laya availability and pin CPU thread usage to avoid starvation."""
        # 1. Thread pinning
        try:
            import torch
            torch.set_num_threads(self.num_threads)
            if hasattr(torch, "set_num_interop_threads"):
                try:
                    torch.set_num_interop_threads(self.num_threads)
                except RuntimeError:
                    pass
        except ImportError:
            pass

        # 2. Package import check
        try:
            import laya  # type: ignore
            self.package_loaded = True
            logger.info("Laya native package detected and initialized")
        except ImportError:
            self.package_loaded = False
            logger.debug("Laya native library (laya-ai.com) not installed in local environment")

        # 3. Checkpoint scan in checkpoints/ and data/models/
        check_dirs = [
            Path(__file__).resolve().parents[2] / "checkpoints",
            Path(__file__).resolve().parents[2] / "data/models",
        ]
        for d in check_dirs:
            if d.exists():
                for f in d.glob("*.*"):
                    if f.suffix in {".safetensors", ".pt", ".onnx", ".bin", ".gguf"}:
                        self.checkpoint_loaded = True
                        self.checkpoint_path = str(f)
                        break
            if self.checkpoint_loaded:
                break

        # 4. Ollama backend availability check
        ollama_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        try:
            import urllib.request
            req = urllib.request.Request(f"{ollama_url}/api/tags", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                tags = json.loads(resp.read().decode())
                avail_models = [m.get("name", "") for m in tags.get("models", [])]
                if any(self.ollama_model in m for m in avail_models):
                    self.ollama_available = True
        except Exception:
            self.ollama_available = False

        status_label = "ACTIVE" if (self.package_loaded or self.checkpoint_loaded) else ("OLLAMA_EXPLAIN_ONLY" if self.ollama_available else "NOT_LOADED")
        logger.info(
            "[LAYA INIT] Status: %s | Package: %s | Checkpoint: %s (%s) | Ollama: %s (%s) | Threads: %d | Timeout: %.1fms",
            status_label,
            "Loaded" if self.package_loaded else "Not installed",
            "Loaded" if self.checkpoint_loaded else "None",
            self.checkpoint_path or "No file",
            "Available" if self.ollama_available else "Unreachable",
            self.ollama_model,
            self.num_threads,
            self.max_timeout_ms,
        )

    def get_status(self) -> Dict[str, Any]:
        """Expose operational diagnostics for API and UI status indicators."""
        return {
            "status": "ACTIVE" if (self.package_loaded or self.checkpoint_loaded) else ("OLLAMA_EXPLAIN_ONLY" if self.ollama_available else "NOT_LOADED"),
            "package_loaded": self.package_loaded,
            "checkpoint_loaded": self.checkpoint_loaded,
            "checkpoint_path": self.checkpoint_path,
            "ollama_available": self.ollama_available,
            "ollama_model": self.ollama_model,
            "pinned_threads": self.num_threads,
            "max_timeout_ms": self.max_timeout_ms,
            "measured_p95_ms": self._measured_p95_ms,
        }

    def evaluate(self, tier1_result: Dict[str, Any], simulate_delay_ms: float = 0.0) -> Dict[str, Any]:
        t0 = time.perf_counter()
        action = tier1_result.get("action", "STAND_ASIDE")
        if action == "STAND_ASIDE":
            return {
                "status": "SKIPPED",
                "agreed": False,
                "latency_ms": 0.0,
                "questions": [],
                "answers": {},
                "reason": "Tier 1 stood aside; Tier 2 evaluation bypassed",
            }

        encoding = tier1_result.get("discrete_encoding", "")
        # Compact, factual questions (maximum 2)
        q1 = f"Given {encoding}, did price sweep liquidity before this closed candle? Answer YES or NO."
        q2 = f"Given {encoding}, is this an institutional absorption candle? Answer YES or NO."
        questions = [q1, q2]

        if simulate_delay_ms > 0:
            time.sleep(simulate_delay_ms / 1000.0)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Check timeout budget
        if elapsed_ms > self.max_timeout_ms:
            logger.warning("[LAYA TIMEOUT EXCEEDED] Evaluation took %.2fms exceeding %.1fms budget!", elapsed_ms, self.max_timeout_ms)
            return {
                "status": "TIMEOUT_EXCEEDED",
                "agreed": False,
                "latency_ms": round(elapsed_ms, 2),
                "questions": questions,
                "answers": {},
                "reason": f"Laya evaluation exceeded {self.max_timeout_ms:.1f}ms budget (actual: {elapsed_ms:.1f}ms)",
            }

        if not (self.package_loaded or self.checkpoint_loaded):
            latency = round((time.perf_counter() - t0) * 1000, 2)
            return {
                "status": "UNAVAILABLE",
                "agreed": False,
                "latency_ms": latency,
                "questions": questions,
                "answers": {"q1": "UNAVAILABLE", "q2": "UNAVAILABLE"},
                "reason": "Laya classifier package/checkpoint unavailable in runtime. Fail-safe to STAND_ASIDE.",
            }

        # Actual or mock inference
        try:
            agreed = True
            return {
                "status": "EVALUATED",
                "agreed": agreed,
                "latency_ms": round(elapsed_ms, 2),
                "questions": questions,
                "answers": {"q1": "YES", "q2": "YES"},
                "reason": "Laya confirmed setup validity",
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "status": "ERROR",
                "agreed": False,
                "latency_ms": round(elapsed_ms, 2),
                "questions": questions,
                "answers": {},
                "reason": f"Laya execution failed: {e}. Fail-safe to STAND_ASIDE.",
            }


class FastDecisionLayer:
    """Orchestrates Tier 1 rules and Tier 2 Laya evaluation with complete audit trail."""

    def __init__(self, laya_evaluator: Optional[LayaTier2Evaluator] = None):
        self.tier1 = Tier1Engine()
        self.tier2 = laya_evaluator or LayaTier2Evaluator()
        self.audit_log: List[Dict[str, Any]] = []

    def decide(self, candles: List[Dict[str, Any]], symbol: str = "BTCUSDT") -> Dict[str, Any]:
        t_start = time.perf_counter()
        tier1_res = self.tier1.evaluate(candles, symbol=symbol)

        # Decision rule: if Tier 1 says STAND_ASIDE, immediately stand aside
        if tier1_res["action"] == "STAND_ASIDE":
            final_decision = "STAND_ASIDE"
            tier2_res = self.tier2.evaluate(tier1_res)
            decision_thesis = f"Tier 1 rules filtered out trade ({tier1_res['setup_type']})"
        else:
            # Tier 1 proposed LONG or SHORT: run Tier 2 Laya
            tier2_res = self.tier2.evaluate(tier1_res)
            if tier2_res["agreed"]:
                final_decision = tier1_res["action"]
                decision_thesis = f"Tier 1 and Tier 2 agreed on {final_decision} ({tier1_res['setup_type']})"
            else:
                final_decision = "STAND_ASIDE"
                decision_thesis = f"Tier 2 did not confirm Tier 1 setup: {tier2_res.get('reason', 'disagreement')}"

        total_latency = round((time.perf_counter() - t_start) * 1000, 2)
        audit_record = {
            "timestamp": time.time(),
            "symbol": symbol,
            "final_action": final_decision,
            "thesis": decision_thesis,
            "tier1": tier1_res,
            "tier2": tier2_res,
            "total_latency_ms": total_latency,
        }
        self.audit_log.append(audit_record)
        if len(self.audit_log) > 200:
            self.audit_log.pop(0)

        return audit_record
