"""Binance WebSocket and REST live feed with automatic data-stream.binance.vision fallback."""
import json
import logging
import threading
import time
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Callable, Dict, List, Optional

from cryptoscope.market_data.base import NormalisedTicker

logger = logging.getLogger("cryptoscope.binance_feed")


class BinanceFeed:
    PRIMARY_WS = "stream.binance.com:9443"
    FALLBACK_WS = "data-stream.binance.vision:9443"
    PRIMARY_REST = "https://api.binance.com"
    FALLBACK_REST = "https://data-api.binance.vision"

    def __init__(self, on_ticker: Callable[[NormalisedTicker], None], symbols: Optional[List[str]] = None):
        self.on_ticker = on_ticker
        self.symbols = [s.upper() for s in (symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"])]
        self.active_rest_host = self.PRIMARY_REST
        self.active_ws_host = self.PRIMARY_WS
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._consecutive_errors = 0

    def start(self):
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="BinanceFeed")
        self._poll_thread.start()
        logger.info("Binance feed started with symbols: %s", self.symbols)

    def stop(self):
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)

    def _poll_loop(self):
        while self._running:
            try:
                for symbol in self.symbols:
                    ticker = self.fetch_book_ticker(symbol)
                    if ticker:
                        self.on_ticker(ticker)
                self._consecutive_errors = 0
                time.sleep(1.0)
            except Exception as e:
                self._consecutive_errors += 1
                logger.warning("Binance poll cycle error (consecutive=%d): %s", self._consecutive_errors, e)
                # Switch to fallback host if consecutive errors >= 3
                if self._consecutive_errors >= 3:
                    if self.active_rest_host == self.PRIMARY_REST:
                        logger.warning("Switching Binance endpoint to fallback: %s", self.FALLBACK_REST)
                        self.active_rest_host = self.FALLBACK_REST
                        self.active_ws_host = self.FALLBACK_WS
                    else:
                        self.active_rest_host = self.PRIMARY_REST
                        self.active_ws_host = self.PRIMARY_WS
                backoff = min(10.0, 1.0 * (1.5 ** min(self._consecutive_errors, 5)))
                time.sleep(backoff)

    def fetch_book_ticker(self, symbol: str) -> Optional[NormalisedTicker]:
        url = f"{self.active_rest_host}/api/v3/ticker/bookTicker?symbol={symbol}"
        start_t = time.time()
        req = Request(url, headers={"User-Agent": "ZILLERS-Terminal/4.2"})
        try:
            with urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            bid = float(data["bidPrice"])
            ask = float(data["askPrice"])
            mid = (bid + ask) / 2.0
            return NormalisedTicker(
                symbol=symbol,
                base_asset=symbol.replace("USDT", ""),
                quote_asset="USDT",
                price=mid,
                bid=bid,
                ask=ask,
                source="binance",
                exchange_timestamp=start_t,
                received_at=time.time(),
            )
        except (URLError, TimeoutError, ValueError, KeyError) as err:
            logger.debug("Binance bookTicker fetch failed for %s: %s", symbol, err)
            return None

    def fetch_24h_stats(self, symbol: str) -> Optional[Dict]:
        url = f"{self.active_rest_host}/api/v3/ticker/24hr?symbol={symbol}"
        req = Request(url, headers={"User-Agent": "ZILLERS-Terminal/4.2"})
        try:
            with urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "volume_24h": float(data["volume"]),
                "change_24h_pct": float(data["priceChangePercent"]),
            }
        except Exception:
            return None
