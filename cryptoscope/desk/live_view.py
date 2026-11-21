"""Live Tradebot view: what the fleet is trading right now, per coin, from real data only.

Sources (read-only):
- FleetManager.status()              which coins the running fleet trades (PAPER / TESTNET)
- orchestrator_execution.db          open positions (stop / target / opened at)
- trading_journal.db                 fills, closed trades, last signal / debate / meta-label / risk decision
- Binance public REST                last price for all traded coins in ONE request (cached 1 s), 24h stats (cached 30 s)

Position size and entry come from the journal's BUY fills since the coin's last close (volume-weighted),
not from the execution row alone: before the one-position-per-coin fix, extra buys overwrote that row.
Nothing here is simulated or invented; a coin with no data shows "—".
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ENDPOINTS = ("https://api.binance.com", "https://data-api.binance.vision")
EXIT_FEE = 0.001   # estimated taker fee on the exit (paper engine books 0.1% per side)


def _get(path: str, timeout: float = 6.0):
    last = None
    for base in ENDPOINTS:
        try:
            req = urllib.request.Request(base + path, headers={"User-Agent": "ZILLERS-Live/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https hosts
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            last = exc
    raise RuntimeError(f"Binance unavailable: {type(last).__name__}")


class PriceCache:
    """Last price for many symbols in one call (1 s TTL) and 24h change (30 s TTL), shared by all viewers."""

    def __init__(self, fetch: Optional[Callable[[str], Any]] = None, ttl: float = 1.0, ttl_24h: float = 30.0):
        self.fetch, self.ttl, self.ttl_24h = fetch or _get, ttl, ttl_24h
        self._lock = threading.Lock()
        self._prices: Dict[str, float] = {}
        self._at = 0.0
        self._key: tuple = ()
        self._day: Dict[str, Dict[str, float]] = {}
        self._day_at = 0.0
        self.error: Optional[str] = None

    def _q(self, symbols) -> str:
        return urllib.parse.quote(json.dumps(sorted(symbols), separators=(",", ":")))

    def prices(self, symbols: List[str]) -> Dict[str, float]:
        key = tuple(sorted(set(symbols)))
        if not key:
            return {}
        with self._lock:
            if key == self._key and time.time() - self._at < self.ttl:
                return dict(self._prices)
            try:
                rows = self.fetch(f"/api/v3/ticker/price?symbols={self._q(key)}")
                self._prices = {r["symbol"]: float(r["price"]) for r in rows}
                self._at, self._key, self.error = time.time(), key, None
            except Exception as exc:
                self.error = type(exc).__name__
            return dict(self._prices)

    def day_stats(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        key = sorted(set(symbols))
        if not key:
            return {}
        with self._lock:
            if time.time() - self._day_at < self.ttl_24h and set(key) <= set(self._day):
                return dict(self._day)
            try:
                rows = self.fetch(f"/api/v3/ticker/24hr?type=MINI&symbols={self._q(key)}")
                self._day = {r["symbol"]: {"open": float(r["openPrice"]), "high": float(r["highPrice"]),
                                           "low": float(r["lowPrice"]), "quote_volume": float(r["quoteVolume"])}
                             for r in rows}
                self._day_at = time.time()
            except Exception:
                pass
            return dict(self._day)


def _ro(path: Path) -> Optional[sqlite3.Connection]:
    if not Path(path).is_file():
        return None
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn, sql, args=()) -> List[Dict[str, Any]]:
    if conn is None:
        return []
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    except sqlite3.Error:
        return []


def _one(conn, sql, args=()) -> Optional[Dict[str, Any]]:
    r = _rows(conn, sql, args)
    return r[0] if r else None


def coin_book(runtime_dir: Path, symbol: str, fills_limit: int = 40) -> Dict[str, Any]:
    """Everything the journal knows about one coin: open position, fills, closed trades, last decisions."""
    runtime_dir = Path(runtime_dir)
    with closing(_ro(runtime_dir / "orchestrator_execution.db") or sqlite3.connect(":memory:")) as ex, \
            closing(_ro(runtime_dir / "trading_journal.db") or sqlite3.connect(":memory:")) as jr:
        ex.row_factory = jr.row_factory = sqlite3.Row
        pos = _one(ex, "SELECT * FROM positions WHERE symbol=?", (symbol,))
        closed = _rows(jr, "SELECT * FROM positions_closed WHERE symbol=? ORDER BY timestamp DESC", (symbol,))
        last_close = max([float(c["timestamp"]) for c in closed] +
                         [float((_one(jr, "SELECT max(timestamp) t FROM fills WHERE symbol=? AND upper(side)='SELL'",
                                      (symbol,)) or {}).get("t") or 0.0)])
        fills = _rows(jr, "SELECT timestamp, side, fill_price, quantity, fee_usd, slippage_pct FROM fills "
                          "WHERE symbol=? ORDER BY timestamp DESC LIMIT ?", (symbol, fills_limit))
        open_buys = _rows(jr, "SELECT timestamp, fill_price, quantity, fee_usd FROM fills WHERE symbol=? AND upper(side)='BUY' "
                              "AND timestamp>? ORDER BY timestamp", (symbol, last_close))
        signal = _one(jr, "SELECT timestamp, direction, confidence, strategy_id, reasons FROM signals WHERE symbol=? "
                          "ORDER BY timestamp DESC LIMIT 1", (symbol,))
        debate = _one(jr, "SELECT timestamp, verdict, conviction_score, risk_summary FROM debates WHERE symbol=? "
                          "ORDER BY timestamp DESC LIMIT 1", (symbol,))
        meta = _one(jr, "SELECT timestamp, thx02_p, laya_p, mean_p, quality, enforced, vetoed FROM meta_labels "
                        "WHERE symbol=? ORDER BY timestamp DESC LIMIT 1", (symbol,))
        risk = _one(jr, "SELECT timestamp, decision, veto_reasons, position_size_usd FROM risk_decisions WHERE symbol=? "
                        "ORDER BY timestamp DESC LIMIT 1", (symbol,))
        counts = _one(jr, "SELECT (SELECT count(*) FROM signals WHERE symbol=?) signals, "
                          "(SELECT count(*) FROM debates WHERE symbol=?) debates, "
                          "(SELECT count(*) FROM risk_decisions WHERE symbol=? AND decision='APPROVED') approved",
                      (symbol, symbol, symbol)) or {}
    position = None
    if pos:
        qty = sum(float(b["quantity"]) for b in open_buys)
        if qty <= 0:                      # journal missing (older run): fall back to the execution row
            qty, entry, fees = float(pos["quantity"]), float(pos["entry_price"]), 0.0
        else:
            entry = sum(float(b["quantity"]) * float(b["fill_price"]) for b in open_buys) / qty
            fees = sum(float(b["fee_usd"] or 0) for b in open_buys)
        position = {"side": pos["side"], "quantity": qty, "entry": entry, "stop": pos["stop_price"],
                    "target": pos["target_price"],
                    "opened_at": float(open_buys[0]["timestamp"]) if open_buys else pos["created_at"], "mode": pos["mode"],
                    "entry_fees": fees, "fills": len(open_buys) or 1}
    wins = [c for c in closed if float(c["pnl_usd"]) > 0]
    return {
        "symbol": symbol, "position": position,
        "realized": sum(float(c["pnl_usd"]) for c in closed), "closed_trades": len(closed), "wins": len(wins),
        "fees_total": sum(float(f["fee_usd"] or 0) for f in fills),
        "closed": closed[:20], "fills": fills,
        "last": {"signal": signal, "debate": debate, "meta": meta, "risk": risk},
        "counts": counts,
    }


def _status(book: Dict[str, Any]) -> str:
    if book["position"]:
        return "IN POSITION"
    risk = (book["last"] or {}).get("risk") or {}
    if risk.get("decision") == "VETOED" and risk.get("veto_reasons"):
        return "BLOCKED: " + str(risk["veto_reasons"]).split(";")[0].split(":")[0][:40]
    return "WATCHING"


def build_live(runtime_dir: Path, fleet_status: Dict[str, Any], prices: PriceCache, now: Optional[float] = None,
               with_detail: Optional[str] = None) -> Dict[str, Any]:
    """Overview of every coin the fleet trades (plus any coin still held), with live marks and P&L."""
    now = time.time() if now is None else now
    runtime_dir = Path(runtime_dir)
    running = bool(fleet_status.get("running"))
    symbols = list(fleet_status.get("symbols") or []) if running else []
    with closing(_ro(runtime_dir / "orchestrator_execution.db") or sqlite3.connect(":memory:")) as ex:
        held = [r["symbol"] for r in _rows(ex, "SELECT symbol FROM positions")]
    for s in held:
        if s not in symbols:
            symbols.append(s)
    marks = prices.prices(symbols)
    day = prices.day_stats(symbols)
    coins, tot = [], {"invested": 0.0, "value": 0.0, "upnl": 0.0, "realized": 0.0, "fees": 0.0}
    for sym in symbols:
        book = coin_book(runtime_dir, sym)
        px = marks.get(sym)
        p = book["position"]
        row = {"symbol": sym, "price": px, "status": _status(book), "traded_by_fleet": sym in (fleet_status.get("symbols") or []),
               "change_24h": (px / day[sym]["open"] - 1) if px and sym in day and day[sym]["open"] else None,
               "realized": book["realized"], "closed_trades": book["closed_trades"], "wins": book["wins"],
               "last": book["last"], "counts": book["counts"]}
        if p:
            cost = p["quantity"] * p["entry"]
            value = p["quantity"] * px if px else None
            gross = (px - p["entry"]) * p["quantity"] if px else None
            net = gross - p["entry_fees"] - (value or 0) * EXIT_FEE if gross is not None else None
            row.update(position=p, invested=cost + p["entry_fees"], value=value, upnl_gross=gross, upnl=net,
                       upnl_pct=net / (cost + p["entry_fees"]) if net is not None and cost else None,
                       to_stop=(p["stop"] / px - 1) if px and p["stop"] else None,
                       to_target=(p["target"] / px - 1) if px and p["target"] else None,
                       held_s=now - float(p["opened_at"] or now))
            tot["invested"] += cost + p["entry_fees"]
            tot["value"] += value or 0
            tot["upnl"] += net or 0
        tot["realized"] += book["realized"]
        tot["fees"] += book["fees_total"]
        if with_detail == sym:
            row["detail"] = {"fills": book["fills"], "closed": book["closed"]}
        coins.append(row)
    coins.sort(key=lambda r: (r.get("position") is None, -(r.get("invested") or 0), r["symbol"]))
    return {"status": "OK", "generated_at": now, "running": running, "mode": fleet_status.get("mode"),
            "started_at": fleet_status.get("started_at"), "symbols": symbols, "coins": coins,
            "totals": {**tot, "net": tot["upnl"] + tot["realized"], "in_position": sum(1 for c in coins if c.get("position")),
                       "coins": len(coins)},
            "price_error": prices.error}
