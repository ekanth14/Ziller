"""Normalised data schemas and truthfulness thresholds for market data."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


LIVE_PRICE_FRESHNESS_SECONDS = 5.0
METADATA_FRESHNESS_SECONDS = 120.0
PRICE_DEVIATION_THRESHOLD = 0.01  # 1% maximum cross-source deviation


@dataclass
class NormalisedTicker:
    symbol: str                   # e.g. 'BTCUSDT'
    base_asset: str               # 'BTC'
    quote_asset: str              # 'USDT'
    price: float                  # Mid or last traded price
    bid: float
    ask: float
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    change_1h_pct: Optional[float] = None
    change_24h_pct: Optional[float] = None
    change_7d_pct: Optional[float] = None
    change_30d_pct: Optional[float] = None
    market_cap: Optional[float] = None
    rank: Optional[int] = None
    source: str = ""              # 'binance', 'coinbase', 'kraken', 'coingecko'
    exchange_timestamp: float = 0.0
    received_at: float = 0.0
    is_heartbeat: bool = False

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "price": self.price,
            "bid": self.bid,
            "ask": self.ask,
            "high_24h": self.high_24h,
            "low_24h": self.low_24h,
            "volume_24h": self.volume_24h,
            "change_1h_pct": self.change_1h_pct,
            "change_24h_pct": self.change_24h_pct,
            "change_7d_pct": self.change_7d_pct,
            "change_30d_pct": self.change_30d_pct,
            "market_cap": self.market_cap,
            "rank": self.rank,
            "source": self.source,
            "exchange_timestamp": self.exchange_timestamp,
            "received_at": self.received_at,
        }


@dataclass
class ExchangeStatus:
    name: str
    state: str = "offline"        # 'connected' | 'reconnecting' | 'offline'
    last_heartbeat: float = 0.0
    consecutive_errors: int = 0
    circuit_broken: bool = False
    endpoint: str = ""
    error_message: Optional[str] = None
