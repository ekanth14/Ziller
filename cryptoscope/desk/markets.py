"""Every coin listed on Binance spot, grouped by base asset, priced in USD.

Data: /api/v3/exchangeInfo (TRADING spot pairs) + /api/v3/ticker/24hr (all pairs), both public.
- USD value of a quote currency: 1 for USD stablecoins; QUOTEUSDT price if that pair exists;
  1 / USDTQUOTE for fiat quoted the other way (TRY, BRL, IDR, JPY, ...).
- Coin price/change: the most liquid pair with a known USD quote (USDT preferred on ties).
- 24h volume: sum over all of the coin's pairs, converted to USD.
Optional enrichment (name, rank, market cap, logo) from the dashboard's CoinGecko cache.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from cryptoscope.desk.scanner import _get
from cryptoscope.desk.feed import ENDPOINTS

USD_STABLES = {"USDT", "USDC", "FDUSD", "USD1", "U", "USD", "USDS", "TUSD", "DAI", "USDP"}


def fetch_exchange_info() -> List[Dict[str, Any]]:
    last = None
    for base in ENDPOINTS:
        try:
            return _get(f"{base}/api/v3/exchangeInfo?permissions=SPOT", timeout=20)["symbols"]
        except Exception as exc:
            last = exc
    raise RuntimeError(f"exchangeInfo unavailable: {type(last).__name__}")


def fetch_all_tickers() -> List[Dict[str, Any]]:
    last = None
    for base in ENDPOINTS:
        try:
            return _get(f"{base}/api/v3/ticker/24hr", timeout=20)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"24h tickers unavailable: {type(last).__name__}")


def build_markets(symbols: List[Dict[str, Any]], tickers: List[Dict[str, Any]],
                  meta: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    trading = {s["symbol"]: s for s in symbols if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed", True)}
    tick = {t["symbol"]: t for t in tickers if t.get("symbol") in trading}
    last = {sym: float(t["lastPrice"]) for sym, t in tick.items() if float(t.get("lastPrice") or 0) > 0}

    def usd_rate(quote: str) -> Optional[float]:
        if quote in USD_STABLES:
            return 1.0
        if f"{quote}USDT" in last:
            return last[f"{quote}USDT"]
        if f"USDT{quote}" in last:
            return 1.0 / last[f"USDT{quote}"]
        return None

    coins: Dict[str, Dict[str, Any]] = {}
    for sym, s in trading.items():
        base, quote = s["baseAsset"], s["quoteAsset"]
        c = coins.setdefault(base, {"asset": base, "pairs": [], "quotes": [], "volume_usd": 0.0, "trades_24h": 0})
        c["quotes"].append(quote)
        t = tick.get(sym)
        rate = usd_rate(quote)
        qv = float(t["quoteVolume"]) if t else 0.0
        vol_usd = qv * rate if rate else None
        c["pairs"].append({"symbol": sym, "quote": quote, "last": last.get(sym), "volume_usd": vol_usd,
                           "chg_24h": float(t["priceChangePercent"]) / 100 if t else None})
        if vol_usd:
            c["volume_usd"] += vol_usd
        c["trades_24h"] += int(t.get("count", 0)) if t else 0

    rows = []
    for base, c in coins.items():
        priced = [p for p in c["pairs"] if p["last"] and usd_rate(p["quote"])]
        ref = max(priced, key=lambda p: ((p["volume_usd"] or 0), p["quote"] == "USDT"), default=None)
        price = ref["last"] * usd_rate(ref["quote"]) if ref else None
        usdt = f"{base}USDT" if f"{base}USDT" in trading else None
        m = (meta or {}).get(base) or {}
        rows.append({
            "asset": base, "name": m.get("name"), "rank": m.get("market_cap_rank"), "market_cap": m.get("market_cap"),
            "image": m.get("image"), "price_usd": price, "chg_24h": ref["chg_24h"] if ref else None,
            "ref_pair": ref["symbol"] if ref else None, "usdt_pair": usdt, "volume_usd": round(c["volume_usd"], 2),
            "trades_24h": c["trades_24h"], "pair_count": len(c["pairs"]), "quotes": sorted(set(c["quotes"])),
            "pairs": sorted(c["pairs"], key=lambda p: -(p["volume_usd"] or 0)),
        })
    rows.sort(key=lambda r: -r["volume_usd"])
    quotes: Dict[str, int] = {}
    for s in trading.values():
        quotes[s["quoteAsset"]] = quotes.get(s["quoteAsset"], 0) + 1
    return {"status": "OK", "coins": rows, "counts": {"coins": len(rows), "pairs": len(trading), "quotes": len(quotes)},
            "quote_counts": dict(sorted(quotes.items(), key=lambda kv: -kv[1])),
            "total_volume_usd": round(sum(r["volume_usd"] for r in rows), 2)}


class MarketDirectory:
    def __init__(self, ttl_seconds: float = 60.0, info_ttl: float = 3600.0,
                 info_fetcher: Callable[[], List[Dict[str, Any]]] = fetch_exchange_info,
                 tickers_fetcher: Callable[[], List[Dict[str, Any]]] = fetch_all_tickers,
                 meta_fetcher: Optional[Callable[[], Dict[str, Dict[str, Any]]]] = None):
        self.ttl, self.info_ttl = ttl_seconds, info_ttl
        self.info_fetcher, self.tickers_fetcher, self.meta_fetcher = info_fetcher, tickers_fetcher, meta_fetcher
        self._info: tuple[float, list] | None = None
        self._cache: tuple[float, Dict[str, Any]] | None = None
        self._lock = threading.Lock()

    def markets(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            if self._cache and now - self._cache[0] < self.ttl:
                return self._cache[1]
        try:
            if not self._info or now - self._info[0] > self.info_ttl:
                self._info = (now, self.info_fetcher())
            tickers = self.tickers_fetcher()
        except Exception as exc:
            if self._cache:
                return {**self._cache[1], "status": "STALE", "error": str(exc)}
            return {"status": "UNAVAILABLE", "error": str(exc), "coins": []}
        meta = {}
        if self.meta_fetcher:
            try:
                meta = self.meta_fetcher()
            except Exception:
                meta = {}
        result = build_markets(self._info[1], tickers, meta)
        result["generated_at"] = now
        with self._lock:
            self._cache = (now, result)
        return result
