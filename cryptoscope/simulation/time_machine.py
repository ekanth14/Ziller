"""Pre-trade Monte Carlo 'Time Machine' statistical odds engine for crypto assets.

Adapted from day-trader-skill methodology and optimized for continuous 24/7 crypto markets.
Performs historical block-bootstrap replays to compute empirical win rates, R-multiples,
and trajectory percentiles (fan chart) before capital is committed.
"""
from dataclasses import dataclass, field
import math
import random
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SimulationConfig:
    symbol: str
    entry_price: float
    stop_price: float
    target_price: float
    horizon_bars: int = 48         # Default 48 bars (e.g. 48x 15m = 12h or 48x 1h = 2d)
    replays: int = 2000            # Number of Monte Carlo trajectories
    seed: Optional[int] = 42
    side: str = "auto"             # 'long', 'short', or 'auto' (inferred from entry/stop/target)


@dataclass
class SimulationResult:
    symbol: str
    side: str
    entry_price: float
    stop_price: float
    target_price: float
    risk_distance: float
    target_distance: float
    target_r: float
    replays: int
    target_hits: int
    stop_hits: int
    neither_hits: int
    empirical_win_rate: float
    breakeven_win_rate: float
    win_rate_edge: float           # empirical_win_rate - breakeven_win_rate
    expected_r: float
    verdict: str
    verdict_code: str              # 'STRONG_FAVORABLE', 'MODERATE_FAVORABLE', 'NEUTRAL', 'UNFAVORABLE'
    percentile_trajectories: Dict[str, List[float]] = field(default_factory=dict)
    summary_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": round(self.entry_price, 4),
            "stop_price": round(self.stop_price, 4),
            "target_price": round(self.target_price, 4),
            "risk_distance": round(self.risk_distance, 4),
            "target_distance": round(self.target_distance, 4),
            "target_r": round(self.target_r, 3),
            "replays": self.replays,
            "target_hits": self.target_hits,
            "stop_hits": self.stop_hits,
            "neither_hits": self.neither_hits,
            "empirical_win_rate": round(self.empirical_win_rate, 4),
            "breakeven_win_rate": round(self.breakeven_win_rate, 4),
            "win_rate_edge": round(self.win_rate_edge, 4),
            "expected_r": round(self.expected_r, 3),
            "verdict": self.verdict,
            "verdict_code": self.verdict_code,
            "summary_message": self.summary_message,
            "percentiles": self.percentile_trajectories,
        }


class CryptoTimeMachine:
    """Monte Carlo bootstrap simulator for validating crypto trade setups."""

    def __init__(self, rng_seed: Optional[int] = 42):
        self._seed = rng_seed
        self._rng = random.Random(rng_seed)

    def extract_transition_pool(self, candles: List[Dict[str, Any]]) -> List[Tuple[float, float, float, float]]:
        """Extract bar-to-bar price ratios (open_ratio, high_ratio, low_ratio, close_ratio)

        relative to the previous candle's close.
        """
        if not candles or len(candles) < 2:
            return []

        # Sort chronological if needed
        sorted_candles = sorted(candles, key=lambda c: float(c.get("open_time", 0)))
        pool = []

        for i in range(1, len(sorted_candles)):
            prev_close = float(sorted_candles[i - 1]["close"])
            if prev_close <= 0:
                continue

            curr_open = float(sorted_candles[i]["open"])
            curr_high = float(sorted_candles[i]["high"])
            curr_low = float(sorted_candles[i]["low"])
            curr_close = float(sorted_candles[i]["close"])

            # Normalized ratios relative to prev_close
            pool.append((
                curr_open / prev_close,
                curr_high / prev_close,
                curr_low / prev_close,
                curr_close / prev_close,
            ))

        return pool

    def run_simulation(
        self,
        config: SimulationConfig,
        candles: Optional[List[Dict[str, Any]]] = None,
    ) -> SimulationResult:
        """Run Monte Carlo simulation and compile empirical odds."""
        # Reset RNG if seed provided
        if config.seed is not None:
            self._rng = random.Random(config.seed)

        # 1. Infer side (LONG or SHORT)
        if config.side.lower() == "auto":
            if config.target_price > config.entry_price and config.stop_price < config.entry_price:
                side = "LONG"
            elif config.target_price < config.entry_price and config.stop_price > config.entry_price:
                side = "SHORT"
            else:
                # Default to LONG if ambiguous
                side = "LONG" if config.target_price >= config.entry_price else "SHORT"
        else:
            side = config.side.upper()

        risk_distance = abs(config.entry_price - config.stop_price)
        target_distance = abs(config.target_price - config.entry_price)

        if risk_distance <= 0:
            risk_distance = config.entry_price * 0.01  # Safe minimum 1%

        target_r = target_distance / risk_distance
        breakeven_win_rate = 1.0 / (1.0 + target_r)

        # 2. Extract or build transition pool
        pool = self.extract_transition_pool(candles) if candles else []

        # Fallback pool if candle sample too small: realistic crypto volatility profile (0.5% - 2.5% stddev)
        if len(pool) < 20:
            pool = []
            base_vol = 0.008  # ~0.8% typical 15m/1h bar move
            for _ in range(200):
                ret = self._rng.gauss(0.0001, base_vol)
                high_wiggle = abs(self._rng.gauss(0.002, 0.003))
                low_wiggle = abs(self._rng.gauss(0.002, 0.003))
                close_ratio = 1.0 + ret
                high_ratio = max(1.0, close_ratio) + high_wiggle
                low_ratio = min(1.0, close_ratio) - low_wiggle
                pool.append((1.0, high_ratio, low_ratio, close_ratio))

        pool_size = len(pool)
        target_hits = 0
        stop_hits = 0
        neither_hits = 0

        # Matrix for trajectory recording (step -> prices across paths)
        # Record trajectory checkpoints every step for fan chart
        horizon = max(5, min(config.horizon_bars, 200))
        trajectories_records: List[List[float]] = [[] for _ in range(horizon + 1)]

        # Add initial price to step 0
        for _ in range(config.replays):
            trajectories_records[0].append(config.entry_price)

        # 3. Simulate Monte Carlo paths
        for _ in range(config.replays):
            current_price = config.entry_price
            resolved = False
            outcome = "neither"
            path_prices = [config.entry_price]

            for step in range(1, horizon + 1):
                if resolved:
                    # After resolution, propagate terminal price for consistent fan chart
                    path_prices.append(current_price)
                    trajectories_records[step].append(current_price)
                    continue

                # Sample transition from historical pool
                idx = self._rng.randint(0, pool_size - 1)
                _o, h_ratio, l_ratio, c_ratio = pool[idx]

                step_high = current_price * h_ratio
                step_low = current_price * l_ratio
                current_price = current_price * c_ratio

                # Check breach conditions
                if side == "LONG":
                    hit_stop = step_low <= config.stop_price
                    hit_target = step_high >= config.target_price

                    if hit_stop and hit_target:
                        # Conservative: stop counted first if both hit in same candle
                        outcome = "stop"
                        resolved = True
                        current_price = config.stop_price
                    elif hit_stop:
                        outcome = "stop"
                        resolved = True
                        current_price = config.stop_price
                    elif hit_target:
                        outcome = "target"
                        resolved = True
                        current_price = config.target_price

                else:  # SHORT
                    hit_stop = step_high >= config.stop_price
                    hit_target = step_low <= config.target_price

                    if hit_stop and hit_target:
                        outcome = "stop"
                        resolved = True
                        current_price = config.stop_price
                    elif hit_stop:
                        outcome = "stop"
                        resolved = True
                        current_price = config.stop_price
                    elif hit_target:
                        outcome = "target"
                        resolved = True
                        current_price = config.target_price

                path_prices.append(current_price)
                trajectories_records[step].append(current_price)

            if outcome == "target":
                target_hits += 1
            elif outcome == "stop":
                stop_hits += 1
            else:
                neither_hits += 1

        # 4. Statistical Metrics
        decisive_runs = target_hits + stop_hits
        if decisive_runs > 0:
            empirical_win_rate = target_hits / decisive_runs
        else:
            empirical_win_rate = 0.50

        win_rate_edge = empirical_win_rate - breakeven_win_rate

        # Expected R: E[R] = P(target)*target_r - P(stop)*1.0 + P(neither)*unrealized_r
        p_target = target_hits / config.replays
        p_stop = stop_hits / config.replays
        p_neither = neither_hits / config.replays
        expected_r = (p_target * target_r) - (p_stop * 1.0)

        # 5. Verdict & Edge Classification
        if win_rate_edge >= 0.12 and expected_r > 0.20:
            verdict_code = "STRONG_FAVORABLE"
            verdict = "Strong Positive Expectancy (Statistical Edge)"
            summary_message = (
                f"Empirical win rate of {empirical_win_rate*100:.1f}% exceeds break-even threshold "
                f"({breakeven_win_rate*100:.1f}%) by +{win_rate_edge*100:.1f} pts. Expected return is +{expected_r:.2f}R."
            )
        elif win_rate_edge >= 0.04 and expected_r >= 0.05:
            verdict_code = "MODERATE_FAVORABLE"
            verdict = "Moderate Positive Expectancy (Favorable Setup)"
            summary_message = (
                f"Empirical win rate of {empirical_win_rate*100:.1f}% slightly outperforms break-even "
                f"({breakeven_win_rate*100:.1f}%) by +{win_rate_edge*100:.1f} pts. Expected return is +{expected_r:.2f}R."
            )
        elif abs(win_rate_edge) < 0.04:
            verdict_code = "NEUTRAL"
            verdict = "Neutral / Coin-Flip (No Statistically Significant Edge)"
            summary_message = (
                f"Empirical win rate ({empirical_win_rate*100:.1f}%) aligns closely with break-even "
                f"({breakeven_win_rate*100:.1f}%). Expected return is {expected_r:+.2f}R."
            )
        else:
            verdict_code = "UNFAVORABLE"
            verdict = "Negative Expectancy (Unfavorable Risk-Reward Probability)"
            summary_message = (
                f"Empirical win rate of {empirical_win_rate*100:.1f}% lags required break-even "
                f"({breakeven_win_rate*100:.1f}%) by {win_rate_edge*100:.1f} pts. Negative expected value {expected_r:+.2f}R."
            )

        # 6. Trajectory Percentiles for Fan Chart
        # Compute p5, p25, p50 (median), p75, p95 at each step
        percentile_dict: Dict[str, List[float]] = {
            "p5": [],
            "p25": [],
            "p50": [],
            "p75": [],
            "p95": [],
        }

        for step in range(horizon + 1):
            vals = sorted(trajectories_records[step])
            n = len(vals)
            percentile_dict["p5"].append(round(vals[int(n * 0.05)], 4))
            percentile_dict["p25"].append(round(vals[int(n * 0.25)], 4))
            percentile_dict["p50"].append(round(vals[int(n * 0.50)], 4))
            percentile_dict["p75"].append(round(vals[int(n * 0.75)], 4))
            percentile_dict["p95"].append(round(vals[min(int(n * 0.95), n - 1)], 4))

        return SimulationResult(
            symbol=config.symbol,
            side=side,
            entry_price=config.entry_price,
            stop_price=config.stop_price,
            target_price=config.target_price,
            risk_distance=risk_distance,
            target_distance=target_distance,
            target_r=target_r,
            replays=config.replays,
            target_hits=target_hits,
            stop_hits=stop_hits,
            neither_hits=neither_hits,
            empirical_win_rate=empirical_win_rate,
            breakeven_win_rate=breakeven_win_rate,
            win_rate_edge=win_rate_edge,
            expected_r=expected_r,
            verdict=verdict,
            verdict_code=verdict_code,
            percentile_trajectories=percentile_dict,
            summary_message=summary_message,
        )


def simulate_trade_odds(
    symbol: str,
    entry: float,
    stop: float,
    target: float,
    candles: Optional[List[Dict[str, Any]]] = None,
    horizon_bars: int = 48,
    replays: int = 2000,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """Convenience functional wrapper for executing a pre-trade Monte Carlo simulation."""
    config = SimulationConfig(
        symbol=symbol,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        horizon_bars=horizon_bars,
        replays=replays,
        seed=seed,
    )
    simulator = CryptoTimeMachine(rng_seed=seed)
    result = simulator.run_simulation(config, candles=candles)
    return result.to_dict()
