"""Trading protections (idea from freqtrade's "protections"; independent implementation).

Time-based, per-pair and global locks evaluated after every closed trade and checked before
every new entry. State is persisted so a restart never clears an active lock.

Guards
- CooldownPeriod   : after ANY exit on a pair, lock that pair for `cooldown_minutes`.
- StoplossGuard    : if >= `stoploss_limit` stop-loss exits happen within `stoploss_lookback_minutes`
                     -> lock ALL pairs (global) for `stoploss_lock_minutes`; per pair as well when
                     a single pair alone hits the limit.
- LowProfitPairs   : if a pair's last `lowprofit_trades` trades within `lowprofit_lookback_hours`
                     sum to <= `lowprofit_required` (fraction), lock that pair for `lowprofit_lock_hours`.
- MaxDrawdown      : if realised drawdown of the closed-trade equity curve within `drawdown_lookback_hours`
                     reaches `max_drawdown`, lock ALL pairs for `drawdown_lock_hours`.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GLOBAL = "*"


@dataclass
class ProtectionConfig:
    cooldown_minutes: float = 30.0
    stoploss_limit: int = 3
    stoploss_lookback_minutes: float = 360.0
    stoploss_lock_minutes: float = 120.0
    lowprofit_trades: int = 3
    lowprofit_lookback_hours: float = 48.0
    lowprofit_required: float = -0.02
    lowprofit_lock_hours: float = 12.0
    max_drawdown: float = 0.08
    drawdown_lookback_hours: float = 48.0
    drawdown_lock_hours: float = 24.0


@dataclass
class ClosedTrade:
    symbol: str
    closed_at: float
    pnl_pct: float          # fraction, e.g. -0.012
    pnl_usd: float
    exit_reason: str


@dataclass
class Lock:
    pair: str               # symbol or "*" for all pairs
    until: float
    reason: str
    guard: str
    created_at: float = field(default_factory=time.time)


class ProtectionManager:
    def __init__(self, config: Optional[ProtectionConfig] = None, state_path: Optional[str] = None,
                 clock=time.time):
        self.cfg = config or ProtectionConfig()
        self.path = Path(state_path) if state_path else None
        self.clock = clock
        self.trades: List[ClosedTrade] = []
        self.locks: List[Lock] = []
        self._lock = threading.Lock()
        self._load()

    # ---------------------------------------------------------- persistence
    def _load(self):
        if not self.path or not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.trades = [ClosedTrade(**t) for t in data.get("trades", [])]
            self.locks = [Lock(**l) for l in data.get("locks", [])]
        except (OSError, ValueError, TypeError):
            # Unreadable protection state fails closed: lock everything for an hour.
            self.locks = [Lock(GLOBAL, self.clock() + 3600, "Protection state unreadable", "Integrity")]

    def _save(self):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"trades": [asdict(t) for t in self.trades[-500:]],
                                   "locks": [asdict(l) for l in self.locks],
                                   "config": asdict(self.cfg)}), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---------------------------------------------------------- core
    def _add_lock(self, pair: str, minutes: float, reason: str, guard: str, now: float):
        until = now + minutes * 60
        for l in self.locks:  # extend an existing lock of the same guard instead of stacking
            if l.pair == pair and l.guard == guard and l.until >= now:
                l.until, l.reason = max(l.until, until), reason
                return
        self.locks.append(Lock(pair, until, reason, guard, now))

    def record_close(self, symbol: str, pnl_pct: float, pnl_usd: float, exit_reason: str,
                     closed_at: Optional[float] = None) -> List[Lock]:
        """Record a closed trade and evaluate every guard. Returns locks created/extended now."""
        now = closed_at or self.clock()
        c = self.cfg
        with self._lock:
            before = {(l.pair, l.guard, l.until) for l in self.locks}
            self.trades.append(ClosedTrade(symbol, now, pnl_pct, pnl_usd, exit_reason))
            # CooldownPeriod
            if c.cooldown_minutes > 0:
                self._add_lock(symbol, c.cooldown_minutes, f"Cooldown {c.cooldown_minutes:.0f} min after exit", "CooldownPeriod", now)
            # StoplossGuard (global and per pair)
            window = now - c.stoploss_lookback_minutes * 60
            stops = [t for t in self.trades if t.closed_at >= window and "STOP" in t.exit_reason.upper() and t.pnl_pct < 0]
            if len(stops) >= c.stoploss_limit:
                self._add_lock(GLOBAL, c.stoploss_lock_minutes,
                               f"{len(stops)} stop-losses in {c.stoploss_lookback_minutes / 60:.0f} h", "StoplossGuard", now)
            pair_stops = [t for t in stops if t.symbol == symbol]
            if len(pair_stops) >= c.stoploss_limit:
                self._add_lock(symbol, c.stoploss_lock_minutes, f"{len(pair_stops)} stop-losses on {symbol}", "StoplossGuard", now)
            # LowProfitPairs
            recent = [t for t in self.trades if t.symbol == symbol and t.closed_at >= now - c.lowprofit_lookback_hours * 3600]
            if len(recent) >= c.lowprofit_trades:
                total = sum(t.pnl_pct for t in recent[-c.lowprofit_trades:])
                if total <= c.lowprofit_required:
                    self._add_lock(symbol, c.lowprofit_lock_hours * 60,
                                   f"Last {c.lowprofit_trades} trades sum {total:+.2%}", "LowProfitPairs", now)
            # MaxDrawdown on the closed-trade equity curve
            window_trades = [t for t in self.trades if t.closed_at >= now - c.drawdown_lookback_hours * 3600]
            equity, peak, worst = 1.0, 1.0, 0.0
            for t in window_trades:
                equity *= 1 + t.pnl_pct
                peak = max(peak, equity)
                worst = min(worst, equity / peak - 1)
            if -worst >= c.max_drawdown:
                self._add_lock(GLOBAL, c.drawdown_lock_hours * 60,
                               f"Closed-trade drawdown {worst:.2%} in {c.drawdown_lookback_hours:.0f} h", "MaxDrawdown", now)
            self.trades = [t for t in self.trades if t.closed_at >= now - 7 * 86400]
            self.locks = [l for l in self.locks if l.until > now]
            created = [l for l in self.locks if (l.pair, l.guard, l.until) not in before]
            self._save()
            return created

    def is_locked(self, symbol: str, now: Optional[float] = None) -> Tuple[bool, List[str]]:
        now = now or self.clock()
        with self._lock:
            active = [l for l in self.locks if l.until > now and l.pair in {symbol, GLOBAL}]
        return bool(active), [f"PROTECTION_{l.guard.upper()}: {l.reason} (until {time.strftime('%H:%M', time.localtime(l.until))})"
                              for l in active]

    def status(self, now: Optional[float] = None) -> Dict[str, Any]:
        now = now or self.clock()
        with self._lock:
            locks = [{**asdict(l), "remaining_s": round(l.until - now)} for l in self.locks if l.until > now]
            return {"locks": sorted(locks, key=lambda l: l["until"]), "recent_trades": len(self.trades),
                    "config": asdict(self.cfg)}

    def clear(self, pair: Optional[str] = None) -> int:
        """Operator override (admin only at the API layer)."""
        with self._lock:
            n = len(self.locks)
            self.locks = [l for l in self.locks if pair is not None and l.pair != pair]
            self._save()
            return n - len(self.locks)


def read_status(state_path: str) -> Dict[str, Any]:
    """Read-only view for the dashboard (the fleet process owns the file)."""
    p = Path(state_path)
    if not p.is_file():
        return {"locks": [], "recent_trades": 0, "config": asdict(ProtectionConfig()), "fleet_state": "none yet"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"locks": [], "error": "unreadable"}
    now = time.time()
    locks = [{**l, "remaining_s": round(l["until"] - now)} for l in data.get("locks", []) if l["until"] > now]
    return {"locks": sorted(locks, key=lambda l: l["until"]), "recent_trades": len(data.get("trades", [])),
            "config": data.get("config", asdict(ProtectionConfig()))}
