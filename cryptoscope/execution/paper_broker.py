"""Atomic, idempotent spot simulation with fees and conservative mark exits."""
import json
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager
from cryptoscope.agents.risk.policy import validate
from cryptoscope.agents.schemas import number


class PaperBroker:
    def __init__(self, path, config):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config = config
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), cash REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, quantity REAL, entry REAL, stop REAL, target REAL);
                CREATE TABLE IF NOT EXISTS fills (run_id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS controls (id INTEGER PRIMARY KEY CHECK(id=1), halted INTEGER NOT NULL, reason TEXT NOT NULL, changed REAL NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO account VALUES (1, ?)", (config["initial_cash"],))
            db.execute("INSERT OR IGNORE INTO controls VALUES (1, 0, '', ?)", (time.time(),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute('PRAGMA journal_mode = WAL')
        db.execute('PRAGMA busy_timeout = 5000')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _portfolio(db):
        return {"cash": db.execute("SELECT cash FROM account WHERE id=1").fetchone()[0],
                "positions": {r[0]: {"quantity": r[1], "entry": r[2], "stop": r[3], "target": r[4]}
                              for r in db.execute("SELECT * FROM positions")}}

    def portfolio(self):
        with self.connect() as db:
            return self._portfolio(db)

    def set_halt(self, halted, reason='Manual operator control'):
        if type(halted) is not bool:
            raise ValueError('halted must be a boolean')
        with self.connect() as db:
            db.execute('UPDATE controls SET halted=?, reason=?, changed=? WHERE id=1',
                       (int(halted), str(reason)[:500], time.time()))
        return self.controls()

    def controls(self):
        with self.connect() as db:
            row = db.execute('SELECT halted,reason,changed FROM controls WHERE id=1').fetchone()
            return {'halted': bool(row[0]), 'reason': row[1], 'changed_at': row[2]}

    def _entry_reasons(self, db, portfolio, quote, now):
        return []

    def _after_fill(self, db, fill):
        pass

    def execute(self, run_id, proposal, snapshot, quote, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT body FROM fills WHERE run_id=?", (run_id,)).fetchone()
            if existing:
                return json.loads(existing[0])
            halted = db.execute('SELECT halted FROM controls WHERE id=1').fetchone()[0]
            if halted and proposal.action in {'LONG','SHORT'}:
                return {'status': 'rejected', 'approved': False, 'quantity': 0, 'reasons': ['MANUAL_ENTRY_HALT']}
            portfolio = self._portfolio(db)
            if proposal.action == 'LONG':
                reasons = self._entry_reasons(db, portfolio, quote, now)
                if reasons:
                    return {'status':'rejected','approved':False,'quantity':0,'reasons':reasons}
            gate = validate(proposal, snapshot, portfolio, quote, self.config, now)
            if not gate["approved"]:
                return {"status": "rejected", **gate}
            quantity = gate["quantity"]
            buy = proposal.action == "LONG"
            price = quote["ask"] * (1 + self.config["slippage_fraction"]) if buy else quote["bid"] * (1 - self.config["slippage_fraction"])
            fee = quantity * price * self.config["fee_fraction"]
            cash_change = -quantity * price - fee if buy else quantity * price - fee
            if buy:
                db.execute("INSERT INTO positions VALUES (?, ?, ?, ?, ?)",
                           (proposal.symbol, quantity, price, proposal.stop, proposal.target))
            else:
                remaining = portfolio["positions"][proposal.symbol]["quantity"] - quantity
                if remaining < 1e-12:
                    db.execute("DELETE FROM positions WHERE symbol=?", (proposal.symbol,))
                else:
                    db.execute("UPDATE positions SET quantity=? WHERE symbol=?", (remaining, proposal.symbol))
            db.execute("UPDATE account SET cash=cash+? WHERE id=1", (cash_change,))
            fill = {"status": "filled", "mode": "paper", "run_id": run_id, "symbol": proposal.symbol,
                    "action": proposal.action, "quantity": quantity, "price": price, "fee": fee, "at": now}
            db.execute("INSERT INTO fills VALUES (?, ?)", (run_id, json.dumps(fill, allow_nan=False)))
            self._after_fill(db, fill)
            return fill

    def mark(self, quote, now=None):
        """Evaluate exits when explicitly given a fresh quote. No background monitor."""
        now = time.time() if now is None else now
        bid = number(quote.get("bid"), "bid", 0.00000001)
        stamp = number(quote.get("available_at"), "quote time", 1)
        if not 0 <= now - stamp <= self.config["max_quote_age_seconds"]:
            raise ValueError("stale or future quote")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            position = self._portfolio(db)["positions"].get(quote["symbol"])
            if not position:
                return {"status": "no_position"}
            if position["stop"] < bid < position["target"]:
                return {"status": "open"}
            price = bid * (1 - self.config["slippage_fraction"])
            quantity = position["quantity"]
            fee = quantity * price * self.config["fee_fraction"]
            db.execute("UPDATE account SET cash=cash+? WHERE id=1", (quantity * price - fee,))
            db.execute("DELETE FROM positions WHERE symbol=?", (quote["symbol"],))
            key = f"mark-{quote['symbol']}-{now}"
            fill = {"status": "filled", "mode": "paper", "action": "CLOSE", "symbol": quote["symbol"],
                    "reason": "stop" if bid <= position["stop"] else "target", "price": price,
                    "quantity": quantity, "fee": fee, "at": now}
            db.execute("INSERT INTO fills VALUES (?, ?)", (key, json.dumps(fill)))
            self._after_fill(db, fill)
            return fill
