"""Daily candle feed for the Action Desk (public Binance spot klines, no credentials)."""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptoscope.desk.engine import build_desk

ENDPOINTS = ("https://api.binance.com", "https://data-api.binance.vision")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")
DAY = 86400.0


def fetch_daily_klines(symbol: str, limit: int = 700, timeout: float = 8.0) -> List[Dict[str, float]]:
    """Fetch daily candles, oldest first. Tries the public fallback host on failure."""
    query = urlencode({"symbol": symbol, "interval": "1d", "limit": limit})
    last_error: Exception | None = None
    for base in ENDPOINTS:
        try:
            req = Request(f"{base}/api/v3/klines?{query}", headers={"User-Agent": "ZILLERS-Desk/1.0"})
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
                rows = json.loads(resp.read().decode("utf-8"))
            return [{"open_time": r[0] / 1000.0, "open": float(r[1]), "high": float(r[2]), "low": float(r[3]),
                     "close": float(r[4]), "volume": float(r[5])} for r in rows]
        except Exception as exc:  # try the next host
            last_error = exc
    raise RuntimeError(f"Daily candles unavailable: {type(last_error).__name__}")


class DeskFeed:
    """Caches the computed desk per symbol for a short time so page polling stays cheap."""

    def __init__(self, ttl_seconds: float = 30.0, fetcher=fetch_daily_klines):
        self.ttl = ttl_seconds
        self.fetcher = fetcher
        self._cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def desk(self, symbol: str, fee_bps: float = 10.0) -> Dict[str, Any]:
        symbol = (symbol or "").upper()
        if not SYMBOL_RE.match(symbol):
            raise ValueError("Invalid symbol")
        if not (0 <= fee_bps <= 100):
            raise ValueError("fee_bps must be between 0 and 100")
        key = f"{symbol}:{fee_bps}"
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        try:
            candles = self.fetcher(symbol)
        except Exception as exc:
            return {"status": "UNAVAILABLE", "symbol": symbol, "error": str(exc)}
        forming = bool(candles) and now < candles[-1]["open_time"] + DAY
        result = build_desk(candles, symbol=symbol, fee_bps=fee_bps, bar_forming=forming)
        result["source"] = "Binance spot · daily"
        result["generated_at"] = now
        with self._lock:
            self._cache[key] = (now, result)
        return result
