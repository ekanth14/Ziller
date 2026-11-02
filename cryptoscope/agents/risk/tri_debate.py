"""Tri-Perspective Risk Governance Debate (Conservative vs Neutral vs Aggressive).

Adapted from TradingAgents risk management architecture.
Evaluates proposed position sizing, stop-loss invalidation, and volatility exposure from three distinct mandates.
"""
from typing import Any, Dict, List, Optional


class ConservativeRiskDebater:
    role = "conservative_risk"
    name = "Conservative Risk Governor (Capital Preservation)"

    def critique(self, setup: Dict[str, Any], balance: float = 10000.0) -> Dict[str, Any]:
        entry = float(setup.get("entry_price", 0.0))
        stop = float(setup.get("stop_loss", 0.0))
        risk_dist = abs(entry - stop)
        risk_pct = (risk_dist / entry) * 100.0 if entry > 0 else 2.0

        max_risk_cap = 0.015  # Max 1.5% NAV loss per trade
        max_position_size = (balance * max_risk_cap) / (risk_dist if risk_dist > 0 else 1.0)

        concerns = []
        if risk_pct > 3.0:
            concerns.append(f"Risk distance ({risk_pct:.2f}%) is too wide for high-volatility crypto assets.")
        concerns.append("Mandate strict stop adherence; zero manual discretion on stop moves.")

        return {
            "role": self.role,
            "name": self.name,
            "stance": "DEFENSIVE",
            "recommended_max_risk_pct": 1.5,
            "max_position_size": round(max_position_size, 4),
            "concerns": concerns,
            "argument": (
                f"Capital preservation priority: Max allowable NAV loss capped at 1.5% (${balance * 0.015:.2f}). "
                f"Strict stop must be hard-routed at {stop:.2f} to prevent catastrophic tail-risk slippage."
            ),
        }


class AggressiveRiskDebater:
    role = "aggressive_risk"
    name = "Aggressive Risk Governor (Profit Maximization)"

    def critique(self, setup: Dict[str, Any], balance: float = 10000.0) -> Dict[str, Any]:
        entry = float(setup.get("entry_price", 0.0))
        target = float(setup.get("take_profit", 0.0))
        rr = float(setup.get("risk_reward_ratio", 2.0))

        return {
            "role": self.role,
            "name": self.name,
            "stance": "OPPORTUNISTIC",
            "recommended_max_risk_pct": 3.0,
            "argument": (
                f"Alpha capture priority: Setup offers {rr:.1f}R potential targeting {target:.2f}. "
                f"Recommend holding a 25% runner position with a trailing ATR stop to capture parabolic crypto continuation."
            ),
        }


class NeutralRiskDebater:
    role = "neutral_risk"
    name = "Neutral Risk Governor (Expected Value Calibrator)"

    def critique(self, conservative: Dict[str, Any], aggressive: Dict[str, Any], setup: Dict[str, Any]) -> Dict[str, Any]:
        # Balanced consensus
        consensus_risk_pct = 2.0  # Industry standard 2.0% risk per trade
        return {
            "role": self.role,
            "name": self.name,
            "stance": "BALANCED_QUANTITATIVE",
            "approved_risk_pct": consensus_risk_pct,
            "argument": (
                f"Synthesized quantitative compromise: Approved per-trade capital allocation at {consensus_risk_pct}% NAV risk. "
                f"Take 75% profit at planned target and trail the remaining 25% with dynamic break-even stop."
            ),
        }


def run_tri_risk_debate(setup: Dict[str, Any], balance: float = 10000.0) -> Dict[str, Any]:
    """Execute tri-perspective risk governance debate."""
    c_debater = ConservativeRiskDebater()
    a_debater = AggressiveRiskDebater()
    n_debater = NeutralRiskDebater()

    c_rep = c_debater.critique(setup, balance=balance)
    a_rep = a_debater.critique(setup, balance=balance)
    n_rep = n_debater.critique(c_rep, a_rep, setup)

    return {
        "conservative": c_rep,
        "aggressive": a_rep,
        "neutral_consensus": n_rep,
        "approved_risk_pct": n_rep["approved_risk_pct"],
        "max_position_size": c_rep["max_position_size"],
    }
