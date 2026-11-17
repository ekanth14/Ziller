"""AI decision journal (idea from TradingAgents' decision memory / QuantDinger signal-only accounts).

Every desk refresh records what each AI system said on the last closed bar (one row per system,
symbol, interval and bar). Later refreshes score those rows against what price actually did
`horizon` bars after the decision bar, using the same exchange candles the desk already fetched.

Scoring (spot, long-only view):
- BUY  -> correct if forward return > +threshold; edge = forward return
- SELL -> correct if forward return < -threshold; edge = -forward return (cash avoided the drop)
- HOLD -> correct if |forward return| <= threshold; edge = 0 (no position)
Threshold defaults to 0.25 x the bar's ATR as a fraction of price, so noise is not counted.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = """CREATE TABLE IF NOT EXISTS ai_decisions (
    system TEXT NOT NULL, symbol TEXT NOT NULL, interval TEXT NOT NULL, bar_time REAL NOT NULL,
    action TEXT NOT NULL, confidence REAL, price REAL NOT NULL, threshold REAL NOT NULL,
    recorded_at REAL NOT NULL, fwd_return REAL, correct INTEGER, edge REAL, scored_at REAL,
    PRIMARY KEY (system, symbol, interval, bar_time))"""


class AIJournal:
    def __init__(self, path: str, horizon: int = 5):
        self.path = Path(path)
        self.horizon = horizon
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(SCHEMA)
            db.commit()

    def _db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def record(self, symbol: str, interval: str, bar_time: float, price: float, threshold: float,
               decisions: Iterable[Dict[str, Any]]) -> int:
        """decisions: [{system, action, confidence?}] for the closed bar. Idempotent per bar."""
        rows = [(d["system"], symbol, interval, float(bar_time), d["action"], d.get("confidence"), float(price),
                 float(threshold), time.time()) for d in decisions if d.get("action") in {"BUY", "SELL", "HOLD"}]
        if not rows:
            return 0
        with self._lock, closing(self._db()) as db:
            cur = db.executemany("INSERT OR IGNORE INTO ai_decisions (system,symbol,interval,bar_time,action,confidence,"
                                 "price,threshold,recorded_at) VALUES (?,?,?,?,?,?,?,?,?)", rows)
            db.commit()
            return cur.rowcount

    def score(self, symbol: str, interval: str, candles: List[Dict[str, float]], last_closed_index: int) -> int:
        """Score unscored rows whose horizon bar is now closed in `candles` (oldest first)."""
        idx = {round(c["open_time"]): i for i, c in enumerate(candles)}
        scored = 0
        with self._lock, closing(self._db()) as db:
            pending = db.execute("SELECT rowid, * FROM ai_decisions WHERE symbol=? AND interval=? AND scored_at IS NULL",
                                 (symbol, interval)).fetchall()
            for r in pending:
                i = idx.get(round(r["bar_time"]))
                if i is None or i + self.horizon > last_closed_index:
                    continue
                fwd = candles[i + self.horizon]["close"] / r["price"] - 1
                th = r["threshold"]
                if r["action"] == "BUY":
                    correct, edge = fwd > th, fwd
                elif r["action"] == "SELL":
                    correct, edge = fwd < -th, -fwd
                else:
                    correct, edge = abs(fwd) <= th, 0.0
                db.execute("UPDATE ai_decisions SET fwd_return=?, correct=?, edge=?, scored_at=? WHERE rowid=?",
                           (fwd, int(correct), edge, time.time(), r["rowid"]))
                scored += 1
            db.commit()
        return scored

    def scoreboard(self, symbol: Optional[str] = None, interval: Optional[str] = None) -> Dict[str, Any]:
        where, args = [], []
        if symbol:
            where.append("symbol=?"); args.append(symbol)
        if interval:
            where.append("interval=?"); args.append(interval)
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        with closing(self._db()) as db:
            rows = db.execute(
                "SELECT system, count(*) n, sum(scored_at IS NOT NULL) scored, avg(correct) hit, avg(edge) edge, "
                "sum(action='BUY') buys, sum(action='SELL') sells, sum(action='HOLD') holds, max(bar_time) last_bar "
                f"FROM ai_decisions{cond} GROUP BY system ORDER BY avg(correct) DESC", args).fetchall()
            recent = db.execute(f"SELECT system, symbol, interval, bar_time, action, price, fwd_return, correct FROM ai_decisions{cond} "
                                "ORDER BY bar_time DESC, system LIMIT 40", args).fetchall()
        return {"horizon_bars": self.horizon,
                "systems": [dict(r) for r in rows],
                "recent": [dict(r) for r in recent]}
