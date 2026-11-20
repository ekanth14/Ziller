"""Market scanner: rank every Binance spot USDT pair and pick the top performers to trade.

Workflow
1. Universe   - every TRADING spot pair quoted in USDT (one /api/v3/ticker/24hr call).
2. Filters    - drop operator-excluded symbols (BTC/ETH/SOL by default, see cryptoscope.trading_universe),
                stablecoins/fiat and leveraged tokens; require 24h quote volume >= min_quote_volume;
                drop pairs that moved more than max_24h_move in 24h (pump/dump risk); TESTNET mode keeps
                only pairs that exist on the Binance Spot testnet.
3. Shortlist  - up to `shortlist` (default 250, i.e. effectively every liquid pair) survivors get 90 daily candles each.
4. Factors    - r7, r30 (returns), vol30 (annualised volatility of daily log returns),
                risk-adjusted momentum  M = (0.4*r7 + 0.6*r30) / vol30,
                trend  = close > SMA20 and SMA10 > SMA30,
                RSI14 (Wilder), ATR14% (ATR / close),
                drawdown from the 90-day high.
5. Eligibility- trend true, 45 <= RSI14 <= 78 (momentum but not blow-off), drawdown >= -25%,
                vol30 >= 10% (filters pegged/stable assets the name list misses).
6. Score      - z-scored blend across the shortlist:
                score = 0.45*z(M) + 0.25*z(r7) + 0.20*z(log quote volume) - 0.10*z(ATR14%)
7. Pick       - up to `top_n` (default 10, the fleet's maximum), filled tier by tier:
   a. TREND      - passes every daily filter above (best, slower swing setups);
   b. SHORT_TERM - 1h uptrend: close > EMA20(1h) > EMA50(1h) and 40 <= RSI14(1h) <= 72;
   c. POTENTIAL  - best remaining coins able to move 0.5-1% within hours, ranked by
                   short-term score = 0.35*z(r4h/ATR1h) + 0.25*z(r24h) + 0.25*z(log quote volume) + 0.15*z(1h volume surge).
   Tiers b and c always need 0.25% <= ATR1h% <= 3% (a 0.5-1% target must be reachable in a few hours,
   and hourly noise must not routinely hit a 0.5-1% stop)
   and exclude free-falls (24h <= -8% or 4h <= -3%). Set ZILLERS_SCANNER_FALLBACK=0 to use tier a only.

This chooses WHAT the fleet watches. Each entry still has to pass the fleet's own pipeline:
signal -> strategy -> debate -> RiskBot (sizing, correlation, drawdown, daily loss) -> execution.
Nothing here places orders.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.request import Request, urlopen

from cryptoscope.desk.feed import ENDPOINTS, fetch_klines
from cryptoscope.trading_universe import excluded_symbols

STABLE_BASES = {"USDC", "FDUSD", "TUSD", "DAI", "USDP", "BUSD", "USDD", "PYUSD", "EUR", "EURI", "AEUR", "GBP", "TRY",
                "BRL", "ARS", "UST", "USTC", "PAXG", "XUSD", "USD1", "BFUSD", "RLUSD", "USDE", "RWUSD", "U"}
MIN_VOL30 = 0.10  # below 10% annualised volatility the asset behaves like a peg/stablecoin
LEVERAGED = ("UP", "DOWN", "BULL", "BEAR")
TESTNET = "https://testnet.binance.vision"


def _get(url: str, timeout: float = 10.0):
    with urlopen(Request(url, headers={"User-Agent": "ZILLERS-Scanner/1.0"}), timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read())


def fetch_24h_tickers() -> List[Dict[str, Any]]:
    last = None
    for base in ENDPOINTS:
        try:
            return _get(f"{base}/api/v3/ticker/24hr?type=FULL", timeout=15)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"24h tickers unavailable: {type(last).__name__}")


def fetch_book_tickers() -> Dict[str, Dict[str, float]]:
    """Best bid/ask and their sizes for every symbol, in one public call."""
    last = None
    for base in ENDPOINTS:
        try:
            rows = _get(f"{base}/api/v3/ticker/bookTicker", timeout=15)
            return {r["symbol"]: {"bid": float(r["bidPrice"]), "ask": float(r["askPrice"]),
                                  "bid_qty": float(r["bidQty"]), "ask_qty": float(r["askQty"])} for r in rows}
        except Exception as exc:
            last = exc
    raise RuntimeError(f"book tickers unavailable: {type(last).__name__}")


def book_quality(book: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
    """Spread as a fraction of mid, and the thinner side of the top of book in USDT."""
    if not book or book["bid"] <= 0 or book["ask"] < book["bid"]:
        return None
    mid = (book["bid"] + book["ask"]) / 2
    return {"spread_pct": (book["ask"] - book["bid"]) / mid,
            "top_depth_usd": min(book["bid"] * book["bid_qty"], book["ask"] * book["ask_qty"])}


def fetch_trading_usdt_symbols(base_url: str) -> set:
    info = _get(f"{base_url}/api/v3/exchangeInfo?permissions=SPOT", timeout=15)
    return {s["symbol"] for s in info.get("symbols", [])
            if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT" and s.get("isSpotTradingAllowed", True)}


# --------------------------------------------------------------------------- factor maths
def _sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def _rsi(closes, n=14):
    if len(closes) <= n:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def factors(candles: List[Dict[str, float]]) -> Optional[Dict[str, float]]:
    """Daily-candle factors; None when there is not enough history (new listings)."""
    if len(candles) < 35:
        return None
    closes = [c["close"] for c in candles]
    last = closes[-1]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0 and closes[i] > 0]
    window = rets[-30:]
    m = sum(window) / len(window)
    vol30 = math.sqrt(sum((r - m) ** 2 for r in window) / (len(window) - 1)) * math.sqrt(365)
    r7 = last / closes[-8] - 1
    r30 = last / closes[-31] - 1
    trs = [max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"]))
           for p, c in zip(candles[-15:-1], candles[-14:])]
    atr_pct = (sum(trs) / len(trs)) / last
    sma10, sma20, sma30 = _sma(closes, 10), _sma(closes, 20), _sma(closes, 30)
    peak = max(c["high"] for c in candles[-90:])
    return {
        "r7": r7, "r30": r30, "vol30": vol30,
        "momentum": (0.4 * r7 + 0.6 * r30) / vol30 if vol30 > 0 else 0.0,
        "trend": bool(last > sma20 and sma10 > sma30), "rsi14": _rsi(closes[-60:]),
        "atr_pct": atr_pct, "drawdown": last / peak - 1, "sma20": sma20,
    }


def _ema_last(xs, n):
    k, e = 2 / (n + 1), xs[0]
    for v in xs[1:]:
        e = k * v + (1 - k) * e
    return e


def intraday_factors(candles: List[Dict[str, float]]) -> Optional[Dict[str, float]]:
    """1-hour-candle factors for short-term (0.5-1%) trading; None with < 60 bars."""
    if len(candles) < 60:
        return None
    closes = [c["close"] for c in candles]
    vols = [c["volume"] for c in candles]
    last = closes[-1]
    trs = [max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"]))
           for p, c in zip(candles[-15:-1], candles[-14:])]
    atr = sum(trs) / len(trs)
    ema20, ema50 = _ema_last(closes, 20), _ema_last(closes, 50)
    base_vol = sum(vols[-27:-3]) / 24 if sum(vols[-27:-3]) else 0.0
    return {"r4h": last / closes[-5] - 1, "r24h": last / closes[-25] - 1, "atr1h_pct": atr / last,
            "ema20_1h": ema20, "ema50_1h": ema50, "rsi1h": _rsi(closes[-60:]),
            "uptrend_1h": bool(last > ema20 > ema50),
            "vol_surge_1h": (sum(vols[-3:]) / 3) / base_vol if base_vol else 1.0}


RISK_OFF_MEDIAN_24H = float(os.environ.get("ZILLERS_RISK_OFF_MEDIAN", "-0.03"))  # median coin down >=3%/24h
# A 0.5% target cannot survive a wide spread; thin top-of-book means the fill slips past it.
MAX_SPREAD = float(os.environ.get("ZILLERS_MAX_SPREAD", "0.0015"))          # 0.15% of mid
MIN_TOP_DEPTH_USD = float(os.environ.get("ZILLERS_MIN_TOP_DEPTH_USD", "1000"))
MIN_ATR1H = 0.0025 # 0.25%/h: a 0.5-1% target is reachable within a few hours
MAX_ATR1H = 0.03     # above 3%/h, ordinary noise hits a 0.5-1% stop most of the time


def _z(values: List[float]) -> List[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    m = sum(values) / len(values)
    sd = math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1)) or 1.0
    return [(v - m) / sd for v in values]


class MarketScanner:
    def __init__(self, min_quote_volume: float = 10e6, max_24h_move: float = 0.25, shortlist: int = 250,
                 top_n: int = 10, ttl_seconds: float = 900.0,
                 tickers_fetcher: Callable[[], List[Dict[str, Any]]] = fetch_24h_tickers,
                 klines_fetcher: Callable[..., List[Dict[str, float]]] = fetch_klines,
                 testnet_symbols: Callable[[], set] = lambda: fetch_trading_usdt_symbols(TESTNET),
                 live_symbols: Optional[Callable[[], set]] = None, fallback: Optional[bool] = None,
                 book_fetcher: Optional[Callable[[], Dict[str, Dict[str, float]]]] = fetch_book_tickers):
        self.book_fetcher = book_fetcher
        self.min_quote_volume, self.max_24h_move = min_quote_volume, max_24h_move
        self.shortlist, self.top_n, self.ttl = shortlist, top_n, ttl_seconds
        self.tickers_fetcher, self.klines_fetcher = tickers_fetcher, klines_fetcher
        self.testnet_symbols = testnet_symbols
        self.live_symbols = live_symbols or (lambda: fetch_trading_usdt_symbols(ENDPOINTS[0]))
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()
        import os
        self.fallback = (os.environ.get("ZILLERS_SCANNER_FALLBACK", "1") != "0") if fallback is None else fallback

    def scan(self, mode: str = "PAPER", force: bool = False) -> Dict[str, Any]:
        mode = mode.upper()
        now = time.time()
        with self._lock:
            hit = self._cache.get(mode)
            if hit and not force and now - hit[0] < self.ttl:
                return hit[1]
        started = time.perf_counter()
        tickers = self.tickers_fetcher()
        tradable = self.live_symbols()
        testnet = None
        if mode == "TESTNET":
            try:
                testnet = self.testnet_symbols()
            except Exception:
                testnet = set()
        blocked = excluded_symbols()
        books, book_error = {}, None
        if self.book_fetcher is not None:
            try:
                books = self.book_fetcher()
            except Exception as exc:     # no book data: say so, keep scanning on volume alone
                book_error = type(exc).__name__
        rows, excluded = [], {"operator_excluded": 0, "stable_or_leveraged": 0, "illiquid": 0, "spike_24h": 0,
                              "not_on_testnet": 0, "wide_spread": 0, "thin_book": 0}
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT") or sym not in tradable:
                continue
            base = sym[:-4]
            row = {"symbol": sym, "base": base, "price": float(t["lastPrice"]),
                   "chg_24h": float(t["priceChangePercent"]) / 100, "quote_volume": float(t["quoteVolume"]),
                   "high_24h": float(t["highPrice"]), "low_24h": float(t["lowPrice"]), "trades_24h": int(t.get("count", 0))}
            reason = None
            if sym in blocked:
                reason = "operator_excluded"
            elif base in STABLE_BASES or base.endswith(LEVERAGED):
                reason = "stable_or_leveraged"
            elif row["quote_volume"] < self.min_quote_volume:
                reason = "illiquid"
            elif abs(row["chg_24h"]) > self.max_24h_move:
                reason = "spike_24h"
            elif testnet is not None and sym not in testnet:
                reason = "not_on_testnet"
            q = book_quality(books.get(sym)) if books else None
            if q:
                row["spread_pct"], row["top_depth_usd"] = round(q["spread_pct"], 6), round(q["top_depth_usd"], 2)
                if not reason and q["spread_pct"] > MAX_SPREAD:
                    reason = "wide_spread"
                elif not reason and q["top_depth_usd"] < MIN_TOP_DEPTH_USD:
                    reason = "thin_book"
            row["excluded"] = reason
            if reason:
                excluded[reason] += 1
            rows.append(row)

        survivors = sorted((r for r in rows if not r["excluded"]), key=lambda r: -r["quote_volume"])[: self.shortlist]

        def enrich(r):
            try:
                f = factors(self.klines_fetcher(r["symbol"], "1d", 90))
            except Exception as exc:
                f, r["error"] = None, type(exc).__name__
            r["factors"] = f
            return r

        with ThreadPoolExecutor(max_workers=8) as pool:
            survivors = list(pool.map(enrich, survivors))
        scored = [r for r in survivors if r.get("factors")]
        if scored:
            zm = _z([r["factors"]["momentum"] for r in scored])
            z7 = _z([r["factors"]["r7"] for r in scored])
            zv = _z([math.log(r["quote_volume"]) for r in scored])
            za = _z([r["factors"]["atr_pct"] for r in scored])
            for r, a, b, c, d in zip(scored, zm, z7, zv, za):
                f = r["factors"]
                r["score"] = round(0.45 * a + 0.25 * b + 0.20 * c - 0.10 * d, 4)
                why = []
                if not f["trend"]:
                    why.append("no uptrend")
                if f["rsi14"] is None or not 45 <= f["rsi14"] <= 78:
                    why.append("RSI outside 45-78")
                if f["drawdown"] < -0.25:
                    why.append("drawdown > 25%")
                if f["vol30"] < MIN_VOL30:
                    why.append("pegged / no volatility")
                r["eligible"], r["why_not"] = not why, why
        ranked = sorted(scored, key=lambda r: -r["score"])
        for r in ranked:
            r["tier"] = "TREND" if r["eligible"] else None
        top = [r["symbol"] for r in ranked if r["eligible"]][: self.top_n]
        # Market-regime filter: when most liquid coins are down hard, buying weak "potential" coins is
        # catching a falling market, so only coins passing the strict daily-trend test are allowed.
        chg = sorted(r["chg_24h"] for r in survivors)
        market_chg = chg[len(chg) // 2] if chg else 0.0
        risk_off = market_chg <= RISK_OFF_MEDIAN_24H
        if self.fallback and not risk_off and len(top) < self.top_n:
            top +=self._short_term_picks([r for r in ranked if not r["eligible"]], self.top_n - len(top))
        tiers = {t: [r["symbol"] for r in ranked if r.get("tier") == t] for t in ("TREND", "SHORT_TERM", "POTENTIAL")}
        result = {
            "tiers": tiers, "status": "OK", "mode": mode, "generated_at": now, "took_s": round(time.perf_counter() - started, 2),
            "top": top, "market": {"median_24h": round(market_chg, 4), "risk_off": risk_off}, "ranked": ranked, "all": sorted(rows, key=lambda r: -r["quote_volume"]),
            "counts": {"universe": len(rows), "survivors": len(survivors), "scored": len(scored), "excluded": excluded},
            "params": {"min_quote_volume": self.min_quote_volume, "max_24h_move": self.max_24h_move,
                       "shortlist": self.shortlist, "top_n": self.top_n, "fallback": self.fallback,
                       "excluded_symbols": sorted(blocked), "max_spread": MAX_SPREAD,
                       "min_top_depth_usd": MIN_TOP_DEPTH_USD, "book_error": book_error},
            "method": __doc__.split("Workflow", 1)[1].split("This chooses", 1)[0].strip(),
        }
        with self._lock:
            self._cache[mode] = (now, result)
        return result

    def _short_term_picks(self, rest: List[Dict[str, Any]], slots: int) -> List[str]:
        """Tiers b/c: when too few coins pass the daily trend filter, pick the best short-term movers."""
        def enrich(r):
            try:
                r["intraday"] = intraday_factors(self.klines_fetcher(r["symbol"], "1h", 72))
            except Exception:
                r["intraday"] = None
            return r

        with ThreadPoolExecutor(max_workers=8) as pool:
            rest = list(pool.map(enrich, rest))
        usable = []
        for r in rest:
            f = r.get("intraday")
            if not f:
                continue
            if f["atr1h_pct"] < MIN_ATR1H:
                r["why_not"] = r["why_not"] + ["moves < 0.25%/h"]
                continue
            if f["r24h"] <= -0.08 or f["r4h"] <= -0.03:
                r["why_not"] = r["why_not"] + ["falling fast (1h)"]
                continue
            if f["atr1h_pct"] > MAX_ATR1H:
                r["why_not"] = r["why_not"] + ["too volatile for 0.5-1% targets"]
                continue
            usable.append(r)
        picks: List[str] = []
        ranked = _short_term_rank(usable) if usable else []
        for tier, ok in (("SHORT_TERM", lambda f: f["uptrend_1h"] and f["rsi1h"] is not None and 40 <= f["rsi1h"] <= 72),
                         ("POTENTIAL", lambda f: True)):
            for r in ranked:
                if len(picks) >= slots:
                    return picks
                if r["symbol"] not in picks and r.get("tier") is None and ok(r["intraday"]):
                    r["tier"] = tier
                    picks.append(r["symbol"])
        return picks


def _short_term_rank(cands):
    zr = _z([c["intraday"]["r4h"] / c["intraday"]["atr1h_pct"] for c in cands])
    z24 = _z([c["intraday"]["r24h"] for c in cands])
    zv = _z([math.log(c["quote_volume"]) for c in cands])
    zs = _z([c["intraday"]["vol_surge_1h"] for c in cands])
    for c, a, b, d, e in zip(cands, zr, z24, zv, zs):
        c["short_score"] = round(0.35 * a + 0.25 * b + 0.25 * d + 0.15 * e, 4)
    return sorted(cands, key=lambda c: -c["short_score"])


class Autopilot:
    """Scan -> trade the top N -> rescan every `period` and rotate only when the fleet is flat."""

    def __init__(self, scanner: MarketScanner, fleet, positions_open: Callable[[], int], notify=None,
                 period_seconds: float = 4 * 3600, tier_log: Optional[Path] = None):
        self.scanner, self.fleet, self.positions_open = scanner, fleet, positions_open
        self.tier_log = Path(tier_log) if tier_log else None
        self.notify, self.period = notify, period_seconds
        self.enabled = False
        self.mode = "PAPER"
        self.last: Dict[str, Any] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self, mode: str, actor: str) -> Dict[str, Any]:
        self.mode, self.enabled = mode.upper(), True
        result = self._cycle(actor, first=True)
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, args=(actor,), daemon=True, name="autopilot")
            self._thread.start()
        return result

    def stop(self) -> None:
        self.enabled = False
        self._stop.set()

    def _loop(self, actor):
        while not self._stop.wait(self.period):
            if self.enabled:
                try:
                    self._cycle(actor)
                except Exception as exc:
                    self.last = {**self.last, "error": type(exc).__name__, "at": time.time()}

    def _cycle(self, actor: str, first: bool = False) -> Dict[str, Any]:
        scan = self.scanner.scan(self.mode, force=True)
        top = scan["top"]
        status = self.fleet.status()
        current = status.get("symbols") if status.get("running") else None
        action = "kept"
        if not top:
            action = "no eligible symbols"
        elif current is None:
            self.fleet.start(self.mode, top, actor)
            action = "started"
        elif sorted(current) != sorted(top):
            if self.positions_open() == 0:
                self.fleet.stop(reason="autopilot rotation to new top performers")
                self.fleet.start(self.mode, top, actor)
                action = "rotated"
            else:
                action = "rotation deferred (open positions)"
        self.last = {"at": time.time(), "top": top, "action": action, "previous": current}
        if action in {"started", "rotated"}:
            self._log_tiers(scan, top)
        if self.notify and action in {"started", "rotated"}:
            self.notify(f"🧭 <b>Autopilot {action}</b>\nMode: {self.mode}\nTrading top {len(top)}: {', '.join(top)}")
        return {"scan": scan, "autopilot": self.status()}

    def _log_tiers(self, scan: Dict[str, Any], top: List[str]) -> None:
        """Append which tier each traded coin came from, so P&L can be split by tier later."""
        if self.tier_log is None:
            return
        tier_of = {s: t for t, syms in (scan.get("tiers") or {}).items() for s in syms}
        line = {"at": time.time(), "mode": self.mode, "tiers": {s: tier_of.get(s, "UNKNOWN") for s in top}}
        try:
            self.tier_log.parent.mkdir(parents=True, exist_ok=True)
            with self.tier_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line) + "\n")
        except OSError:
            pass   # bookkeeping only: never block trading on it

    def status(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, "mode": self.mode, "period_hours": self.period / 3600, "last": self.last}
