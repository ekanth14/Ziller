"""Market-wide entry filters for long-only spot (deep-research report: regime filters were the most useful
long-only addition; funding extremes as a crowding warning). Both are VETO-ONLY and fail OPEN: missing data
means "no opinion", never a forced trade and never a blocked fleet.

- BTC trend gate: no NEW long entries while BTC's daily close is below its 50-day SMA (altcoins are highly
  correlated with BTC; most long-only drawdowns happen in BTC downtrends). Parameters are a pre-registered
  convention, not tuned; the research warns such gates are parameter-sensitive.
- Funding-rate filter: Binance USD-M perpetual funding is public (no API key). A very positive rate means
  crowded leveraged longs; BitMEX research found extreme positive funding precedes weaker returns over the
  next 8 h. Veto a NEW long when the coin's perpetual funding is above +0.05% per 8 h (~55% a year).

Environment: ZILLERS_BTC_GATE=1 enables the BTC gate (off by default: it halts every new entry during a BTC
downtrend); ZILLERS_FUNDING_FILTER=0 disables the funding filter; ZILLERS_FUNDING_MAX sets its threshold.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional


def _get_json(url: str, timeout: float = 6.0):
    req = urllib.request.Request(url, headers={"User-Agent": "ZILLERS-Filters/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed public https hosts
        return json.loads(r.read().decode("utf-8"))


def _btc_daily_closes(n: int = 60) -> List[float]:
    from cryptoscope.desk.feed import fetch_klines
    return [b["close"] for b in fetch_klines("BTCUSDT", "1d", n)[:-1]]   # closed days only


def _funding(symbol: str) -> Optional[float]:
    try:
        d = _get_json(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}")
    except Exception:
        return None                       # no perpetual for this coin, or futures API unreachable
    try:
        return float(d["lastFundingRate"])
    except (KeyError, TypeError, ValueError):
        return None


class BtcTrendGate:
    def __init__(self, closes: Callable[[], List[float]] = _btc_daily_closes, sma: int = 50, ttl: float = 900.0):
        self.closes, self.sma, self.ttl = closes, sma, ttl
        self._lock = threading.Lock()
        self._state: Optional[Dict[str, Any]] = None
        self._at = 0.0

    def state(self) -> Dict[str, Any]:
        with self._lock:
            if self._state is not None and time.time() - self._at < self.ttl:
                return self._state
            try:
                c = self.closes()
                if len(c) < self.sma:
                    raise ValueError("not enough BTC history")
                avg = sum(c[-self.sma:]) / self.sma
                self._state = {"ok": True, "btc_close": c[-1], "sma": avg, "uptrend": c[-1] > avg}
            except Exception as exc:
                self._state = {"ok": False, "error": type(exc).__name__, "uptrend": None}
            self._at = time.time()
            return self._state

    def veto(self) -> Optional[str]:
        s = self.state()
        if s.get("uptrend") is False:
            return (f"BTC_DOWNTREND: BTC daily close {s['btc_close']:.0f} is below its {self.sma}-day average "
                    f"{s['sma']:.0f}; no new longs (ZILLERS_BTC_GATE=0 disables).")
        return None


class FundingFilter:
    def __init__(self, fetch: Callable[[str], Optional[float]] = _funding, max_rate: Optional[float] = None,
                 ttl: float = 300.0):
        if max_rate is None:
            try:
                max_rate = float(os.environ.get("ZILLERS_FUNDING_MAX", "0.0005"))
            except ValueError:
                max_rate = 0.0005
        self.fetch, self.max_rate, self.ttl = fetch, max_rate, ttl
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    def rate(self, symbol: str) -> Optional[float]:
        with self._lock:
            hit = self._cache.get(symbol)
            if hit and time.time() - hit[0] < self.ttl:
                return hit[1]
        r = self.fetch(symbol)
        with self._lock:
            self._cache[symbol] = (time.time(), r)
        return r

    def veto(self, symbol: str) -> Optional[str]:
        r = self.rate(symbol)
        if r is not None and r > self.max_rate:
            return (f"FUNDING_CROWDED: {symbol} perpetual funding {r * 100:.3f}%/8h is above "
                    f"{self.max_rate * 100:.3f}%; leveraged longs are crowded.")
        return None


def default_filters() -> Dict[str, Any]:
    """Filters the live fleet uses (each can be switched off by environment)."""
    out: Dict[str, Any] = {}
    # OFF unless the operator opts in: in a BTC downtrend it stops ALL new entries (a large behaviour change).
    if os.environ.get("ZILLERS_BTC_GATE", "0") == "1":
        out["btc"] = BtcTrendGate()
    if os.environ.get("ZILLERS_FUNDING_FILTER", "1") != "0":
        out["funding"] = FundingFilter()
    return out
