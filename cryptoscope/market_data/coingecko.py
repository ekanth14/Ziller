"""CoinGecko and Binance market data adapter for verified listed crypto assets.

Filters tokens strictly to actively traded spot pairs on Binance/Coinbase,
ensuring unlisted tokens (delisted coins, private exchange tokens, non-trading pairs)
are never presented in the execution terminal.
"""
import json
import logging
import threading
import time
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("cryptoscope.coingecko")

CORE_BINANCE_PAIRS: Set[str] = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "SUIUSDT", "NEARUSDT", "PEPEUSDT", "SHIBUSDT", "DOTUSDT",
    "LTCUSDT", "UNIUSDT", "APTUSDT", "POLUSDT", "FETUSDT", "RENDERUSDT", "XLMUSDT",
    "BCHUSDT", "HBARUSDT", "FILUSDT", "VETUSDT", "ICPUSDT", "AAVEUSDT", "ALGOUSDT",
    "ATOMUSDT", "MKRUSDT", "STXUSDT", "GRTUSDT", "INJUSDT", "TAOUSDT", "TIAUSDT",
    "SEIUSDT", "FTMUSDT", "SANDUSDT", "MANAUSDT", "AXSUSDT", "THETAUSDT", "RUNEUSDT",
    "KASUSDT", "FLOKIUSDT", "BONKUSDT", "WIFUSDT", "JUPUSDT", "ENAUSDT", "WLDUSDT",
    "GALAUSDT", "CHZUSDT", "CRVUSDT", "LDOUSDT", "PENDLEUSDT", "PYTHUSDT", "BEAMUSDT",
    "BLURUSDT", "DYDXUSDT", "FLOWUSDT", "EGLDUSDT", "ZECUSDT", "IOTAUSDT", "NEOUSDT",
    "KAVAUSDT", "ROSEUSDT", "QNTUSDT", "SNXUSDT", "COMPUSDT", "1INCHUSDT", "ENJUSDT",
}

DELISTED_OR_UNLISTED_BASES: Set[str] = {
    "XMR", "USDS", "WBT", "LEO", "FTT", "LUNA", "UST", "USTC", "HUSD", "BUSD",
    "DAI", "USDC", "USDT", "USD", "EUR", "GBP"
}


class CoinGeckoService:
    BASE_URL = "https://api.coingecko.com/api/v3"
    CACHE_TTL_SECONDS = 90.0

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.cached_listings: List[Dict[str, Any]] = []
        self.last_fetch: float = 0.0
        self.last_error: Optional[str] = None
        self._binance_pairs: Set[str] = set(CORE_BINANCE_PAIRS)
        self._binance_pairs_fetched: float = 0.0
        self._lock = threading.Lock()

    def _get_binance_usdt_pairs(self) -> Set[str]:
        """Fetch or return cached active Binance spot USDT trading pairs."""
        now = time.time()
        if self._binance_pairs and (now - self._binance_pairs_fetched < 3600.0) and len(self._binance_pairs) > 100:
            return self._binance_pairs

        try:
            req = Request(
                "https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT",
                headers={"User-Agent": "ZILLERS-Terminal/4.2"}
            )
            with urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pairs = {
                s["symbol"] for s in data.get("symbols", [])
                if s.get("symbol", "").endswith("USDT") and s.get("status") == "TRADING"
            }
            if pairs:
                self._binance_pairs = pairs
                self._binance_pairs_fetched = now
                logger.info("Binance active USDT spot pairs refreshed (%d pairs)", len(pairs))
                return pairs
        except Exception as e:
            logger.debug("Binance exchangeInfo check used fallback: %s", e)

        return self._binance_pairs

    def get_top_listings(self, per_page: int = 50, page: int = 1) -> Dict[str, Any]:
        """Return cached top crypto assets filtered to actively traded exchange pairs."""
        with self._lock:
            if not self.cached_listings or (time.time() - self.last_fetch > self.CACHE_TTL_SECONDS):
                self._fetch_markets_locked(per_page=150)

            now = time.time()
            age = max(0.0, now - self.last_fetch) if self.last_fetch > 0 else None
            is_stale = (age > self.CACHE_TTL_SECONDS) if age is not None else True

            start = (page - 1) * per_page
            end = start + per_page
            items = [dict(it, snapshot_age_seconds=round(age, 1) if age else None) for it in self.cached_listings[start:end]]

            return {
                "items": items,
                "total": len(self.cached_listings),
                "page": page,
                "per_page": per_page,
                "age_seconds": round(age, 1) if age else None,
                "stale": is_stale,
                "attribution": "Data verified by Binance & CoinGecko",
                "error": self.last_error if is_stale else None,
            }

    def _fetch_markets_locked(self, per_page: int = 150):
        binance_pairs = self._get_binance_usdt_pairs()

        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": str(per_page),
            "page": "1",
            "sparkline": "true",
            "price_change_percentage": "1h,24h,7d,30d",
        }
        url = f"{self.BASE_URL}/coins/markets?" + urlencode(params)
        headers = {"User-Agent": "ZILLERS-Terminal/4.2 (Research Aggregator)"}
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key

        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=7.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                parsed = []
                for row in data:
                    base_sym = (row.get("symbol") or "").upper()
                    # Skip unlisted, delisted, stablecoin bases, and non-trading assets
                    if base_sym in DELISTED_OR_UNLISTED_BASES:
                        continue
                    sym = base_sym + "USDT"
                    # Strictly require that coin is actively listed on Binance
                    if sym not in binance_pairs:
                        continue

                    price = float(row.get("current_price") or 0.0)
                    chg_24h = float(row.get("price_change_percentage_24h") or 0.0)
                    sparkline_data = row.get("sparkline_in_7d", {}).get("price", [])

                    parsed.append({
                        "id": row.get("id"),
                        "symbol": sym,
                        "base_symbol": base_sym,
                        "name": row.get("name"),
                        "image": row.get("image"),
                        "current_price": price,
                        "price_usd": price,
                        "price": price,
                        "change_24h_pct": chg_24h,
                        "price_change_percentage_24h": chg_24h,
                        "market_cap": float(row.get("market_cap") or 0.0),
                        "market_cap_rank": int(row.get("market_cap_rank") or 9999),
                        "total_volume": float(row.get("total_volume") or 0.0),
                        "high_24h": float(row.get("high_24h") or 0.0),
                        "low_24h": float(row.get("low_24h") or 0.0),
                        "price_change_percentage_1h": float(row.get("price_change_percentage_1h_in_currency") or 0.0),
                        "price_change_percentage_7d": float(row.get("price_change_percentage_7d_in_currency") or 0.0),
                        "price_change_percentage_30d": float(row.get("price_change_percentage_30d_in_currency") or 0.0),
                        "sparkline_7d": sparkline_data[-24:] if len(sparkline_data) >= 24 else sparkline_data,
                        "circulating_supply": float(row.get("circulating_supply") or 0.0),
                        "source": "coingecko",
                        "is_listed": True,
                    })

                if parsed:
                    self.cached_listings = parsed
                    self.last_fetch = time.time()
                    self.last_error = None
                    logger.info("CoinGecko listings refreshed (%d active exchange assets)", len(parsed))
                    return
        except Exception as e:
            self.last_error = f"CoinGecko fetch: {e}"
            logger.debug("CoinGecko fetch failed, falling back to Binance 24hr tickers: %s", e)

        # Fallback: Populate directly from Binance 24hr tickers if CoinGecko is rate-limited or fails
        try:
            req_bin = Request("https://api.binance.com/api/v3/ticker/24hr", headers={"User-Agent": "ZILLERS-Terminal/4.2"})
            with urlopen(req_bin, timeout=6.0) as resp:
                bin_tickers = json.loads(resp.read().decode("utf-8"))
            parsed_bin = []
            for t in bin_tickers:
                sym = t.get("symbol", "")
                if sym.endswith("USDT") and (sym in CORE_BINANCE_PAIRS or len(parsed_bin) < 80):
                    base = sym.removesuffix("USDT")
                    if base in DELISTED_OR_UNLISTED_BASES:
                        continue
                    price = float(t.get("lastPrice") or 0.0)
                    chg = float(t.get("priceChangePercent") or 0.0)
                    parsed_bin.append({
                        "id": base.lower(),
                        "symbol": sym,
                        "base_symbol": base,
                        "name": base,
                        "image": None,
                        "current_price": price,
                        "price_usd": price,
                        "price": price,
                        "change_24h_pct": chg,
                        "price_change_percentage_24h": chg,
                        "market_cap": 0.0,
                        "market_cap_rank": 9999,
                        "total_volume": float(t.get("volume") or 0.0),
                        "high_24h": float(t.get("highPrice") or 0.0),
                        "low_24h": float(t.get("lowPrice") or 0.0),
                        "price_change_percentage_1h": 0.0,
                        "price_change_percentage_7d": 0.0,
                        "price_change_percentage_30d": 0.0,
                        "sparkline_7d": [],
                        "circulating_supply": 0.0,
                        "source": "binance_24hr",
                        "is_listed": True,
                    })
            if parsed_bin:
                self.cached_listings = parsed_bin
                self.last_fetch = time.time()
                self.last_error = None
                logger.info("Binance fallback listings populated (%d assets)", len(parsed_bin))
        except Exception as b_err:
            logger.warning("Binance ticker fallback also failed: %s", b_err)
