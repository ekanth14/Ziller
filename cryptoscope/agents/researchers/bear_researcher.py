"""Bearish thesis researcher adapted from TradingAgents.

Hunts for market structure breaks, distribution traps, supply blocks, and momentum divergence.
"""
from typing import Any, Dict, List, Optional


class BearResearcher:
    role = "bear_researcher"
    name = "Bearish Quantitative Researcher"

    def formulate_thesis(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        order_blocks: Optional[List[Dict[str, Any]]] = None,
        opponent_argument: str = "",
        provider: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Formulate bearish thesis with technical counter-evidence."""
        close = float(indicators.get("close", 0.0))
        rsi = float(indicators.get("rsi14", 50.0))
        ema20 = float(indicators.get("ema20", 0.0))
        ema50 = float(indicators.get("ema50", 0.0))
        obs = order_blocks or indicators.get("order_blocks", [])

        bear_obs = [ob for ob in obs if ob.get("type") == "BEARISH_OB"]

        evidence = []
        if rsi >= 70:
            evidence.append(f"RSI(14) at {rsi:.1f} indicates severe overbought conditions susceptible to violent mean-reversion.")
        if bear_obs:
            nearest_bear_ob = bear_obs[-1]
            evidence.append(f"Overhead institutional supply block detected at {nearest_bear_ob.get('low', 0):.2f} - {nearest_bear_ob.get('high', 0):.2f}.")
        if ema20 < ema50:
            evidence.append(f"Short-term EMA20 ({ema20:.2f}) trades below EMA50 ({ema50:.2f}), indicating bearish regime pressure.")
        if not evidence:
            evidence.append(f"Potential liquidity hunt trap near local resistance {close * 1.02:.2f}.")

        counterargs = []
        if opponent_argument:
            counterargs.append(f"Refuting bull optimism: volume expansion near resistance frequently precedes institutional distribution.")

        thesis = (
            f"Bearish risk thesis on {symbol}: Elevated risk of liquidity sweep reversal into "
            f"overhead supply zones. Long positions face negative asymmetric skew if support fails."
        )

        if provider and hasattr(provider, "complete"):
            try:
                prompt_ctx = {
                    "role": self.role,
                    "symbol": symbol,
                    "evidence": evidence,
                    "opponent_argument": opponent_argument,
                    "output_contract": {"thesis": "string", "evidence": ["technical"], "counterarguments": ["string"]},
                }
                res = provider.complete(self.role, prompt_ctx)
                if isinstance(res, dict) and res.get("thesis"):
                    return res
            except Exception:
                pass

        return {
            "role": self.role,
            "name": self.name,
            "thesis": thesis,
            "evidence": evidence,
            "counterarguments": counterargs,
            "conviction": min(0.88, 0.50 + (0.15 if rsi >= 70 else 0) + (0.15 if bear_obs else 0)),
        }
