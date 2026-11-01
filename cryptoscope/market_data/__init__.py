"""Real-time multi-exchange crypto market data aggregator and truthfulness engine."""
from cryptoscope.market_data.base import NormalisedTicker, ExchangeStatus
from cryptoscope.market_data.aggregator import MarketDataAggregator
from cryptoscope.market_data.candle_store import CandleStore

__all__ = ["NormalisedTicker", "ExchangeStatus", "MarketDataAggregator", "CandleStore"]
