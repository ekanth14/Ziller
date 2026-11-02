"""Tests for expanded crypto quantitative strategies and alert notifier."""
import pytest
from cryptoscope.autotrader.strategies.volume_breakout import VolumeBreakoutStrategy
from cryptoscope.autotrader.strategies.shrink_pullback import ShrinkPullbackStrategy
from cryptoscope.autotrader.strategies.box_oscillation import BoxOscillationStrategy
from cryptoscope.autotrader.notifier import AlertNotifier, AlertPayload


def _make_consolidation_candles(n: int = 30, base: float = 100.0, height: float = 0.05) -> list:
    """Make candles oscillating in a box."""
    candles = []
    for i in range(n):
        frac = 0.5 + 0.4 * (1 if i % 4 < 2 else -1)
        c = base * (1.0 + height * frac)
        candles.append({
            "open": c * 0.998,
            "high": base * (1.0 + height),
            "low": base,
            "close": c,
            "volume": 500.0,
            "open_time": 1000 + i * 60,
        })
    return candles


class TestExpandedStrategies:
    def test_volume_breakout_fires_on_surge(self):
        strategy = VolumeBreakoutStrategy(volume_multiplier=1.5, lookback=10)
        # Create 15 quiet candles, then 1 big breakout candle
        candles = []
        for i in range(15):
            candles.append({
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.0,
                "volume": 100.0,
                "open_time": 1000 + i * 60,
            })

        # Breakout candle: close > 102.0 and volume >= 150
        candles.append({
            "open": 101.5,
            "high": 105.0,
            "low": 101.0,
            "close": 104.0,
            "volume": 300.0,  # 3x volume
            "open_time": 1900,
        })

        sig = strategy.evaluate(candles, indicators={"rsi14": 62.0, "ema20": 101.0, "ema50": 100.0})
        assert sig is not None
        assert sig["strategy"] == "volume_breakout"
        assert sig["side"] == "BUY"
        assert sig["entry_price"] == 104.0
        assert sig["stop_loss"] < 104.0
        assert sig["take_profit"] > 104.0

    def test_volume_breakout_ignores_low_volume(self):
        strategy = VolumeBreakoutStrategy(volume_multiplier=1.5, lookback=10)
        candles = []
        for i in range(15):
            candles.append({
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.0,
                "volume": 100.0,
                "open_time": 1000 + i * 60,
            })

        # High price but low volume
        candles.append({
            "open": 101.5,
            "high": 105.0,
            "low": 101.0,
            "close": 104.0,
            "volume": 80.0,  # below avg
            "open_time": 1900,
        })

        sig = strategy.evaluate(candles, indicators={"rsi14": 62.0, "ema20": 101.0, "ema50": 100.0})
        assert sig is None

    def test_shrink_pullback_fires(self):
        strategy = ShrinkPullbackStrategy(max_pullback_vol_ratio=0.75, lookback=10)
        candles = []
        for i in range(15):
            candles.append({
                "open": 100.0 + i,
                "high": 102.0 + i,
                "low": 99.0 + i,
                "close": 101.5 + i,
                "volume": 500.0,
                "open_time": 1000 + i * 60,
            })

        # Pullback bar with very low volume
        candles.append({
            "open": 115.0,
            "high": 115.2,
            "low": 110.0,
            "close": 110.2,
            "volume": 150.0,  # 0.3x volume
            "open_time": 1900,
        })
        # Bullish rebound bar
        candles.append({
            "open": 110.3,
            "high": 113.0,
            "low": 110.1,
            "close": 112.5,
            "volume": 400.0,
            "open_time": 1960,
        })

        sig = strategy.evaluate(candles, indicators={"ema20": 110.0, "ema50": 105.0, "rsi14": 52.0})
        assert sig is not None
        assert sig["strategy"] == "shrink_pullback"
        assert sig["side"] == "BUY"
        assert sig["entry_price"] == 112.5

    def test_box_oscillation_fires(self):
        strategy = BoxOscillationStrategy(lookback=25, min_height_pct=0.03, max_height_pct=0.08)
        candles = _make_consolidation_candles(25, base=1000.0, height=0.05)

        # Last candle at box bottom with green bounce
        candles.append({
            "open": 1002.0,
            "high": 1015.0,
            "low": 1000.5,
            "close": 1010.0,
            "volume": 600.0,
            "open_time": 3000,
        })

        sig = strategy.evaluate(candles, indicators={"rsi14": 38.0})
        assert sig is not None
        assert sig["strategy"] == "box_oscillation"
        assert sig["side"] == "BUY"
        assert sig["take_profit"] > sig["entry_price"]
        assert sig["stop_loss"] < sig["entry_price"]

    def test_alert_notifier_dispatch_dry_run(self):
        # Empty configs: should not crash or throw
        notifier = AlertNotifier()
        assert not notifier.is_configured()

        alert = AlertPayload(
            title="Test Signal",
            message="Volume breakout detected on BTC/USDT",
            symbol="BTCUSDT",
            alert_type="TRADE_SIGNAL",
            details={"price": 65000.0, "volume_ratio": 2.4},
        )
        notifier.dispatch(alert, sync=True)
