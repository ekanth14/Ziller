"""Grid and DCA paper bots (ideas from OctoBot / Hummingbot executors; independent implementation).

Paper only: no exchange orders. Bots advance on real Binance 1-minute candles, processed in order,
so restarts never skip or double-count a candle. A resting buy fills when a candle's low reaches
its price; a resting sell when the high reaches it; fills happen at the order price (limit-style),
with a taker-equivalent fee per fill. An order created on a candle can only fill on later candles.

GRID  (spot, neutral)
  levels L0 < L1 < ... < Ln evenly spaced in [lower, upper]; equal quote per grid.
  Start: market-buy inventory for every level above the price (so those sells can rest), then
  rest buys on the levels below. Buy filled at Li -> rest sell at Li+1. Sell filled at Li -> rest
  buy at Li-1. Each buy->sell round trip earns qty x (Li+1 - Li) minus fees.

DCA   (spot, long)
  Base order at market. Safety order k (k = 1..N) rests at
      entry x (1 - step x sum_{j<k} step_scale^j)   with quote size base x volume_scale^k.
  Take profit: sell everything at average_entry x (1 + take_profit). Optional stop loss below the
  last safety level. After a take profit a new cycle starts automatically.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

FEE = 0.001  # 0.1% per fill (Binance spot taker without BNB discount)

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS bots (id TEXT PRIMARY KEY, kind TEXT NOT NULL, symbol TEXT NOT NULL,
       config TEXT NOT NULL, state TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL,
       updated_at REAL NOT NULL, created_by TEXT)""",
    """CREATE TABLE IF NOT EXISTS bot_fills (bot_id TEXT NOT NULL, ts REAL NOT NULL, side TEXT NOT NULL,
       price REAL NOT NULL, qty REAL NOT NULL, fee REAL NOT NULL, note TEXT)""",
]


# --------------------------------------------------------------------------- validation
def validate(kind: str, cfg: Dict[str, Any], price: float) -> Dict[str, Any]:
    kind = kind.upper()
    num = lambda k, d=None: float(cfg.get(k, d)) if cfg.get(k, d) is not None else None  # noqa: E731
    if kind == "GRID":
        lower, upper, levels, invest = num("lower"), num("upper"), int(cfg.get("levels", 10)), num("investment")
        if not (lower and upper and invest) or lower <= 0 or upper <= lower * 1.001:
            raise ValueError("Grid needs 0 < lower < upper")
        if not 2 <= levels <= 100:
            raise ValueError("Grid levels must be between 2 and 100")
        if not lower < price < upper:
            raise ValueError(f"Current price {price:g} must be inside the grid range")
        if invest < 10:
            raise ValueError("Investment must be at least 10 USDT")
        return {"lower": lower, "upper": upper, "levels": levels, "investment": invest}
    if kind == "DCA":
        out = {"investment": num("investment"), "base_order": num("base_order"), "safety_orders": int(cfg.get("safety_orders", 5)),
               "step": num("step", 0.015), "step_scale": num("step_scale", 1.2), "volume_scale": num("volume_scale", 1.5),
               "take_profit": num("take_profit", 0.012), "stop_loss": num("stop_loss", 0.0) or 0.0}
        if not out["investment"] or not out["base_order"] or out["base_order"] < 5:
            raise ValueError("DCA needs investment and a base order of at least 5 USDT")
        if not 0 <= out["safety_orders"] <= 20 or not 0.001 <= out["step"] <= 0.2 or not 0.001 <= out["take_profit"] <= 0.5:
            raise ValueError("DCA parameters out of range")
        need = out["base_order"] * sum(out["volume_scale"] ** k for k in range(out["safety_orders"] + 1))
        if need > out["investment"] * 1.0001:
            raise ValueError(f"Base + safety orders need {need:.2f} USDT, more than the investment")
        return out
    raise ValueError("kind must be GRID or DCA")


# --------------------------------------------------------------------------- bot logic (pure)
def _fill(state, side, price, qty, ts, note, fills):
    fee = price * qty * FEE
    if side == "BUY":
        state["cash"] -= price * qty + fee
        state["base"] += qty
    else:
        state["cash"] += price * qty - fee
        state["base"] -= qty
    state["fees"] += fee
    state["fill_count"] += 1
    fills.append({"ts": ts, "side": side, "price": price, "qty": qty, "fee": fee, "note": note})


def grid_start(cfg, price, ts):
    n, lo, hi = cfg["levels"], cfg["lower"], cfg["upper"]
    levels = [lo + (hi - lo) * i / n for i in range(n + 1)]
    per_grid = cfg["investment"] / n
    state = {"levels": levels, "orders": [], "cash": cfg["investment"], "base": 0.0, "fees": 0.0, "realized": 0.0,
             "round_trips": 0, "fill_count": 0, "last_ts": ts, "start_price": price}
    fills: List[Dict[str, Any]] = []
    sell_levels = [i for i, L in enumerate(levels) if L > price and i > 0]
    inv_qty = sum(per_grid / levels[i - 1] for i in sell_levels)
    if inv_qty:
        _fill(state, "BUY", price, inv_qty, ts, "initial inventory for sell levels", fills)
    for i, L in enumerate(levels):
        if i > 0 and L > price:
            state["orders"].append({"side": "SELL", "level": i, "price": L, "qty": per_grid / levels[i - 1], "cost": levels[i - 1], "since": ts})
        elif L < price and i < n:
            state["orders"].append({"side": "BUY", "level": i, "price": L, "qty": per_grid / L, "since": ts})
    return state, fills


def grid_step(cfg, state, candle):
    fills: List[Dict[str, Any]] = []
    ts, lo, hi = candle["open_time"], candle["low"], candle["high"]
    levels, keep, new = state["levels"], [], []
    for o in state["orders"]:
        if o["since"] >= ts:  # placed on this candle: may only fill later
            keep.append(o)
            continue
        if o["side"] == "BUY" and lo <= o["price"]:
            _fill(state, "BUY", o["price"], o["qty"], ts, f"grid buy L{o['level']}", fills)
            if o["level"] + 1 < len(levels):
                new.append({"side": "SELL", "level": o["level"] + 1, "price": levels[o["level"] + 1], "qty": o["qty"],
                            "cost": o["price"], "since": ts})
        elif o["side"] == "SELL" and hi >= o["price"]:
            _fill(state, "SELL", o["price"], o["qty"], ts, f"grid sell L{o['level']}", fills)
            state["realized"] += o["qty"] * (o["price"] - o["cost"]) - o["qty"] * (o["price"] + o["cost"]) * FEE
            state["round_trips"] += 1
            if o["level"] - 1 >= 0:
                new.append({"side": "BUY", "level": o["level"] - 1, "price": levels[o["level"] - 1], "qty": o["qty"], "since": ts})
        else:
            keep.append(o)
    state["orders"] = keep + new
    state["last_ts"] = ts
    return fills


def dca_start(cfg, price, ts):
    state = {"cash": cfg["investment"], "base": 0.0, "fees": 0.0, "realized": 0.0, "cycles": 0, "fill_count": 0,
             "last_ts": ts, "start_price": price}
    fills: List[Dict[str, Any]] = []
    _dca_new_cycle(cfg, state, price, ts, fills)
    return state, fills


def _dca_new_cycle(cfg, state, price, ts, fills):
    qty = cfg["base_order"] / price
    _fill(state, "BUY", price, qty, ts, "base order", fills)
    state.update(entry=price, cycle_cost=price * qty * (1 + FEE), cycle_qty=qty, next_so=1, cycle_started=ts)
    state["safety"] = []
    cum = 0.0
    for k in range(1, cfg["safety_orders"] + 1):
        cum += cfg["step"] * cfg["step_scale"] ** (k - 1)
        p = price * (1 - cum)
        state["safety"].append({"k": k, "price": p, "qty": cfg["base_order"] * cfg["volume_scale"] ** k / p, "since": ts})


def dca_step(cfg, state, candle):
    fills: List[Dict[str, Any]] = []
    ts, lo, hi = candle["open_time"], candle["low"], candle["high"]
    if state.get("cycle_qty", 0) <= 0:
        _dca_new_cycle(cfg, state, candle["open"], ts, fills)
        state["last_ts"] = ts
        return fills
    remaining = []
    for so in state["safety"]:
        if so["since"] < ts and lo <= so["price"]:
            _fill(state, "BUY", so["price"], so["qty"], ts, f"safety order {so['k']}", fills)
            state["cycle_cost"] += so["price"] * so["qty"] * (1 + FEE)
            state["cycle_qty"] += so["qty"]
        else:
            remaining.append(so)
    state["safety"] = remaining
    avg = state["cycle_cost"] / state["cycle_qty"]
    tp = avg * (1 + cfg["take_profit"])
    sl = None
    if cfg["stop_loss"] > 0:
        deepest = min([so["price"] for so in state["safety"]] + [avg])
        sl = deepest * (1 - cfg["stop_loss"])
    exit_price, note = None, None
    if sl and lo <= sl:
        exit_price, note = sl, "stop loss"
    elif hi >= tp and not fills:  # a candle that filled a safety order exits on a later candle
        exit_price, note = tp, "take profit"
    if exit_price:
        qty = state["cycle_qty"]
        _fill(state, "SELL", exit_price, qty, ts, note, fills)
        state["realized"] += exit_price * qty * (1 - FEE) - state["cycle_cost"]
        state["cycles"] += 1
        state.update(cycle_qty=0.0, cycle_cost=0.0, safety=[], last_exit=note)
    state["avg_entry"] = avg if state["cycle_qty"] else None
    state["take_profit_price"] = tp if state["cycle_qty"] else None
    state["last_ts"] = ts
    return fills


# --------------------------------------------------------------------------- manager
class PaperBotManager:
    def __init__(self, path: str, candles: Callable[[str, int], List[Dict[str, float]]],
                 price: Callable[[str], float], gate: Callable[[], bool] = lambda: True,
                 notify: Optional[Callable[[str], Any]] = None, period: float = 20.0):
        self.path, self.candles, self.price = Path(path), candles, price
        self.gate, self.notify, self.period = gate, notify, period
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            for stmt in SCHEMA:
                db.execute(stmt)
            db.commit()

    def _db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def create(self, kind: str, symbol: str, cfg: Dict[str, Any], actor: str) -> Dict[str, Any]:
        kind, symbol = kind.upper(), symbol.upper()
        price = float(self.price(symbol))
        cfg = validate(kind, cfg, price)
        now_bar = time.time() // 60 * 60
        state, fills = (grid_start if kind == "GRID" else dca_start)(cfg, price, now_bar)
        bot_id = uuid.uuid4().hex[:12]
        with self._lock, closing(self._db()) as db:
            db.execute("INSERT INTO bots VALUES (?,?,?,?,?,?,?,?,?)", (bot_id, kind, symbol, json.dumps(cfg), json.dumps(state),
                                                                      "RUNNING", time.time(), time.time(), actor))
            self._save_fills(db, bot_id, fills)
            db.commit()
        self._notify(f"🤖 <b>Paper {kind} bot started</b> · {symbol}\nInvestment {cfg['investment']:.2f} USDT")
        self.ensure_running()
        return self.get(bot_id)

    def _save_fills(self, db, bot_id, fills):
        db.executemany("INSERT INTO bot_fills VALUES (?,?,?,?,?,?,?)",
                       [(bot_id, f["ts"], f["side"], f["price"], f["qty"], f["fee"], f["note"]) for f in fills])

    def set_status(self, bot_id: str, status: str) -> Dict[str, Any]:
        with self._lock, closing(self._db()) as db:
            db.execute("UPDATE bots SET status=?, updated_at=? WHERE id=?", (status, time.time(), bot_id))
            db.commit()
        return self.get(bot_id)

    def delete(self, bot_id: str) -> None:
        with self._lock, closing(self._db()) as db:
            db.execute("DELETE FROM bots WHERE id=?", (bot_id,))
            db.execute("DELETE FROM bot_fills WHERE bot_id=?", (bot_id,))
            db.commit()

    def tick(self) -> int:
        """Advance every running bot over the 1m candles closed since its last processed candle."""
        if not self.gate():
            return 0
        processed = 0
        with self._lock, closing(self._db()) as db:
            bots = db.execute("SELECT * FROM bots WHERE status='RUNNING'").fetchall()
            for b in bots:
                cfg, state = json.loads(b["config"]), json.loads(b["state"])
                try:
                    rows = self.candles(b["symbol"], 120)
                except Exception:
                    continue
                now = time.time()
                new = [c for c in rows if c["open_time"] > state["last_ts"] and c["open_time"] + 60 <= now]
                step = grid_step if b["kind"] == "GRID" else dca_step
                all_fills = []
                for c in new:
                    all_fills += step(cfg, state, c)
                    processed += 1
                if new:
                    db.execute("UPDATE bots SET state=?, updated_at=? WHERE id=?", (json.dumps(state), now, b["id"]))
                    self._save_fills(db, b["id"], all_fills)
                    for f in all_fills:
                        if f["note"] in {"take profit", "stop loss"}:
                            self._notify(f"{'🎯' if f['note'] == 'take profit' else '🛑'} <b>Paper DCA {f['note']}</b> · {b['symbol']} "
                                         f"@ {f['price']:g} · realised {state['realized']:+.2f} USDT")
            db.commit()
        return processed

    def _notify(self, text):
        if self.notify:
            threading.Thread(target=self.notify, args=(text,), daemon=True).start()

    def summary(self, b, mark: Optional[float]) -> Dict[str, Any]:
        cfg, state = json.loads(b["config"]), json.loads(b["state"])
        mark = mark or state.get("start_price")
        equity = state["cash"] + state["base"] * mark
        out = {"id": b["id"], "kind": b["kind"], "symbol": b["symbol"], "status": b["status"], "config": cfg,
               "created_at": b["created_at"], "mark": mark, "cash": state["cash"], "base": state["base"],
               "equity": equity, "pnl": equity - cfg["investment"], "pnl_pct": equity / cfg["investment"] - 1,
               "realized": state["realized"], "fees": state["fees"], "fills": state["fill_count"],
               "hold_pnl_pct": mark / state["start_price"] - 1 if state.get("start_price") else None}
        if b["kind"] == "GRID":
            out.update(round_trips=state["round_trips"], open_orders=len(state["orders"]),
                       in_range=cfg["lower"] <= mark <= cfg["upper"], levels=state["levels"])
        else:
            out.update(cycles=state["cycles"], avg_entry=state.get("avg_entry"), take_profit_price=state.get("take_profit_price"),
                       safety_left=len(state.get("safety", [])))
        return out

    def get(self, bot_id: str) -> Dict[str, Any]:
        with closing(self._db()) as db:
            b = db.execute("SELECT * FROM bots WHERE id=?", (bot_id,)).fetchone()
            if not b:
                raise KeyError(bot_id)
            fills = db.execute("SELECT ts, side, price, qty, fee, note FROM bot_fills WHERE bot_id=? ORDER BY ts DESC, rowid DESC LIMIT 30",
                               (bot_id,)).fetchall()
        try:
            mark = float(self.price(b["symbol"]))
        except Exception:
            mark = None
        return {**self.summary(b, mark), "recent_fills": [dict(f) for f in fills]}

    def list(self) -> List[Dict[str, Any]]:
        with closing(self._db()) as db:
            bots = db.execute("SELECT * FROM bots ORDER BY created_at DESC").fetchall()
        marks: Dict[str, Optional[float]] = {}
        out = []
        for b in bots:
            if b["symbol"] not in marks:
                try:
                    marks[b["symbol"]] = float(self.price(b["symbol"]))
                except Exception:
                    marks[b["symbol"]] = None
            out.append(self.summary(b, marks[b["symbol"]]))
        return out

    # ---------------------------------------------------------- background loop
    def ensure_running(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="paper-bots", daemon=True)
            self._thread.start()

    def _loop(self):
        while not self._stop.wait(self.period):
            try:
                self.tick()
            except Exception:
                pass

    def stop_loop(self):
        self._stop.set()
