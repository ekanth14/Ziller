"""Repair PAPER positions that earlier fleet runs split across several fills.

Before the one-position-per-coin fix, each extra buy of a held coin OVERWROTE the tracked position
(quantity and entry of the last fill only), orphaning the earlier fills from their stop and target.
This rebuilds each open PAPER position from the journal: every BUY fill for the coin since its last
close, summed, with a volume-weighted entry price. Stop and target stay as recorded.

Runs only while the fleet is stopped (FleetManager.start calls it before spawning the child), only for
PAPER rows, and only ever increases a quantity to what the journal shows was actually bought.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List


def repair_paper_positions(execution_db: Path, journal_db: Path) -> List[Dict[str, Any]]:
    execution_db, journal_db = Path(execution_db), Path(journal_db)
    if not execution_db.is_file() or not journal_db.is_file():
        return []
    fixed: List[Dict[str, Any]] = []
    with closing(sqlite3.connect(str(execution_db), timeout=10)) as ex, \
            closing(sqlite3.connect(journal_db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as jr:
        ex.row_factory = sqlite3.Row
        rows = ex.execute("SELECT * FROM positions WHERE mode='PAPER' AND upper(side)='BUY'").fetchall()
        for r in rows:
            sym = r["symbol"]
            last_close = jr.execute(
                "SELECT max(t) FROM (SELECT max(timestamp) t FROM positions_closed WHERE symbol=? "
                "UNION ALL SELECT max(timestamp) FROM fills WHERE symbol=? AND upper(side)='SELL')", (sym, sym)).fetchone()[0] or 0.0
            buys = jr.execute("SELECT quantity, fill_price FROM fills WHERE symbol=? AND upper(side)='BUY' AND timestamp>?",
                              (sym, last_close)).fetchall()
            qty = sum(float(q) for q, _ in buys)
            if qty <= float(r["quantity"]) * (1 + 1e-9):
                continue
            entry = sum(float(q) * float(p) for q, p in buys) / qty
            ex.execute("UPDATE positions SET quantity=?, entry_price=? WHERE symbol=?", (qty, entry, sym))
            det = ex.execute("SELECT payload FROM position_details WHERE symbol=?", (sym,)).fetchone()
            if det:
                payload = json.loads(det[0])
                payload.update(quantity=qty, entry_price=entry)
                ex.execute("UPDATE position_details SET payload=? WHERE symbol=?", (json.dumps(payload), sym))
            fixed.append({"symbol": sym, "was_qty": float(r["quantity"]), "qty": qty, "entry": entry, "fills": len(buys)})
        ex.commit()
    return fixed
