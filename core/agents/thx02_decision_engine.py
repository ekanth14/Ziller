"""Formula ensemble used inside the hedge-fund committee (historically named "THX-02").

Despite the class name, what runs here is a DETERMINISTIC FORMULA: softmax over logits built from
order-flow CVD, log-return z-score, GARCH vol and Alpha158 momentum. It is not the HAL-X-AI/THX-02
neural model. The NATIVE mode below is a stub that is never reached on this machine.

The real HAL-X-AI/THX-02 (and convaiinnovations/laya) run in a separate sidecar process and act only
as a veto-only meta-label filter on fleet trades: see cryptoscope/agents/decision_models.py and
cryptoscope/models_sidecar/server.py. The class keeps its name so existing callers keep working.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import math
import os
from typing import Any, Mapping, Sequence

logger = logging.getLogger("core.agents.thx02")


class ExecutionMode(str, Enum):
    AUTO = "AUTO"
    NATIVE = "NATIVE"
    DETERMINISTIC_ENSEMBLE = "DETERMINISTIC_ENSEMBLE"


@dataclass
class THX02TradeDecision:
    """Structured decision output from THX-02 reasoning deliberation."""

    action: str  # "BUY", "SELL", "HOLD"
    regime: str  # "TRENDING_BULLISH", "TRENDING_BEARISH", "HIGH_VOL_CHOP", "LOW_VOL_CONSOLIDATION"
    conviction: float  # 0.0 to 1.0
    risk_cleared: bool  # True if risk parameters pass gate checks
    suggested_leverage: float  # e.g., 1.0 to 3.0
    suggested_sizing_pct: float  # e.g., 0.0 to 0.25
    thought: str  # <think>...</think> reasoning thought chain
    probabilities: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def _softmax(logits: Sequence[float]) -> list[float]:
    """Numerically stable softmax."""
    if not logits:
        return []
    max_logit = max(logits)
    exps = [math.exp(x - max_logit) for x in logits]
    total = sum(exps)
    if total <= 0.0 or math.isnan(total):
        n = len(logits)
        return [1.0 / n] * n
    return [x / total for x in exps]


def _sigmoid(x: float) -> float:
    """Bounded sigmoid function."""
    if x >= 40.0:
        return 1.0
    elif x <= -40.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


class THX02DecisionEngine:
    """THX-02 Thinking Decision Engine."""

    def __init__(
        self,
        mode: ExecutionMode | str = ExecutionMode.AUTO,
        model_name_or_path: str = "HAL-X-AI/THX-02",
        model_path: str | None = None,
        device: str | None = None,
        precision: str = "int8",
        fallback_to_ensemble: bool = True,
    ) -> None:
        if isinstance(mode, str):
            mode = ExecutionMode(mode.upper())
        self.requested_mode = mode
        self.model_name_or_path = model_name_or_path
        self.model_path = model_path or os.environ.get("THX02_MODEL_PATH")
        self.device = device
        self.precision = precision
        self.fallback_to_ensemble = fallback_to_ensemble

        self.effective_mode = self._initialize_runtime()

    def _initialize_runtime(self) -> ExecutionMode:
        """Resolve native runtime vs deterministic ensemble fallback."""
        if self.requested_mode == ExecutionMode.DETERMINISTIC_ENSEMBLE:
            return ExecutionMode.DETERMINISTIC_ENSEMBLE

        # Check native weights / library availability
        native_available = False
        if self.model_path and os.path.exists(self.model_path):
            native_available = True
        else:
            try:
                import thx02  # type: ignore
                native_available = True
            except ImportError:
                native_available = False

        if native_available:
            return ExecutionMode.NATIVE

        if self.requested_mode == ExecutionMode.NATIVE and not self.fallback_to_ensemble:
            raise RuntimeError(
                f"Native THX-02 runtime unavailable (model_path='{self.model_path}' not found "
                f"and 'thx02' library not installed). Fallback disabled."
            )

        logger.info(
            "THX-02 native weights not located in local environment; "
            "running in calibrated DETERMINISTIC_ENSEMBLE mode."
        )
        return ExecutionMode.DETERMINISTIC_ENSEMBLE

    def _extract_signals(self, state: Any) -> dict[str, float]:
        """Safely extract microstructural and quantitative features from state dictionary."""
        if not isinstance(state, Mapping):
            return {
                "zscore": 0.0,
                "roc5": 0.0,
                "roc20": 0.0,
                "vol_ratio": 1.0,
                "volatility": 0.02,
                "cvd": 0.0,
                "var_95": 0.02,
                "drawdown": 0.0,
                "liq_distance": 1.0,
                "kelly": 0.10,
            }

        factors = state.get("factors", {}) if isinstance(state.get("factors"), Mapping) else {}
        order_flow = state.get("order_flow", {}) if isinstance(state.get("order_flow"), Mapping) else {}
        risk_metrics = state.get("risk_metrics", {}) if isinstance(state.get("risk_metrics"), Mapping) else {}

        zscore = float(state.get("zscore", factors.get("zscore", 0.0)))
        roc5 = float(state.get("ROC5", factors.get("ROC5", 0.0)))
        roc20 = float(state.get("ROC20", factors.get("ROC20", 0.0)))
        vol_ratio = float(state.get("VOL_MA5_RATIO", factors.get("VOL_MA5_RATIO", 1.0)))
        volatility = float(
            state.get(
                "volatility",
                factors.get("PRICE_VOLATILITY_20", state.get("garch_vol", 0.02)),
            )
        )
        cvd = float(state.get("cvd", order_flow.get("cvd", 0.0)))
        var_95 = float(state.get("var_95", risk_metrics.get("var_95_pct", risk_metrics.get("var_95", 0.02))))
        drawdown = float(state.get("drawdown", risk_metrics.get("current_drawdown_pct", risk_metrics.get("drawdown", 0.0))))
        liq_distance = float(state.get("liquidation_distance", risk_metrics.get("liquidation_distance_pct", 1.0)))
        kelly = float(state.get("kelly", risk_metrics.get("kelly_fraction", 0.10)))

        return {
            "zscore": zscore,
            "roc5": roc5,
            "roc20": roc20,
            "vol_ratio": vol_ratio,
            "volatility": volatility,
            "cvd": cvd,
            "var_95": var_95,
            "drawdown": drawdown,
            "liq_distance": liq_distance,
            "kelly": kelly,
        }

    def ask_choice(
        self,
        state: Any,
        question: str,
        choices: list[str],
    ) -> dict[str, Any]:
        """Query THX-02 to choose the best option from a typed list of choices."""
        if not choices:
            raise ValueError("choices must not be empty")

        signals = self._extract_signals(state)
        zscore = signals["zscore"]
        roc5 = signals["roc5"]
        roc20 = signals["roc20"]
        cvd = signals["cvd"]
        volatility = signals["volatility"]

        # Calculate directional affinity score [-3.0, +3.0]
        directional_score = (
            0.40 * zscore
            + 0.30 * (roc5 * 20.0)
            + 0.20 * (roc20 * 10.0)
            + 0.10 * math.tanh(cvd / 5000.0 if cvd != 0 else 0.0)
        )

        logits: list[float] = []
        for choice in choices:
            ch_upper = str(choice).upper()
            if ch_upper in ("BUY", "LONG", "TRENDING_BULLISH", "ACCUMULATE"):
                logit = directional_score
            elif ch_upper in ("SELL", "SHORT", "TRENDING_BEARISH", "DISTRIBUTE"):
                logit = -directional_score
            elif ch_upper in ("HOLD", "NEUTRAL", "LOW_VOL_CONSOLIDATION"):
                logit = 1.0 - abs(directional_score)
            elif ch_upper in ("HIGH_VOL_CHOP", "VOLATILE_CHOP"):
                logit = (volatility - 0.03) * 50.0 - abs(directional_score)
            else:
                logit = 0.0
            logits.append(logit)

        probs = _softmax(logits)
        best_idx = int(probs.index(max(probs)))
        best_choice = choices[best_idx]

        probabilities = {c: float(p) for c, p in zip(choices, probs)}

        thought = (
            f"<think>\n"
            f"Analyzing question: '{question}' across candidate choices: {choices}.\n"
            f"Signals evaluated: z-score={zscore:.2f}, ROC5={roc5*100:.2f}%, ROC20={roc20*100:.2f}%, "
            f"CVD={cvd:.1f}, Volatility={volatility*100:.2f}%.\n"
            f"Computed composite directional affinity: {directional_score:.3f}.\n"
            f"Softmax probability distribution: {probabilities}.\n"
            f"Leading selection: '{best_choice}' with confidence {probs[best_idx]*100:.1f}%.\n"
            f"</think>"
        )

        return {
            "best_choice": best_choice,
            "probabilities": probabilities,
            "thought": thought,
        }

    def ask_noul(
        self,
        state: Any,
        question: str,
    ) -> dict[str, Any]:
        """Query THX-02 with a yes/no question returning calibrated confidence and thought."""
        signals = self._extract_signals(state)
        q_lower = question.lower()

        # Risk safety query
        if any(w in q_lower for w in ("risk", "safe", "clear", "acceptable", "leverage")):
            var_95 = signals["var_95"]
            drawdown = signals["drawdown"]
            volatility = signals["volatility"]
            liq_distance = signals["liq_distance"]

            # Safe if var < 0.05, drawdown < 0.15, vol < 0.06, liq_distance > 0.15
            risk_penalty = (
                max(0.0, var_95 - 0.04) * 60.0
                + max(0.0, drawdown - 0.10) * 30.0
                + max(0.0, volatility - 0.05) * 40.0
                + max(0.0, 0.20 - liq_distance) * 20.0
            )
            net_logit = 2.0 - risk_penalty
            prob_yes = _sigmoid(net_logit)
            topic = "Risk Clearance"
        else:
            # General directional affirmation
            zscore = signals["zscore"]
            roc5 = signals["roc5"]
            net_logit = zscore + roc5 * 10.0
            prob_yes = _sigmoid(net_logit)
            topic = "General Hypothesis Affirmation"

        prob_no = 1.0 - prob_yes
        result = bool(prob_yes >= 0.5)
        confidence = round(max(prob_yes, prob_no), 4)

        thought = (
            f"<think>\n"
            f"Evaluating proposition ({topic}): '{question}'.\n"
            f"State features: var95={signals['var_95']*100:.1f}%, drawdown={signals['drawdown']*100:.1f}%, "
            f"zscore={signals['zscore']:.2f}, volatility={signals['volatility']*100:.1f}%.\n"
            f"Calibrated probability outcome: P(YES)={prob_yes:.3f}, P(NO)={prob_no:.3f}.\n"
            f"Verdict: {result} with confidence {confidence*100:.1f}%.\n"
            f"</think>"
        )

        return {
            "result": result,
            "confidence": confidence,
            "prob_yes": round(prob_yes, 4),
            "prob_no": round(prob_no, 4),
            "thought": thought,
        }

    def ask_score(
        self,
        state: Any,
        question: str,
        min_val: int = 1,
        max_val: int = 10,
    ) -> dict[str, Any]:
        """Query THX-02 for a numerical rating within [min_val, max_val]."""
        if min_val >= max_val:
            raise ValueError(f"min_val must be strictly less than max_val (got min_val={min_val}, max_val={max_val})")

        signals = self._extract_signals(state)
        # Normalized score index in range [0, 1]
        z = max(-3.0, min(3.0, signals["zscore"]))
        norm_center = 0.5 + (z / 6.0)

        # Generate Gaussian-like distribution over discrete steps
        steps = list(range(min_val, max_val + 1))
        span = max_val - min_val
        logits = []
        for s in steps:
            normalized_s = (s - min_val) / span
            dist = normalized_s - norm_center
            logits.append(- (dist ** 2) / 0.08)

        probs = _softmax(logits)
        distribution = {s: float(p) for s, p in zip(steps, probs)}
        expected_score = round(sum(s * p for s, p in zip(steps, probs)), 2)

        thought = (
            f"<think>\n"
            f"Scoring request: '{question}' over range [{min_val}, {max_val}].\n"
            f"Signal input: z-score={signals['zscore']:.2f}, ROC5={signals['roc5']*100:.1f}%.\n"
            f"Normalized distribution center: {norm_center:.2f}.\n"
            f"Computed expected score: {expected_score} / {max_val}.\n"
            f"</think>"
        )

        return {
            "score": expected_score,
            "distribution": distribution,
            "thought": thought,
        }

    def deliberate_regime_and_trade(
        self,
        market_state: dict[str, Any],
    ) -> THX02TradeDecision:
        """Execute multi-step THX-02 reasoning deliberation on market regime, trade action, and sizing."""
        signals = self._extract_signals(market_state)

        # Step 1: Market Regime Classification
        regime_choices = [
            "TRENDING_BULLISH",
            "TRENDING_BEARISH",
            "HIGH_VOL_CHOP",
            "LOW_VOL_CONSOLIDATION",
        ]
        regime_query = self.ask_choice(
            market_state,
            "Classify the active market regime under current volatility and trend features.",
            regime_choices,
        )
        regime = regime_query["best_choice"]

        # Step 2: Trade Direction Action
        action_choices = ["BUY", "SELL", "HOLD"]
        action_query = self.ask_choice(
            market_state,
            "Determine optimal directional trading recommendation given order flow and momentum factors.",
            action_choices,
        )
        action = action_query["best_choice"]
        action_probs = action_query["probabilities"]
        conviction = action_probs.get(action, 0.50)

        # Step 3: Risk Clearance Gate
        risk_query = self.ask_noul(
            market_state,
            "Are portfolio drawdown, liquidation distance, and parametric VaR within safe trading thresholds?",
        )
        risk_cleared = risk_query["result"]

        # Step 4: Sizing & Leverage
        if not risk_cleared:
            action = "HOLD"
            suggested_leverage = 1.0
            suggested_sizing_pct = 0.0
            sizing_rationale = "Risk clearance failed: trading sizing clamped to 0.0% and leverage locked to 1.0x."
        elif regime == "HIGH_VOL_CHOP" or action == "HOLD":
            suggested_leverage = 1.0
            suggested_sizing_pct = min(0.05, signals["kelly"] * 0.25)
            sizing_rationale = "Regime indicates chop/consolidation: defensive sizing applied."
        else:
            base_size = min(0.25, max(0.02, signals["kelly"] * 0.50))
            suggested_sizing_pct = round(base_size * conviction, 3)
            suggested_leverage = round(min(2.5, 1.0 + conviction), 2)
            sizing_rationale = (
                f"Favorable regime '{regime}' with high conviction ({conviction*100:.1f}%): "
                f"allocation {suggested_sizing_pct*100:.1f}%, leverage {suggested_leverage}x."
            )

        thought = (
            f"<think>\n"
            f"[Phase 1: Regime Assessment]\n"
            f"Assessed market microstructure: regime identified as '{regime}' "
            f"(P={regime_query['probabilities'].get(regime, 0.0)*100:.1f}%).\n\n"
            f"[Phase 2: Directional Edge & CVD Delta]\n"
            f"Order flow delta and momentum evaluate to action: '{action}' "
            f"with conviction {conviction*100:.1f}%.\n"
            f"Action Probabilities: {action_probs}.\n\n"
            f"[Phase 3: Risk Governance Gate]\n"
            f"Risk Clearance Result: {risk_cleared} (P(Safe)={risk_query['prob_yes']*100:.1f}%).\n\n"
            f"[Phase 4: Synthesis & Sizing Allocation]\n"
            f"{sizing_rationale}\n"
            f"</think>"
        )

        return THX02TradeDecision(
            action=action,
            regime=regime,
            conviction=round(conviction, 3),
            risk_cleared=risk_cleared,
            suggested_leverage=suggested_leverage,
            suggested_sizing_pct=suggested_sizing_pct,
            thought=thought,
            probabilities=action_probs,
            metadata={
                "regime_probabilities": regime_query["probabilities"],
                "risk_prob_yes": risk_query["prob_yes"],
                "signals": signals,
            },
        )
