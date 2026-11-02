"""Tests for CryptoTimeMachine pre-trade Monte Carlo odds simulation engine."""
import pytest
from cryptoscope.simulation.time_machine import (
    CryptoTimeMachine,
    SimulationConfig,
    simulate_trade_odds,
)


def _generate_synthetic_candles(n: int = 100, trend: float = 0.0005) -> list:
    """Generate realistic candles with a slight upward drift."""
    candles = []
    price = 50000.0
    for i in range(n):
        o = price
        c = o * (1.0 + trend + (0.002 if i % 2 == 0 else -0.001))
        h = max(o, c) * 1.003
        l = min(o, c) * 0.997
        candles.append({
            "open_time": 1700000000.0 + (i * 3600),
            "close_time": 1700000000.0 + ((i + 1) * 3600),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": 100.0,
            "taker_buy_volume": 55.0,
        })
        price = c
    return candles


class TestCryptoTimeMachine:
    def test_extract_transition_pool(self):
        candles = _generate_synthetic_candles(30)
        sim = CryptoTimeMachine(rng_seed=123)
        pool = sim.extract_transition_pool(candles)
        assert len(pool) == 29
        # Check that ratios are sensible
        for o_r, h_r, l_r, c_r in pool:
            assert 0.90 < o_r < 1.10
            assert 0.90 < h_r < 1.10
            assert 0.90 < l_r < 1.10
            assert 0.90 < c_r < 1.10
            assert h_r >= l_r

    def test_run_simulation_long(self):
        candles = _generate_synthetic_candles(50)
        config = SimulationConfig(
            symbol="BTC/USDT",
            entry_price=50000.0,
            stop_price=49000.0,    # 2% risk
            target_price=52000.0,  # 4% reward (2R)
            horizon_bars=30,
            replays=500,
            seed=42,
        )
        sim = CryptoTimeMachine(rng_seed=42)
        res = sim.run_simulation(config, candles=candles)

        assert res.symbol == "BTC/USDT"
        assert res.side == "LONG"
        assert res.target_r == pytest.approx(2.0, rel=1e-2)
        assert res.breakeven_win_rate == pytest.approx(1.0 / 3.0, rel=1e-2)
        assert res.replays == 500
        assert res.target_hits + res.stop_hits + res.neither_hits == 500
        assert 0.0 <= res.empirical_win_rate <= 1.0
        assert res.verdict_code in ["STRONG_FAVORABLE", "MODERATE_FAVORABLE", "NEUTRAL", "UNFAVORABLE"]

        # Verify percentiles structure
        assert "p5" in res.percentile_trajectories
        assert "p50" in res.percentile_trajectories
        assert "p95" in res.percentile_trajectories
        assert len(res.percentile_trajectories["p50"]) == 31  # step 0 to step 30

    def test_run_simulation_short(self):
        candles = _generate_synthetic_candles(50)
        config = SimulationConfig(
            symbol="ETH/USDT",
            entry_price=3000.0,
            stop_price=3060.0,    # 2% risk
            target_price=2880.0,  # 4% reward (2R)
            horizon_bars=20,
            replays=300,
            seed=42,
        )
        sim = CryptoTimeMachine(rng_seed=42)
        res = sim.run_simulation(config, candles=candles)

        assert res.symbol == "ETH/USDT"
        assert res.side == "SHORT"
        assert res.target_r == pytest.approx(2.0, rel=1e-2)
        assert res.replays == 300
        assert res.target_hits + res.stop_hits + res.neither_hits == 300

    def test_convenience_function(self):
        candles = _generate_synthetic_candles(40)
        result_dict = simulate_trade_odds(
            symbol="SOL/USDT",
            entry=150.0,
            stop=145.0,
            target=160.0,
            candles=candles,
            replays=200,
            seed=99,
        )
        assert result_dict["symbol"] == "SOL/USDT"
        assert result_dict["side"] == "LONG"
        assert "empirical_win_rate" in result_dict
        assert "percentiles" in result_dict
        assert "expected_r" in result_dict
