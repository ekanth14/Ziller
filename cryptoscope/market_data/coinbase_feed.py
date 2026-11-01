"""Coinbase public market data adapter for cross-exchange verification."""
import json
import logging
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from typing import Callable, Dict, List, Optional

from cryptoscope.market_data.base import NormalisedTicker

logger = logging.getLogger("cryptoscope.coinbase_feed")


class CoinbaseFeed:
    REST_ENDPOINT = "https://api.exchange.coinbase.com"

    # Map standard unified crypto symbols to Coinbase product IDs
    SYMBOL_MAP = {
        "BTCUSDT": "BTC-USDT",
        "ETHUSDT": "ETH-USDT",
        "SOLUSDT": "SOL-USDT",
    }

    def __init__(self, on_ticker: Callable[[NormalisedTicker], None], symbols: Optional[List[str]] = None):
        self.on_ticker = on_ticker
        self.symbols = [s.upper() for s in (symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"])]
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="CoinbaseFeed")
        self._poll_thread.start()

    def stop(self):
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)

    def _poll_loop(self):
        while self._running:
            for symbol in self.symbols:
                ticker = self.fetch_ticker(symbol)
                if ticker:
                    self.on_ticker(ticker)
                time.sleep(0.3)
            time.sleep(1.5)

    def fetch_ticker(self, symbol: str) -> Optional[NormalisedTicker]:
        cb_symbol = self.SYMBOL_MAP.get(symbol, symbol.replace("USDT", "-USDT"))
        url = f"{self.REST_ENDPOINT}/products/{cb_symbol}/ticker"
        start_t = time.time()
        req = Request(url, headers={"User-Agent": "ZILLERS-Terminal/4.2"})
        try:
            with urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            price = float(data["price"])
            bid = float(data.get("bid", price))
            ask = float(data.get("ask", price))
            vol = float(data.get("volume", 0.0))
            return NormalisedTicker(
                symbol=symbol,
                base_asset=symbol.replace("USDT", ""),
                quote_asset="USDT",
                price=price,
                bid=bid,
                ask=ask,
                volume_24h=vol,
                source="coinbase",
                exchange_timestamp=start_t,
                received_at=time.time(),
            )
        except (URLError, TimeoutError, ValueError, KeyError) as err:
            logger.debug("Coinbase fetch failed for %s: %s", symbol, err)
            return None
