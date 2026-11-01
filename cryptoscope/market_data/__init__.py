"""Real-time multi-exchange crypto market data aggregator and truthfulness engine."""
from cryptoscope.market_data.base import NormalisedTicker, ExchangeStatus
from cryptoscope.market_data.aggregator import MarketDataAggregator
from cryptoscope.market_data.candle_store import CandleStore
from cryptoscope.market_data.binance_feed import BinanceFeed
from cryptoscope.market_data.coinbase_feed import CoinbaseFeed
from cryptoscope.market_data.kraken_feed import KrakenFeed
from cryptoscope.market_data.coingecko import CoinGeckoService

__all__ = [
    "NormalisedTicker",
    "ExchangeStatus",
    "MarketDataAggregator",
    "CandleStore",
    "BinanceFeed",
    "CoinbaseFeed",
    "KrakenFeed",
    "CoinGeckoService",
]
