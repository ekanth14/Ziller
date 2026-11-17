"""Daily candle feed for the Action Desk (public Binance spot klines, no credentials)."""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptoscope.desk.engine import INTERVALS, build_desk

ENDPOINTS = ("https://api.binance.com", "https://data-api.binance.vision")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")
DAY = 86400.0


def fetch_klines(symbol: str, interval: str = "1d", limit: int = 700, timeout: float = 8.0) -> List[Dict[str, float]]:
    """Fetch candles for any supported interval, oldest first. Tries the public fallback host on failure."""
    if interval not in INTERVALS:
        raise ValueError("Unsupported interval")
    query = urlencode({"symbol": symbol, "interval": interval, "limit": limit})
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
    raise RuntimeError(f"Candles unavailable: {type(last_error).__name__}")


def fetch_daily_klines(symbol: str, limit: int = 700, timeout: float = 8.0) -> List[Dict[str, float]]:
    return fetch_klines(symbol, "1d", limit, timeout)


class DeskFeed:
    """Caches the computed desk per symbol for a short time so page polling stays cheap."""

    def __init__(self, ttl_seconds: float = 30.0, fetcher=fetch_klines, with_ai: bool = True, ollama_status=None,
                 llm_panel=None):
        self.ttl = ttl_seconds
        self.fetcher = fetcher
        self.with_ai = with_ai
        self.ollama_status = ollama_status
        self.llm_panel = llm_panel
        self._fast_layer = None
        self._cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def _layer(self):
        if self._fast_layer is None:
            from cryptoscope.autotrader.decision import FastDecisionLayer
            self._fast_layer = FastDecisionLayer()
        return self._fast_layer

    def desk(self, symbol: str, fee_bps: float = 10.0, interval: str = "1d") -> Dict[str, Any]:
        symbol = (symbol or "").upper()
        if not SYMBOL_RE.match(symbol):
            raise ValueError("Invalid symbol")
        if not (0 <= fee_bps <= 100):
            raise ValueError("fee_bps must be between 0 and 100")
        if interval not in INTERVALS:
            raise ValueError("interval must be one of " + ", ".join(INTERVALS))
        step = INTERVALS[interval]
        ttl = min(self.ttl, max(5.0, step / 4))  # 1m charts refresh faster than daily ones
        key = f"{symbol}:{fee_bps}:{interval}"
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < ttl:
                return hit[1]
        try:
            try:
                candles = self.fetcher(symbol, interval)
            except TypeError:  # simple fetchers (tests) that only take a symbol
                candles = self.fetcher(symbol)
        except Exception as exc:
            return {"status": "UNAVAILABLE", "symbol": symbol, "error": str(exc)}
        forming = bool(candles) and now < candles[-1]["open_time"] + step
        result = build_desk(candles, symbol=symbol, fee_bps=fee_bps, bar_forming=forming, interval=interval)
        if result.get("status") == "OK" and self.with_ai:
            from cryptoscope.desk.ai_layer import ai_overlay
            closed = candles[:-1] if forming else candles
            result["ai"] = ai_overlay(closed, symbol, result, layer=self._layer(), bar_seconds=step,
                                      llm_panel=self.llm_panel, interval=interval,
                                      ollama_status=self.ollama_status() if self.ollama_status else None)
        result.pop("all_trades", None)
        result["source"] = f"Binance spot · {interval}"
        result["generated_at"] = now
        with self._lock:
            self._cache[key] = (now, result)
        return result


_LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def fetch_spot_symbols(quote: str = "USDT", timeout: float = 10.0) -> List[Dict[str, str]]:
    """All Binance spot pairs currently TRADING against `quote` (leveraged tokens excluded)."""
    last_error: Exception | None = None
    for base_url in ENDPOINTS:
        try:
            req = Request(f"{base_url}/api/v3/exchangeInfo?permissions=SPOT", headers={"User-Agent": "ZILLERS-Desk/1.0"})
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
                info = json.loads(resp.read().decode("utf-8"))
            out = []
            for s in info.get("symbols", []):
                base = s.get("baseAsset", "")
                if (s.get("status") == "TRADING" and s.get("quoteAsset") == quote and s.get("isSpotTradingAllowed", True)
                        and not base.endswith(_LEVERAGED_SUFFIXES) and SYMBOL_RE.match(s.get("symbol", ""))):
                    out.append({"symbol": s["symbol"], "base": base, "quote": quote})
            return sorted(out, key=lambda x: x["symbol"])
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Symbol list unavailable: {type(last_error).__name__}")


class SymbolDirectory:
    """Caches the Binance spot symbol list (refreshes hourly)."""

    def __init__(self, ttl_seconds: float = 3600.0, fetcher=fetch_spot_symbols):
        self.ttl, self.fetcher = ttl_seconds, fetcher
        self._cached: tuple[float, List[Dict[str, str]]] | None = None
        self._lock = threading.Lock()

    def symbols(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            if self._cached and now - self._cached[0] < self.ttl:
                return {"status": "OK", "symbols": self._cached[1], "fetched_at": self._cached[0]}
        try:
            rows = self.fetcher()
        except Exception as exc:
            if self._cached:  # keep serving the last good list rather than nothing
                return {"status": "STALE", "symbols": self._cached[1], "fetched_at": self._cached[0], "error": str(exc)}
            return {"status": "UNAVAILABLE", "symbols": [], "error": str(exc)}
        with self._lock:
            self._cached = (now, rows)
        return {"status": "OK", "symbols": rows, "fetched_at": now}
