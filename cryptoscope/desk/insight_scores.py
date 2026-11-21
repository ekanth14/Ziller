"""Signal-source accuracy ("insight scoring", after QuantConnect LEAN's Insight scores; ideas, not code).

For every signal the fleet journalled, did the price move the predicted way over the trade horizon?
- One signal per (source, coin, 15 m bar, direction): the analyst/quant bots re-emit the same signal on
  every 15 s poll, so raw rows would overweight long-lived signals.
- Forward return = close `horizon` bars after the signal bar / close of the signal bar - 1 (Binance 15 m klines).
- Direction score = share of BUY signals followed by a rise (SELL: by a fall).
- Base rate = share of ALL 15 m bars of the same coins followed by a rise over the same horizon, so a source
  that only "wins" because the market went up gets no credit. Edge = direction score - base rate.
Signals newer than `horizon` bars (outcome not known yet) or older than the fetched history are skipped.
"""
from __future__ import annotations

import sqlite3
import time
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

BAR = 900


def _klines(symbol: str) -> List[Dict[str, float]]:
    from cryptoscope.desk.feed import fetch_klines
    return fetch_klines(symbol, "15m", 1000)


def score_signals(runtime_dir: Path, horizon: int = 16, klines: Optional[Callable[[str], list]] = None,
                  now: Optional[float] = None) -> Dict[str, Any]:
    klines = klines or _klines
    now = time.time() if now is None else now
    db = Path(runtime_dir) / "trading_journal.db"
    if not db.is_file():
        return {"status": "OK", "sources": [], "note": "no journal yet"}
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as c:
        rows = c.execute("SELECT timestamp, symbol, direction, strategy_id FROM signals "
                         "WHERE direction IN ('BUY','SELL')").fetchall()
    uniq = {}
    for ts, sym, d, src in rows:
        uniq.setdefault((src or "core", sym, int(ts // BAR), d), ts)
    by_sym = defaultdict(list)
    for (src, sym, bar, d) in uniq:
        by_sym[sym].append((src, bar, d))
    stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"n": 0, "hits": 0, "fwd": [], "base_up": 0, "base_n": 0,
                                                            "coins": set()})
    base_cache = {}
    skipped = 0
    for sym, sigs in by_sym.items():
        try:
            bars = klines(sym)
        except Exception:
            skipped += len(sigs)
            continue
        idx = {int(b["open_time"] // BAR): i for i, b in enumerate(bars)}
        closes = [b["close"] for b in bars]
        ups = [closes[i + horizon] > closes[i] for i in range(len(closes) - horizon)]
        base_cache[sym] = (sum(ups), len(ups))
        for src, bar, d in sigs:
            i = idx.get(bar)
            if i is None or i + horizon >= len(closes) or (bar + horizon + 1) * BAR > now:
                skipped += 1
                continue
            fwd = closes[i + horizon] / closes[i] - 1
            st = stats[src]
            st["n"] += 1
            st["hits"] += (fwd > 0) if d == "BUY" else (fwd < 0)
            st["fwd"].append(fwd if d == "BUY" else -fwd)
            if sym not in st["coins"]:
                st["coins"].add(sym)
                st["base_up"] += base_cache[sym][0]
                st["base_n"] += base_cache[sym][1]
    out = []
    for src, st in stats.items():
        if not st["n"]:
            continue
        score = st["hits"] / st["n"]
        base = st["base_up"] / st["base_n"] if st["base_n"] else None
        out.append({"source": src, "signals": st["n"], "direction_score": score, "base_rate": base,
                    "edge": (score - base) if base is not None else None,
                    "avg_fwd_return": sum(st["fwd"]) / st["n"], "coins": len(st["coins"])})
    out.sort(key=lambda r: -(r["edge"] if r["edge"] is not None else -1))
    return {"status": "OK", "horizon_bars": horizon, "horizon_hours": horizon * BAR / 3600, "sources": out,
            "skipped": skipped, "generated_at": now}
