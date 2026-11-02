"""Bullish thesis researcher adapted from TradingAgents.

Builds a data-backed affirmative thesis based on Smart Money Concepts (SMC),
liquidity sweeps, volume accumulation, and momentum indicators.
"""
from typing import Any, Dict, List, Optional


class BullResearcher:
    role = "bull_researcher"
    name = "Bullish Quantitative Researcher"

    def formulate_thesis(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        order_blocks: Optional[List[Dict[str, Any]]] = None,
        opponent_argument: str = "",
        provider: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Formulate bullish thesis with technical evidence and counterarguments."""
        close = float(indicators.get("close", 0.0))
        rsi = float(indicators.get("rsi14", 50.0))
        ema20 = float(indicators.get("ema20", 0.0))
        ema50 = float(indicators.get("ema50", 0.0))
        obs = order_blocks or indicators.get("order_blocks", [])

        bull_obs = [ob for ob in obs if ob.get("type") == "BULLISH_OB"]

        # Deterministic grounded evidence extraction
        evidence = []
        if ema20 > ema50:
            evidence.append(f"EMA20 ({ema20:.2f}) > EMA50 ({ema50:.2f}) establishes structural crypto trend alignment.")
        if bull_obs:
            nearest_ob = bull_obs[-1]
            evidence.append(f"Institutional bullish order block confirmed at {nearest_ob.get('low', 0):.2f} - {nearest_ob.get('high', 0):.2f}.")
        if 40 <= rsi <= 68:
            evidence.append(f"Wilder RSI(14) at {rsi:.1f} shows sustained bullish accumulation room before overbought exhaustion.")
        if not evidence:
            evidence.append(f"Asset {symbol} maintaining support above {close * 0.98:.2f}.")

        counterargs = []
        if opponent_argument:
            counterargs.append(f"Addressing bear caution: down-moves on {symbol} are corrective absorptions rather than structural liquidation.")

        thesis = (
            f"Bullish continuation thesis on {symbol}: Market structure exhibits active demand defense "
            f"with {len(bull_obs)} verified order blocks and positive momentum slope. Target extension 1.5R to 2.5R."
        )

        # If LLM provider is available, enrich with generation
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
            "conviction": min(0.90, 0.55 + (0.1 if ema20 > ema50 else 0) + (0.15 if bull_obs else 0)),
        }
