"""Kraken public market data adapter for cross-exchange verification."""
import json
import logging
import threading
import time
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
from typing import Callable, Dict, List, Optional

from cryptoscope.market_data.base import NormalisedTicker

logger = logging.getLogger("cryptoscope.kraken_feed")


class KrakenFeed:
    REST_ENDPOINT = "https://api.kraken.com/0/public"

    # Map standard unified crypto symbols to Kraken pair names
    SYMBOL_MAP = {
        "BTCUSDT": "XBTUSDT",
        "ETHUSDT": "ETHUSDT",
        "SOLUSDT": "SOLUSDT",
    }

    REVERSE_MAP = {
        "XBTUSDT": "BTCUSDT",
        "ETHUSDT": "ETHUSDT",
        "SOLUSDT": "SOLUSDT",
    }

    def __init__(self, on_ticker: Callable[[NormalisedTicker], None], symbols: Optional[List[str]] = None):
        self.on_ticker = on_ticker
        self.symbols = [s.upper() for s in (symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"])]
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._consecutive_errors = 0

    def start(self):
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="KrakenFeed")
        self._poll_thread.start()
        logger.info("Kraken feed started with symbols: %s", self.symbols)

    def stop(self):
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)

    def _poll_loop(self):
        while self._running:
            try:
                pairs = [self.SYMBOL_MAP.get(s, s) for s in self.symbols]
                tickers = self.fetch_tickers(pairs)
                for t in tickers:
                    self.on_ticker(t)
                self._consecutive_errors = 0
                time.sleep(1.5)
            except Exception as e:
                self._consecutive_errors += 1
                logger.warning("Kraken poll error (consecutive=%d): %s", self._consecutive_errors, e)
                backoff = min(15.0, 1.0 * (1.5 ** min(self._consecutive_errors, 5)))
                time.sleep(backoff)

    def fetch_tickers(self, pairs: List[str]) -> List[NormalisedTicker]:
        pair_str = ",".join(pairs)
        url = f"{self.REST_ENDPOINT}/Ticker?pair={pair_str}"
        start_t = time.time()
        req = Request(url, headers={"User-Agent": "ZILLERS-Terminal/4.2"})
        try:
            with urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("error"):
                logger.warning("Kraken API error: %s", data["error"])
                return []

            result = data.get("result", {})
            tickers = []
            for kraken_pair, obj in result.items():
                std_symbol = self.REVERSE_MAP.get(kraken_pair)
                if not std_symbol:
                    for s in self.symbols:
                        if self.SYMBOL_MAP.get(s) == kraken_pair:
                            std_symbol = s
                            break
                if not std_symbol:
                    std_symbol = kraken_pair

                # Kraken ticker:
                # a: [ask, whole_lot_volume, lot_volume]
                # b: [bid, whole_lot_volume, lot_volume]
                # c: [last_price, lot_volume]
                # v: [today_volume, 24h_volume]
                # h: [today_high, 24h_high]
                # l: [today_low, 24h_low]
                # o: today_opening_price
                ask = float(obj["a"][0])
                bid = float(obj["b"][0])
                last_price = float(obj["c"][0])
                vol_24h = float(obj["v"][1])
                high_24h = float(obj["h"][1])
                low_24h = float(obj["l"][1])
                open_today = float(obj["o"])
                change_24h = ((last_price - open_today) / open_today * 100.0) if open_today > 0 else 0.0

                tickers.append(NormalisedTicker(
                    symbol=std_symbol,
                    base_asset=std_symbol.replace("USDT", ""),
                    quote_asset="USDT",
                    price=last_price,
                    bid=bid,
                    ask=ask,
                    high_24h=high_24h,
                    low_24h=low_24h,
                    volume_24h=vol_24h,
                    change_24h_pct=round(change_24h, 2),
                    source="kraken",
                    exchange_timestamp=start_t,
                    received_at=time.time(),
                ))
            return tickers
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as err:
            logger.debug("Kraken ticker fetch failed: %s", err)
            return []
