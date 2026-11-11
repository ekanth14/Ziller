"""Binance WebSocket and REST live feed with automatic data-stream.binance.vision fallback."""
import asyncio
import json
import logging
import threading
import time
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any, Callable, Dict, List, Optional

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
        self._ws_thread: Optional[threading.Thread] = None
        self._consecutive_errors = 0
        self._last_ws_recv: float = 0.0
        self._stats_cache: Dict[str, Dict[str, float]] = {}

    def start(self):
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="BinanceFeed-REST")
        self._poll_thread.start()
        self._ws_thread = threading.Thread(target=self._ws_runner, daemon=True, name="BinanceFeed-WS")
        self._ws_thread.start()
        logger.info("Binance feed started (WebSocket + REST fallback) with symbols: %s", self.symbols)

    def stop(self):
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=1.0)

    def _is_ws_healthy(self) -> bool:
        """Returns True if WebSocket received a tick within the last 3.5 seconds."""
        return (time.time() - self._last_ws_recv) < 3.5

    def _ws_runner(self):
        """Thread runner for the async WebSocket event loop."""
        try:
            import websockets  # type: ignore
        except ImportError:
            logger.info("websockets package not available; using REST polling mode.")
            return

        while self._running:
            try:
                asyncio.run(self._async_ws_loop())
            except Exception as e:
                logger.debug("Binance WS loop exited: %s; reconnecting in 2s", e)
                time.sleep(2.0)

    async def _async_ws_loop(self):
        import websockets  # type: ignore

        # Subscribe to combined streams: <sym>@bookTicker and <sym>@ticker
        stream_names = []
        for s in self.symbols:
            low = s.lower()
            stream_names.append(f"{low}@bookTicker")
            stream_names.append(f"{low}@ticker")
        streams_query = "/".join(stream_names)
        ws_url = f"wss://{self.active_ws_host}/stream?streams={streams_query}"

        logger.debug("Connecting Binance WebSocket stream: %s", ws_url)
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
            logger.info("Binance real-time WebSocket connected (%s)", self.active_ws_host)
            while self._running:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=6.0)
                except asyncio.TimeoutError:
                    # Ping / keep-alive timeout
                    break

                now_t = time.time()
                self._last_ws_recv = now_t
                try:
                    envelope = json.loads(msg)
                    stream = envelope.get("stream", "")
                    data = envelope.get("data", {})
                    symbol = data.get("s", "").upper()
                    if not symbol:
                        continue

                    # Calculate real-time latency
                    event_time_ms = float(data.get("E", 0))
                    if event_time_ms > 0:
                        latency_ms = max(1.0, round((now_t * 1000.0) - event_time_ms, 1))
                        # Guard against local clock drift skew (>5000ms or <0ms)
                        if latency_ms > 5000.0 or latency_ms < 0:
                            latency_ms = 25.0
                    else:
                        latency_ms = 20.0

                    if "@ticker" in stream:
                        # 24hr ticker stream with full price change, vol, high, low
                        high = float(data.get("h", 0.0))
                        low = float(data.get("l", 0.0))
                        vol = float(data.get("v", 0.0))
                        chg = float(data.get("P", 0.0))
                        self._stats_cache[symbol] = {
                            "high_24h": high,
                            "low_24h": low,
                            "volume_24h": vol,
                            "change_24h_pct": chg,
                        }
                        bid = float(data.get("b", 0.0))
                        ask = float(data.get("a", 0.0))
                        last_p = float(data.get("c", (bid + ask) / 2.0 if bid and ask else 0.0))
                        mid = (bid + ask) / 2.0 if bid and ask else last_p
                        ticker = NormalisedTicker(
                            symbol=symbol,
                            base_asset=symbol.replace("USDT", ""),
                            quote_asset="USDT",
                            price=round(mid, 4 if mid < 10 else 2),
                            bid=bid,
                            ask=ask,
                            high_24h=high,
                            low_24h=low,
                            volume_24h=vol,
                            change_24h_pct=chg,
                            source="binance",
                            exchange_timestamp=now_t,
                            received_at=now_t,
                            latency_ms=latency_ms,
                        )
                        ticker.feed_type = "websocket"
                        self.on_ticker(ticker)

                    elif "@bookTicker" in stream:
                        # Real-time bookTicker stream with best bid and best ask
                        bid = float(data.get("b", 0.0))
                        ask = float(data.get("a", 0.0))
                        if bid <= 0.0 or ask <= 0.0:
                            continue
                        mid = (bid + ask) / 2.0
                        cached = self._stats_cache.get(symbol, {})
                        ticker = NormalisedTicker(
                            symbol=symbol,
                            base_asset=symbol.replace("USDT", ""),
                            quote_asset="USDT",
                            price=round(mid, 4 if mid < 10 else 2),
                            bid=bid,
                            ask=ask,
                            high_24h=cached.get("high_24h"),
                            low_24h=cached.get("low_24h"),
                            volume_24h=cached.get("volume_24h"),
                            change_24h_pct=cached.get("change_24h_pct"),
                            source="binance",
                            exchange_timestamp=now_t,
                            received_at=now_t,
                            latency_ms=latency_ms,
                        )
                        ticker.feed_type = "websocket"
                        self.on_ticker(ticker)

                except Exception as parse_err:
                    logger.debug("Error processing Binance WS tick: %s", parse_err)

    def _poll_loop(self):
        while self._running:
            # If WebSocket is healthy and actively receiving ticks, idle briefly
            if self._is_ws_healthy():
                time.sleep(1.0)
                continue

            try:
                received = False
                for symbol in self.symbols:
                    ticker = self.fetch_book_ticker(symbol)
                    if ticker:
                        self.on_ticker(ticker)
                        received = True
                if not received:
                    raise ConnectionError('No public quotes received this cycle')
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
        t0 = time.perf_counter()
        now_t = time.time()
        req = Request(url, headers={"User-Agent": "ZILLERS-Terminal/4.2"})
        try:
            with urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            bid = float(data["bidPrice"])
            ask = float(data["askPrice"])
            mid = (bid + ask) / 2.0
            cached = self._stats_cache.get(symbol, {})
            ticker = NormalisedTicker(
                symbol=symbol,
                base_asset=symbol.replace("USDT", ""),
                quote_asset="USDT",
                price=round(mid, 4 if mid < 10 else 2),
                bid=bid,
                ask=ask,
                high_24h=cached.get("high_24h"),
                low_24h=cached.get("low_24h"),
                volume_24h=cached.get("volume_24h"),
                change_24h_pct=cached.get("change_24h_pct"),
                source="binance",
                exchange_timestamp=now_t,
                received_at=time.time(),
                latency_ms=latency_ms,
            )
            ticker.feed_type = "rest"
            return ticker
        except (URLError, TimeoutError, ValueError, KeyError) as err:
            logger.debug("Binance bookTicker fetch failed for %s: %s", symbol, err)
            return None

    def fetch_24h_stats(self, symbol: str) -> Optional[Dict]:
        url = f"{self.active_rest_host}/api/v3/ticker/24hr?symbol={symbol}"
        req = Request(url, headers={"User-Agent": "ZILLERS-Terminal/4.2"})
        try:
            with urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            stats = {
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "volume_24h": float(data["volume"]),
                "change_24h_pct": float(data["priceChangePercent"]),
            }
            self._stats_cache[symbol] = stats
            return stats
        except Exception:
            return None
