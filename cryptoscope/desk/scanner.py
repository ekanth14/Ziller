"""Market scanner: rank every Binance spot USDT pair and pick the top performers to trade.

Workflow
1. Universe   - every TRADING spot pair quoted in USDT (one /api/v3/ticker/24hr call).
2. Filters    - drop stablecoins/fiat and leveraged tokens; require 24h quote volume >= min_quote_volume;
                drop pairs that moved more than max_24h_move in 24h (pump/dump risk); TESTNET mode keeps
                only pairs that exist on the Binance Spot testnet.
3. Shortlist  - the `shortlist` most liquid survivors get 90 daily candles each.
4. Factors    - r7, r30 (returns), vol30 (annualised volatility of daily log returns),
                risk-adjusted momentum  M = (0.4*r7 + 0.6*r30) / vol30,
                trend  = close > SMA20 and SMA10 > SMA30,
                RSI14 (Wilder), ATR14% (ATR / close),
                drawdown from the 90-day high.
5. Eligibility- trend true, 45 <= RSI14 <= 78 (momentum but not blow-off), drawdown >= -25%,
                vol30 >= 10% (filters pegged/stable assets the name list misses).
6. Score      - z-scored blend across the shortlist:
                score = 0.45*z(M) + 0.25*z(r7) + 0.20*z(log quote volume) - 0.10*z(ATR14%)
7. Pick       - top `top_n` eligible by score.

This chooses WHAT the fleet watches. Each entry still has to pass the fleet's own pipeline:
signal -> strategy -> debate -> RiskBot (sizing, correlation, drawdown, daily loss) -> execution.
Nothing here places orders.
"""
from __future__ import annotations

import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional
from urllib.request import Request, urlopen

from cryptoscope.desk.feed import ENDPOINTS, fetch_klines

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


def _z(values: List[float]) -> List[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    m = sum(values) / len(values)
    sd = math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1)) or 1.0
    return [(v - m) / sd for v in values]


class MarketScanner:
    def __init__(self, min_quote_volume: float = 10e6, max_24h_move: float = 0.25, shortlist: int = 60,
                 top_n: int = 5, ttl_seconds: float = 900.0,
                 tickers_fetcher: Callable[[], List[Dict[str, Any]]] = fetch_24h_tickers,
                 klines_fetcher: Callable[..., List[Dict[str, float]]] = fetch_klines,
                 testnet_symbols: Callable[[], set] = lambda: fetch_trading_usdt_symbols(TESTNET),
                 live_symbols: Optional[Callable[[], set]] = None):
        self.min_quote_volume, self.max_24h_move = min_quote_volume, max_24h_move
        self.shortlist, self.top_n, self.ttl = shortlist, top_n, ttl_seconds
        self.tickers_fetcher, self.klines_fetcher = tickers_fetcher, klines_fetcher
        self.testnet_symbols = testnet_symbols
        self.live_symbols = live_symbols or (lambda: fetch_trading_usdt_symbols(ENDPOINTS[0]))
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()

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
        rows, excluded = [], {"stable_or_leveraged": 0, "illiquid": 0, "spike_24h": 0, "not_on_testnet": 0}
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT") or sym not in tradable:
                continue
            base = sym[:-4]
            row = {"symbol": sym, "base": base, "price": float(t["lastPrice"]),
                   "chg_24h": float(t["priceChangePercent"]) / 100, "quote_volume": float(t["quoteVolume"]),
                   "high_24h": float(t["highPrice"]), "low_24h": float(t["lowPrice"]), "trades_24h": int(t.get("count", 0))}
            reason = None
            if base in STABLE_BASES or base.endswith(LEVERAGED):
                reason = "stable_or_leveraged"
            elif row["quote_volume"] < self.min_quote_volume:
                reason = "illiquid"
            elif abs(row["chg_24h"]) > self.max_24h_move:
                reason = "spike_24h"
            elif testnet is not None and sym not in testnet:
                reason = "not_on_testnet"
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
        top = [r["symbol"] for r in ranked if r["eligible"]][: self.top_n]
        result = {
            "status": "OK", "mode": mode, "generated_at": now, "took_s": round(time.perf_counter() - started, 2),
            "top": top, "ranked": ranked, "all": sorted(rows, key=lambda r: -r["quote_volume"]),
            "counts": {"universe": len(rows), "survivors": len(survivors), "scored": len(scored), "excluded": excluded},
            "params": {"min_quote_volume": self.min_quote_volume, "max_24h_move": self.max_24h_move,
                       "shortlist": self.shortlist, "top_n": self.top_n},
            "method": __doc__.split("Workflow", 1)[1].split("This chooses", 1)[0].strip(),
        }
        with self._lock:
            self._cache[mode] = (now, result)
        return result


class Autopilot:
    """Scan -> trade the top N -> rescan every `period` and rotate only when the fleet is flat."""

    def __init__(self, scanner: MarketScanner, fleet, positions_open: Callable[[], int], notify=None,
                 period_seconds: float = 4 * 3600):
        self.scanner, self.fleet, self.positions_open = scanner, fleet, positions_open
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
        if self.notify and action in {"started", "rotated"}:
            self.notify(f"🧭 <b>Autopilot {action}</b>\nMode: {self.mode}\nTrading top {len(top)}: {', '.join(top)}")
        return {"scan": scan, "autopilot": self.status()}

    def status(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, "mode": self.mode, "period_hours": self.period / 3600, "last": self.last}
