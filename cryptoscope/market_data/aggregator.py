"""Truthful multi-source crypto market data aggregator with median pricing and state locks.

Enforces:
1. Lock-protected shared state across background ingestion threads.
2. Drops stale sources before comparison (live price freshness ~5.0s, metadata ~120s).
3. Median pricing across fresh sources.
4. Status: 'single-source' (if only 1 fresh source), 'verified' (if >=2 sources and all <=1% deviation),
   'unverified' (if >=2 sources and >1% deviation), 'stale' (if latest source > 5s), 'unavailable' (if no data).
5. Heartbeat & book update liveness tracking.
"""

import logging
import statistics
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from cryptoscope.market_data.base import (
    ExchangeStatus,
    NormalisedTicker,
    LIVE_PRICE_FRESHNESS_SECONDS,
    METADATA_FRESHNESS_SECONDS,
    PRICE_DEVIATION_THRESHOLD,
)

logger = logging.getLogger("cryptoscope.aggregator")


class MarketDataAggregator:
    def __init__(self, symbols: Optional[List[str]] = None):
        self._lock = threading.Lock()
        self.symbols = list(symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        # symbol -> source -> NormalisedTicker
        self._tickers: Dict[str, Dict[str, NormalisedTicker]] = {s: {} for s in self.symbols}
        # symbol -> dict of CoinGecko metadata
        self._metadata: Dict[str, Dict[str, Any]] = {}
        # source_name -> ExchangeStatus
        self._exchanges: Dict[str, ExchangeStatus] = {
            "binance": ExchangeStatus(name="binance", endpoint="stream.binance.com"),
            "coinbase": ExchangeStatus(name="coinbase", endpoint="ws-feed.exchange.coinbase.com"),
            "kraken": ExchangeStatus(name="kraken", endpoint="ws.kraken.com"),
            "coingecko": ExchangeStatus(name="coingecko", endpoint="api.coingecko.com"),
        }
        self.deviation_threshold = PRICE_DEVIATION_THRESHOLD

    def update_exchange_status(self, source: str, state: str, error: Optional[str] = None):
        with self._lock:
            if source not in self._exchanges:
                self._exchanges[source] = ExchangeStatus(name=source)
            ex = self._exchanges[source]
            ex.state = state
            if state == "connected":
                ex.last_heartbeat = time.time()
                ex.consecutive_errors = 0
                ex.error_message = None
            elif state in {"reconnecting", "offline"}:
                ex.consecutive_errors += 1
                ex.error_message = error

    def record_ticker(self, ticker: NormalisedTicker):
        """Record real-time ticker update from an exchange adapter."""
        with self._lock:
            sym = ticker.symbol
            if sym not in self._tickers:
                self._tickers[sym] = {}
            self._tickers[sym][ticker.source] = ticker

            # Liveness: book updates and heartbeats maintain exchange connection state
            ex = self._exchanges.get(ticker.source)
            if ex:
                ex.last_heartbeat = ticker.received_at or time.time()
                ex.state = "connected"

    def record_metadata(self, symbol: str, data: Dict[str, Any]):
        """Record CoinGecko metadata (rank, market cap, 24h vol, sparkline)."""
        with self._lock:
            self._metadata[symbol] = {
                **data,
                "received_at": time.time(),
            }

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Compute truthful consolidated price and verification status."""
        with self._lock:
            now = time.time()
            sources_dict = self._tickers.get(symbol, {})

            if not sources_dict:
                return {
                    "symbol": symbol,
                    "status": "unavailable",
                    "price": None,
                    "bid": None,
                    "ask": None,
                    "sources_reporting": [],
                    "sources_dropped_stale": [],
                    "age_seconds": None,
                    "metadata": self._get_metadata_locked(symbol, now),
                }

            # 1. Drop stale sources before comparing
            fresh_sources: Dict[str, NormalisedTicker] = {}
            stale_sources: Dict[str, NormalisedTicker] = {}
            for src, t in sources_dict.items():
                age = now - t.received_at
                if age <= LIVE_PRICE_FRESHNESS_SECONDS:
                    fresh_sources[src] = t
                else:
                    stale_sources[src] = t

            # If no fresh sources exist, return the latest stale observation
            if not fresh_sources:
                latest = max(sources_dict.values(), key=lambda t: t.received_at)
                age = round(now - latest.received_at, 1)
                return {
                    "symbol": symbol,
                    "status": "stale",
                    "price": latest.price,
                    "bid": latest.bid,
                    "ask": latest.ask,
                    "sources_reporting": list(sources_dict.keys()),
                    "sources_dropped_stale": list(sources_dict.keys()),
                    "age_seconds": age,
                    "last_fresh_source": latest.source,
                    "metadata": self._get_metadata_locked(symbol, now),
                }

            # 2. Exactly 1 fresh source -> status: 'single-source'
            if len(fresh_sources) == 1:
                src, t = next(iter(fresh_sources.items()))
                age = round(now - t.received_at, 2)
                return {
                    "symbol": symbol,
                    "status": "single-source",
                    "price": t.price,
                    "bid": t.bid,
                    "ask": t.ask,
                    "change_24h_pct": t.change_24h_pct,
                    "volume_24h": t.volume_24h,
                    "high_24h": t.high_24h,
                    "low_24h": t.low_24h,
                    "source": src,
                    "sources_reporting": [src],
                    "sources_dropped_stale": list(stale_sources.keys()),
                    "age_seconds": age,
                    "median_price": t.price,
                    "max_deviation_pct": 0.0,
                    "metadata": self._get_metadata_locked(symbol, now),
                }

            # 3. >= 2 fresh sources -> compute median and check deviation
            prices = [t.price for t in fresh_sources.values()]
            median_price = statistics.median(prices)
            deviations = {src: abs(t.price - median_price) / median_price for src, t in fresh_sources.items()}
            max_dev = max(deviations.values())

            # Best bid (highest bid) and best ask (lowest ask) among fresh sources
            best_bid = max(t.bid for t in fresh_sources.values())
            best_ask = min(t.ask for t in fresh_sources.values())

            # Representative ticker (closest to median)
            rep = min(fresh_sources.values(), key=lambda t: abs(t.price - median_price))
            age = round(now - rep.received_at, 2)

            is_verified = (max_dev <= self.deviation_threshold)
            status = "verified" if is_verified else "unverified"

            if not is_verified:
                logger.warning(
                    "Price deviation for %s exceeded %.1f%% across fresh sources: %s (max_dev=%.3f%%)",
                    symbol, self.deviation_threshold * 100,
                    {src: round(t.price, 2) for src, t in fresh_sources.items()},
                    max_dev * 100
                )

            return {
                "symbol": symbol,
                "status": status,
                "price": round(median_price, 4 if median_price < 10 else 2),
                "bid": best_bid,
                "ask": best_ask,
                "change_24h_pct": rep.change_24h_pct,
                "volume_24h": rep.volume_24h,
                "high_24h": rep.high_24h,
                "low_24h": rep.low_24h,
                "source": "median(" + ",".join(sorted(fresh_sources.keys())) + ")",
                "sources_reporting": sorted(list(fresh_sources.keys())),
                "sources_dropped_stale": sorted(list(stale_sources.keys())),
                "age_seconds": age,
                "median_price": median_price,
                "max_deviation_pct": round(max_dev * 100, 3),
                "metadata": self._get_metadata_locked(symbol, now),
            }

    def _get_metadata_locked(self, symbol: str, now: float) -> Optional[Dict[str, Any]]:
        meta = self._metadata.get(symbol)
        if not meta:
            return None
        age = now - meta.get("received_at", 0)
        return {
            **meta,
            "metadata_age_seconds": round(age, 1),
            "metadata_stale": age > METADATA_FRESHNESS_SECONDS,
            "attribution": "Data provided by CoinGecko (Public API)",
        }

    def get_all_tickers(self) -> List[Dict[str, Any]]:
        return [self.get_ticker(s) for s in self.symbols]

    def get_connection_status(self) -> Dict[str, Any]:
        """Connection health indicator across all connected exchange feeds."""
        with self._lock:
            now = time.time()
            res = {}
            for name, ex in self._exchanges.items():
                heartbeat_age = now - ex.last_heartbeat if ex.last_heartbeat > 0 else None
                # If no heartbeat within 15 seconds, mark reconnecting/offline
                state = ex.state
                if state == "connected" and heartbeat_age and heartbeat_age > 15.0:
                    state = "reconnecting"
                res[name] = {
                    "state": state,
                    "endpoint": ex.endpoint,
                    "last_heartbeat_age": round(heartbeat_age, 1) if heartbeat_age else None,
                    "consecutive_errors": ex.consecutive_errors,
                    "error": ex.error_message,
                }
            return res
