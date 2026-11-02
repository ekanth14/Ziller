"""Quantitative strategy library adapted for continuous 24/7 crypto markets."""
from .volume_breakout import VolumeBreakoutStrategy
from .shrink_pullback import ShrinkPullbackStrategy
from .box_oscillation import BoxOscillationStrategy
from .stat_arb_pairs import StatArbPairsStrategy
from .volatility_breakout import VolatilityCompressionBreakoutStrategy

__all__ = [
    "VolumeBreakoutStrategy",
    "ShrinkPullbackStrategy",
    "BoxOscillationStrategy",
    "StatArbPairsStrategy",
    "VolatilityCompressionBreakoutStrategy",
]
