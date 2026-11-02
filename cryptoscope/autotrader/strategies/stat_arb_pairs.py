"""Statistical Arbitrage / Cointegrated Pairs Trading Strategy.

Trades stationary linear combinations of cointegrated crypto pairs using
the Ornstein-Uhlenbeck mean-reversion process and dynamic Z-score bands.
"""

from typing import Any, Dict, List, Optional
from cryptoscope.quant.stat_arb import (
    calculate_hedge_ratio,
    calculate_spread,
    ornstein_uhlenbeck_parameters,
    calculate_spread_zscore,
    adf_unit_root_test,
)


class StatArbPairsStrategy:
    name = "stat_arb_pairs"
    display_name = "Statistical Arbitrage Pairs (统计套利)"

    def __init__(
        self,
        entry_zscore: float = 2.0,
        exit_zscore: float = 0.25,
        stop_zscore: float = 3.5,
        window: int = 30,
        max_half_life: float = 200.0,
    ):
        self.entry_zscore = entry_zscore
        self.exit_zscore = exit_zscore
        self.stop_zscore = stop_zscore
        self.window = window
        self.max_half_life = max_half_life

    def evaluate_pair(
        self,
        candles_a: List[Dict[str, Any]],
        candles_b: List[Dict[str, Any]],
        symbol_a: str = "ETHUSDT",
        symbol_b: str = "BTCUSDT",
    ) -> Optional[Dict[str, Any]]:
        n = min(len(candles_a), len(candles_b))
        if n < self.window + 10:
            return None

        closes_a = [float(c["close"]) for c in candles_a[-n:]]
        closes_b = [float(c["close"]) for c in candles_b[-n:]]

        beta, alpha = calculate_hedge_ratio(closes_a, closes_b)
        spread = calculate_spread(closes_a, closes_b, beta=beta, alpha=alpha)

        # 1. Engle-Granger Cointegration check
        _, _, is_coint = adf_unit_root_test(spread)

        # 2. OU process parameter estimation
        ou = ornstein_uhlenbeck_parameters(spread)

        # 3. Dynamic Z-Score
        z_res = calculate_spread_zscore(
            closes_a,
            closes_b,
            window=self.window,
            entry_threshold=self.entry_zscore,
            exit_threshold=self.exit_zscore,
            stop_threshold=self.stop_zscore,
        )

        zscore = z_res["zscore"]
        action = z_res["action"]
        signal = z_res["signal"]

        # Only trigger entry if mean-reverting with reasonable half-life
        half_life = ou.get("half_life_bars", float("inf"))
        valid_dynamics = (half_life <= self.max_half_life) and ou.get("mean_reverting", False)

        price_a = closes_a[-1]
        price_b = closes_b[-1]

        if action == "BUY_A_SELL_B" and valid_dynamics:
            # Spread is depressed; Buy A, Short B
            return {
                "strategy": self.name,
                "display_name": self.display_name,
                "side": "LONG_SPREAD",
                "symbol_a": symbol_a,
                "symbol_b": symbol_b,
                "entry_price_a": price_a,
                "entry_price_b": price_b,
                "hedge_ratio_beta": beta,
                "zscore": zscore,
                "half_life_bars": half_life,
                "is_cointegrated": is_coint,
                "confidence": min(0.92, 0.65 + abs(zscore) * 0.08),
                "reason": f"Spread Z-score ({zscore:.2f}) undervalued below -{self.entry_zscore}. Mean reversion expected with half-life of {half_life:.1f} bars.",
            }

        elif action == "SELL_A_BUY_B" and valid_dynamics:
            # Spread is elevated; Short A, Buy B
            return {
                "strategy": self.name,
                "display_name": self.display_name,
                "side": "SHORT_SPREAD",
                "symbol_a": symbol_a,
                "symbol_b": symbol_b,
                "entry_price_a": price_a,
                "entry_price_b": price_b,
                "hedge_ratio_beta": beta,
                "zscore": zscore,
                "half_life_bars": half_life,
                "is_cointegrated": is_coint,
                "confidence": min(0.92, 0.65 + abs(zscore) * 0.08),
                "reason": f"Spread Z-score ({zscore:.2f}) overextended above +{self.entry_zscore}. Mean reversion expected with half-life of {half_life:.1f} bars.",
            }

        elif action == "CLOSE_TARGET":
            return {
                "strategy": self.name,
                "display_name": self.display_name,
                "side": "EXIT_TARGET",
                "symbol_a": symbol_a,
                "symbol_b": symbol_b,
                "zscore": zscore,
                "hedge_ratio_beta": beta,
                "confidence": 0.90,
                "reason": f"Spread has converged back to equilibrium (|Z| = {abs(zscore):.2f} <= {self.exit_zscore}). Close pair position for profit.",
            }

        elif action == "FLATTEN":
            return {
                "strategy": self.name,
                "display_name": self.display_name,
                "side": "STOP_LOSS",
                "symbol_a": symbol_a,
                "symbol_b": symbol_b,
                "zscore": zscore,
                "confidence": 0.99,
                "reason": f"Structural break stop triggered (|Z| = {abs(zscore):.2f} >= {self.stop_zscore}). Regime departure; emergency flatten.",
            }

        return None
