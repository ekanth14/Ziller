"""Paper-trading fill realism, after QuantConnect LEAN's fill and slippage models (ideas, not code).

LEAN behaviours mirrored here:
- Market buy fills at the ASK, market sell at the BID, plus slippage (EquityFillModel / ConstantSlippageModel).
- Stop-market sell: fills at the stop, but if price has already gapped THROUGH the stop, at the (worse)
  current price - the old paper engine always booked the stop price, which flattered losses.
- Limit (take-profit) sell: fills at the limit, or at the better current price if it gapped above.
- SpreadExecutionModel: skip a market entry when (ask - bid) / mid is wider than a threshold.
- TrailingStopRiskManagementModel: ratchet a long's stop to (peak price) * (1 - pct) - opt-in here.
- Insight period: a trade that has not hit target or stop by its horizon is closed at market (time stop).

Book prices come from Binance's public bookTicker (cached 1 s); if unavailable, a constant half-spread is used.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from typing import Dict, Optional, Tuple

DEFAULT_SLIPPAGE = 0.0005        # 5 bp per market fill when no live book is available (LEAN ConstantSlippageModel)
BAR_SECONDS = 900                # fleet bars are 15 m; horizon_bars * 900 s = time limit


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


class BookSource:
    """Best bid / ask from Binance's public bookTicker, cached per symbol for `ttl` seconds."""

    def __init__(self, fetch=None, ttl: float = 1.0):
        self.fetch = fetch or self._fetch
        self.ttl = ttl
        self._cache: Dict[str, Tuple[float, Optional[Tuple[float, float]]]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _fetch(symbol: str) -> Optional[Tuple[float, float]]:
        for base in ("https://api.binance.com", "https://data-api.binance.vision"):
            try:
                req = urllib.request.Request(f"{base}/api/v3/ticker/bookTicker?symbol={symbol}",
                                             headers={"User-Agent": "ZILLERS-Fills/1.0"})
                with urllib.request.urlopen(req, timeout=4) as r:  # noqa: S310 - fixed public hosts
                    d = json.loads(r.read().decode("utf-8"))
                bid, ask = float(d["bidPrice"]), float(d["askPrice"])
                if 0 < bid <= ask:
                    return bid, ask
            except Exception:
                continue
        return None

    def quote(self, symbol: str) -> Optional[Tuple[float, float]]:
        with self._lock:
            hit = self._cache.get(symbol)
            if hit and time.time() - hit[0] < self.ttl:
                return hit[1]
        q = self.fetch(symbol)
        with self._lock:
            self._cache[symbol] = (time.time(), q)
        return q


def market_fill(side: str, ref_price: float, quote: Optional[Tuple[float, float]],
                slippage: float = DEFAULT_SLIPPAGE) -> float:
    """Buy at the ask, sell at the bid; without a book, the reference price +/- a constant slippage."""
    if quote:
        bid, ask = quote
        return ask if side == "BUY" else bid
    return ref_price * (1 + slippage) if side == "BUY" else ref_price * (1 - slippage)


def spread_ok(quote: Optional[Tuple[float, float]], max_spread: float) -> Tuple[bool, Optional[float]]:
    """LEAN SpreadExecutionModel: accept a market entry only if (ask - bid) / mid <= max_spread."""
    if not quote:
        return True, None                                   # no book: no opinion (fail open)
    bid, ask = quote
    spread = (ask - bid) / ((ask + bid) / 2)
    return spread <= max_spread, spread


def long_exit(price: float, stop: float, target: float, expires_at: Optional[float], now: float,
              slippage: float = DEFAULT_SLIPPAGE) -> Optional[Tuple[str, float]]:
    """Exit decision and fill price for a long. Gaps fill at the market, never at a better stop price."""
    if price <= stop:
        return "STOP_LOSS", min(stop, price * (1 - slippage)) if price < stop else stop
    if price >= target:
        return "TAKE_PROFIT", max(target, price) if price > target else target
    if expires_at is not None and now >= expires_at:
        return "TIME_STOP", price * (1 - slippage)
    return None


def trail_stop(stop: float, peak: float, pct: Optional[float]) -> float:
    """Ratchet a long's stop up to peak * (1 - pct); never moves down. pct None/0 disables."""
    return max(stop, peak * (1 - pct)) if pct else stop


def settings() -> Dict[str, Optional[float]]:
    trail = _env_float("ZILLERS_TRAILING_STOP_PCT", 0.0)
    return {"max_entry_spread": _env_float("ZILLERS_MAX_ENTRY_SPREAD", 0.003),
            "trailing_pct": trail if trail > 0 else None,
            "slippage": _env_float("ZILLERS_PAPER_SLIPPAGE", DEFAULT_SLIPPAGE)}
