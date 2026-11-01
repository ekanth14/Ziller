"""CoinGecko public market data adapter for listings, market caps, ranks, and 7d sparklines."""
import json
import logging
import threading
import time
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cryptoscope.coingecko")


class CoinGeckoService:
    BASE_URL = "https://api.coingecko.com/api/v3"
    CACHE_TTL_SECONDS = 120.0  # Respect free tier rate limits (10-30 req/min)

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.cached_listings: List[Dict[str, Any]] = []
        self.last_fetch: float = 0.0
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()

    def get_top_listings(self, per_page: int = 50, page: int = 1) -> Dict[str, Any]:
        """Return cached top crypto assets with market cap, sparklines, and volume."""
        with self._lock:
            if not self.cached_listings or (time.time() - self.last_fetch > self.CACHE_TTL_SECONDS):
                self._fetch_markets_locked(per_page=100)

            now = time.time()
            age = max(0.0, now - self.last_fetch) if self.last_fetch > 0 else None
            is_stale = (age > self.CACHE_TTL_SECONDS) if age is not None else True

            # Paginate in memory from top list
            start = (page - 1) * per_page
            end = start + per_page
            items = self.cached_listings[start:end]

            return {
                "items": items,
                "total": len(self.cached_listings),
                "page": page,
                "per_page": per_page,
                "age_seconds": round(age, 1) if age else None,
                "stale": is_stale,
                "attribution": "Data provided by CoinGecko (Public API)",
                "error": self.last_error if is_stale else None,
            }

    def _fetch_markets_locked(self, per_page: int = 100):
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
            with urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                parsed = []
                for row in data:
                    sparkline_data = row.get("sparkline_in_7d", {}).get("price", [])
                    parsed.append({
                        "id": row.get("id"),
                        "symbol": (row.get("symbol") or "").upper() + "USDT",
                        "base_symbol": (row.get("symbol") or "").upper(),
                        "name": row.get("name"),
                        "image": row.get("image"),
                        "current_price": float(row.get("current_price") or 0.0),
                        "market_cap": float(row.get("market_cap") or 0.0),
                        "market_cap_rank": int(row.get("market_cap_rank") or 9999),
                        "total_volume": float(row.get("total_volume") or 0.0),
                        "high_24h": float(row.get("high_24h") or 0.0),
                        "low_24h": float(row.get("low_24h") or 0.0),
                        "price_change_percentage_1h": float(row.get("price_change_percentage_1h_in_currency") or 0.0),
                        "price_change_percentage_24h": float(row.get("price_change_percentage_24h") or 0.0),
                        "price_change_percentage_7d": float(row.get("price_change_percentage_7d_in_currency") or 0.0),
                        "price_change_percentage_30d": float(row.get("price_change_percentage_30d_in_currency") or 0.0),
                        "sparkline_7d": sparkline_data[-24:] if len(sparkline_data) >= 24 else sparkline_data,
                        "circulating_supply": float(row.get("circulating_supply") or 0.0),
                        "source": "coingecko",
                    })
                self.cached_listings = parsed
                self.last_fetch = time.time()
                self.last_error = None
                logger.info("CoinGecko listings refreshed (%d assets)", len(parsed))
            else:
                self.last_error = "Unexpected CoinGecko response structure"
        except HTTPError as e:
            self.last_error = f"CoinGecko HTTP {e.code}: {e.reason}"
            logger.warning("CoinGecko fetch rate-limited or error: %s", self.last_error)
        except (URLError, TimeoutError, OSError) as e:
            self.last_error = f"CoinGecko network error: {e}"
            logger.debug("CoinGecko unreachable: %s", e)
