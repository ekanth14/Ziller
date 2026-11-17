"""Market-structure data for one coin: perpetual funding, open interest, positioning, taker flow
and spot order-book depth. All from Binance public endpoints; nothing is estimated.

Formulas
- Funding APR          = last funding rate x 3 settlements/day x 365
- Basis (premium)      = (mark - index) / index
- OI change 24h        = OI value now / OI value 24 h ago - 1           (1h history)
- Spread (bps)         = (best ask - best bid) / mid x 10,000
- Depth +/-x%          = sum(price x qty) of bids >= mid(1-x) and asks <= mid(1+x)
- Book imbalance       = (bid depth - ask depth) / (bid depth + ask depth)   within +/-1%
- Microprice           = (ask x bid_qty + bid x ask_qty) / (bid_qty + ask_qty)
Readings use common rules of thumb (e.g. funding above +0.05%/8h = crowded longs); they are
context for a human, not trade signals.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from cryptoscope.desk.scanner import _get

FAPI = "https://fapi.binance.com"
SPOT = "https://api.binance.com"


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def book_metrics(depth: Dict[str, Any]) -> Dict[str, Any]:
    bids = [(float(p), float(q)) for p, q in depth.get("bids", [])]
    asks = [(float(p), float(q)) for p, q in depth.get("asks", [])]
    if not bids or not asks:
        return {"available": False}
    (bb, bq), (ba, aq) = bids[0], asks[0]
    mid = (bb + ba) / 2

    def within(x):
        b = sum(p * q for p, q in bids if p >= mid * (1 - x))
        a = sum(p * q for p, q in asks if p <= mid * (1 + x))
        return b, a

    b1, a1 = within(0.01)
    b2, a2 = within(0.02)
    return {"available": True, "best_bid": bb, "best_ask": ba, "mid": mid,
            "spread_bps": (ba - bb) / mid * 1e4, "microprice": (ba * bq + bb * aq) / (bq + aq) if bq + aq else mid,
            "bid_depth_1pct": b1, "ask_depth_1pct": a1, "bid_depth_2pct": b2, "ask_depth_2pct": a2,
            "imbalance_1pct": (b1 - a1) / (b1 + a1) if b1 + a1 else 0.0,
            "levels": len(bids) + len(asks), "book_reaches_1pct": bids[-1][0] <= mid * 0.99 and asks[-1][0] >= mid * 1.01}


def readings(d: Dict[str, Any]) -> List[str]:
    out = []
    f = d.get("funding") or {}
    if f.get("rate") is not None:
        r = f["rate"]
        if r >= 0.0005:
            out.append(f"Funding {r:+.4%}/8h: longs are paying heavily — crowded long positioning.")
        elif r <= -0.0003:
            out.append(f"Funding {r:+.4%}/8h: shorts are paying — crowded short positioning (squeeze risk).")
        else:
            out.append(f"Funding {r:+.4%}/8h: neutral positioning.")
    oi, chg = d.get("open_interest") or {}, d.get("price_change_24h")
    if oi.get("change_24h") is not None and chg is not None:
        rising_oi, rising_px = oi["change_24h"] > 0.02, chg > 0
        if rising_oi and rising_px:
            out.append("Open interest and price both rising: new longs entering (trend-confirming).")
        elif rising_oi and not rising_px:
            out.append("Open interest rising while price falls: new shorts entering.")
        elif oi["change_24h"] < -0.02:
            out.append("Open interest falling: positions closing (de-leveraging).")
    b = d.get("book") or {}
    if b.get("available"):
        imb = b["imbalance_1pct"]
        if abs(imb) > 0.25:
            out.append(f"Order book within ±1% is {'bid' if imb > 0 else 'ask'}-heavy ({imb:+.0%}).")
        if b["spread_bps"] > 10:
            out.append(f"Wide spread ({b['spread_bps']:.1f} bps): trade with limit orders.")
    return out


class MarketStructure:
    def __init__(self, ttl_seconds: float = 30.0, getter: Callable[[str], Any] = _get):
        self.ttl, self.get = ttl_seconds, getter
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    def snapshot(self, symbol: str) -> Dict[str, Any]:
        symbol = symbol.upper()
        now = time.time()
        with self._lock:
            hit = self._cache.get(symbol)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        # Low-priced coins trade on futures as 1000x contracts (e.g. PEPEUSDT -> 1000PEPEUSDT).
        perp = symbol
        try:
            self.get(f"{FAPI}/fapi/v1/premiumIndex?symbol={symbol}")
        except Exception:
            try:
                self.get(f"{FAPI}/fapi/v1/premiumIndex?symbol=1000{symbol}")
                perp = f"1000{symbol}"
            except Exception:
                pass
        q, fq = f"symbol={symbol}", f"symbol={perp}"
        jobs = {
            "premium": f"{FAPI}/fapi/v1/premiumIndex?{fq}",
            "oi_hist": f"{FAPI}/futures/data/openInterestHist?{fq}&period=1h&limit=25",
            "ls": f"{FAPI}/futures/data/globalLongShortAccountRatio?{fq}&period=1h&limit=25",
            "taker": f"{FAPI}/futures/data/takerlongshortRatio?{fq}&period=1h&limit=24",
            "depth": f"{SPOT}/api/v3/depth?{q}&limit=500",
            "ticker": f"{SPOT}/api/v3/ticker/24hr?{q}",
        }
        res: Dict[str, Any] = {}

        def fetch(k):
            try:
                res[k] = self.get(jobs[k])
            except Exception as exc:
                res[k] = exc

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(fetch, jobs))
        ok = lambda k: not isinstance(res.get(k), Exception) and res.get(k) not in (None, [], {})  # noqa: E731
        out: Dict[str, Any] = {"symbol": symbol, "perp_symbol": perp if ok("premium") else None,
                               "generated_at": now, "perpetual": ok("premium")}
        if ok("ticker"):
            out["price_change_24h"] = _f(res["ticker"].get("priceChangePercent")) / 100
        if ok("premium"):
            p = res["premium"]
            rate, mark, index = _f(p.get("lastFundingRate")), _f(p.get("markPrice")), _f(p.get("indexPrice"))
            out["funding"] = {"rate": rate, "apr": rate * 3 * 365 if rate is not None else None, "mark": mark, "index": index,
                              "basis": (mark - index) / index if mark and index else None,
                              "next_funding_time": (_f(p.get("nextFundingTime")) or 0) / 1000 or None}
        if ok("oi_hist"):
            h = res["oi_hist"]
            last, first = _f(h[-1].get("sumOpenInterestValue")), _f(h[0].get("sumOpenInterestValue"))
            out["open_interest"] = {"value_usd": last, "contracts": _f(h[-1].get("sumOpenInterest")),
                                    "change_24h": last / first - 1 if last and first else None,
                                    "history": [_f(x.get("sumOpenInterestValue")) for x in h]}
        if ok("ls"):
            h = res["ls"]
            out["long_short"] = {"ratio": _f(h[-1].get("longShortRatio")), "long_pct": _f(h[-1].get("longAccount")),
                                 "ratio_24h_ago": _f(h[0].get("longShortRatio"))}
        if ok("taker"):
            h = res["taker"]
            buy, sell = sum(_f(x.get("buyVol")) or 0 for x in h), sum(_f(x.get("sellVol")) or 0 for x in h)
            out["taker_flow"] = {"buy_sell_ratio_1h": _f(h[-1].get("buySellRatio")),
                                 "buy_sell_ratio_24h": buy / sell if sell else None}
        out["book"] = book_metrics(res["depth"]) if ok("depth") else {"available": False}
        out["readings"] = readings(out)
        out["errors"] = sorted(k for k in jobs if isinstance(res.get(k), Exception))
        with self._lock:
            self._cache[symbol] = (now, out)
        return out
