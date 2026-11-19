"""P&L dashboard data: one read-only view over everything that can make or lose money.

Sources (all opened read-only; a missing database simply contributes nothing):
- work/runtime/trading_journal.db      fleet pipeline: signals, intents, debates, risk decisions,
                                        orders, fills, closed positions (realised P&L)
- work/runtime/orchestrator_execution.db fleet open positions (marked to the live price -> unrealised)
- PaperBotManager.list()               grid / DCA paper bots (equity vs investment)

Formulas
- Realised P&L       = sum(pnl_usd) of closed fleet positions (net of the fees the execution layer booked)
- Unrealised P&L     = (mark - entry) x qty for each open long
- Win rate           = winners / closed trades
- Profit factor      = gross wins / |gross losses|
- Expectancy         = mean pnl_usd per closed trade
- Equity curve       = starting NAV + cumulative realised P&L (in close order)
- Max drawdown       = min over the curve of equity / running peak - 1
"""
from __future__ import annotations

import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DAY = 86400


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


def _scalar(conn, sql, default=0):
    if conn is None:
        return default
    try:
        v = conn.execute(sql).fetchone()[0]
        return default if v is None else v
    except sqlite3.Error:
        return default


def trade_stats(closed: List[Dict[str, Any]], start_nav: float) -> Dict[str, Any]:
    pnls = [float(t["pnl_usd"]) for t in closed]
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p <= 0]
    gross_win, gross_loss = sum(wins), sum(losses)
    equity, peak, max_dd, curve = start_nav, start_nav, 0.0, []
    for t in sorted(closed, key=lambda r: r["timestamp"]):
        equity += float(t["pnl_usd"])
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1 if peak else 0.0)
        curve.append({"time": int(t["timestamp"]), "equity": round(equity, 4)})
    streak, kind = 0, None
    for p in reversed([float(t["pnl_usd"]) for t in sorted(closed, key=lambda r: r["timestamp"])]):
        k = "win" if p > 0 else "loss"
        if kind in (None, k):
            kind, streak = k, streak + 1
        else:
            break
    return {
        "trades": len(pnls), "wins": len(wins), "losses": len(losses),
        "realized": gross_win + gross_loss, "gross_win": gross_win, "gross_loss": gross_loss,
        "win_rate": len(wins) / len(pnls) if pnls else None,
        "profit_factor": gross_win / -gross_loss if gross_loss < 0 else None,
        "expectancy": sum(pnls) / len(pnls) if pnls else None,
        "avg_win": gross_win / len(wins) if wins else None,
        "avg_loss": gross_loss / len(losses) if losses else None,
        "best": max(pnls) if pnls else None, "worst": min(pnls) if pnls else None,
        "avg_hold_s": sum(float(t["duration_seconds"]) for t in closed) / len(closed) if closed else None,
        "max_drawdown": max_dd, "curve": curve,
        "streak": {"kind": kind, "count": streak} if kind else None,
    }


def build_pnl(runtime_dir: Path, paper_bots: Optional[List[Dict[str, Any]]] = None,
              price: Optional[Callable[[str], float]] = None, start_nav: float = 10_000.0,
              now: Optional[float] = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    runtime_dir = Path(runtime_dir)
    paper_bots = paper_bots or []

    with closing(_ro(runtime_dir / "trading_journal.db") or sqlite3.connect(":memory:")) as jr:
        jr.row_factory = sqlite3.Row
        closed = _rows(jr, "SELECT * FROM positions_closed ORDER BY timestamp")
        fees = float(_scalar(jr, "SELECT sum(fee_usd) FROM fills", 0.0))
        recent_fills = _rows(jr, "SELECT timestamp, symbol, side, fill_price, quantity, fee_usd, slippage_pct "
                                 "FROM fills ORDER BY timestamp DESC LIMIT 25")
        funnel = {
            "signals": _scalar(jr, "SELECT count(*) FROM signals"),
            "intents": _scalar(jr, "SELECT count(*) FROM trade_intents"),
            "debates": _scalar(jr, "SELECT count(*) FROM debates"),
            "debate_approved": _scalar(jr, "SELECT count(*) FROM debates WHERE upper(verdict) IN ('APPROVE','APPROVED')"),
            "risk_approved": _scalar(jr, "SELECT count(*) FROM risk_decisions WHERE decision='APPROVED'"),
            "risk_vetoed": _scalar(jr, "SELECT count(*) FROM risk_decisions WHERE decision='VETOED'"),
            "orders": _scalar(jr, "SELECT count(*) FROM orders"),
            "fills": _scalar(jr, "SELECT count(*) FROM fills"),
            "closed": len(closed),
        }
        vetoes: Counter = Counter()
        for r in _rows(jr, "SELECT veto_reasons FROM risk_decisions WHERE decision='VETOED' ORDER BY timestamp DESC LIMIT 500"):
            for reason in str(r["veto_reasons"] or "").split("; "):
                if not reason:
                    continue
                vetoes[str(reason).split(":", 1)[0].split(" (", 1)[0][:60]] += 1
        last_signal = _scalar(jr, "SELECT max(timestamp) FROM signals", None)

    with closing(_ro(runtime_dir / "orchestrator_execution.db") or sqlite3.connect(":memory:")) as ex:
        ex.row_factory = sqlite3.Row
        open_rows = _rows(ex, "SELECT symbol, side, quantity, entry_price, stop_price, target_price, created_at, mode FROM positions")

    open_positions, unrealized = [], 0.0
    for p in open_rows:
        mark = None
        if price:
            try:
                mark = float(price(p["symbol"]))
            except Exception:
                mark = None
        qty, entry = float(p["quantity"]), float(p["entry_price"])
        upnl = (mark - entry) * qty if mark is not None else None
        unrealized += upnl or 0.0
        open_positions.append({**p, "mark": mark, "value": mark * qty if mark is not None else None,
                               "upnl": upnl, "upnl_pct": mark / entry - 1 if mark is not None and entry else None,
                               "to_stop_pct": p["stop_price"] / mark - 1 if mark and p.get("stop_price") else None,
                               "to_target_pct": p["target_price"] / mark - 1 if mark and p.get("target_price") else None})

    stats = trade_stats(closed, start_nav)
    periods = {}
    for name, secs in (("today", None), ("7d", 7 * DAY), ("30d", 30 * DAY)):
        cut = now - (now % DAY) if secs is None else now - secs
        sel = [t for t in closed if t["timestamp"] >= cut]
        periods[name] = {"pnl": sum(float(t["pnl_usd"]) for t in sel), "trades": len(sel)}
    periods["all"] = {"pnl": stats["realized"], "trades": stats["trades"]}

    by_symbol: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    by_reason: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"pnl": 0.0, "trades": 0})
    daily: Dict[int, float] = defaultdict(float)
    for t in closed:
        s = by_symbol[t["symbol"]]
        s["pnl"] += float(t["pnl_usd"]); s["trades"] += 1; s["wins"] += float(t["pnl_usd"]) > 0
        r = by_reason[t["exit_reason"]]
        r["pnl"] += float(t["pnl_usd"]); r["trades"] += 1
        daily[int(t["timestamp"] // DAY * DAY)] += float(t["pnl_usd"])

    bots_pnl = sum(float(b.get("pnl") or 0) for b in paper_bots)
    bots_invested = sum(float((b.get("config") or {}).get("investment") or 0) for b in paper_bots)
    fleet_equity = start_nav + stats["realized"] + unrealized
    return {
        "status": "OK", "generated_at": now, "start_nav": start_nav,
        "totals": {
            "net": stats["realized"] + unrealized + bots_pnl,
            "fleet_realized": stats["realized"], "fleet_unrealized": unrealized, "paper_bots": bots_pnl,
            "fees": fees, "fleet_equity": fleet_equity, "fleet_return": fleet_equity / start_nav - 1,
            "exposure": sum(p["value"] or 0 for p in open_positions),
            "bots_invested": bots_invested, "bots_return": bots_pnl / bots_invested if bots_invested else None,
        },
        "periods": periods,
        "stats": {k: v for k, v in stats.items() if k != "curve"},
        "equity_curve": stats["curve"],
        "daily": [{"time": d, "pnl": round(v, 4)} for d, v in sorted(daily.items())],
        "by_symbol": sorted(({"symbol": k, **v} for k, v in by_symbol.items()), key=lambda r: r["pnl"]),
        "by_exit_reason": sorted(({"reason": k, **v} for k, v in by_reason.items()), key=lambda r: r["pnl"]),
        "open_positions": open_positions,
        "recent_trades": [dict(t) for t in closed[-25:]][::-1],
        "recent_fills": recent_fills,
        "paper_bots": [{k: b.get(k) for k in ("id", "kind", "symbol", "status", "equity", "pnl", "pnl_pct",
                                                "realized", "fees", "fills", "hold_pnl_pct")}
                       | {"investment": (b.get("config") or {}).get("investment")} for b in paper_bots],
        "funnel": funnel,
        "top_vetoes": [{"reason": k, "count": v} for k, v in vetoes.most_common(8)],
        "last_signal_at": last_signal,
    }
