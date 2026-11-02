"""JournalBot: Complete chronological audit logging and quantitative performance metrics."""

import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import (
    BaseEvent,
    DebateResult,
    Fill,
    OrderRequest,
    PositionClosed,
    RiskDecision,
    Signal,
    TradeIntent,
)

logger = logging.getLogger("cryptoscope.orchestrator.journal_bot")


class JournalBot(BaseBot):
    """Logs every signal, trade intent, debate, risk veto, order, fill, and position closure.

    Computes institutional performance analytics:
    - Win Rate & Profit Factor
    - Mathematical Expectancy ($E = (P_{win} \times \bar{W}) - (P_{loss} \times |\bar{L}|)$)
    - Maximum Historical Drawdown
    - Execution Friction (Total Fees Paid + Average Realized Slippage)
    """

    def __init__(
        self,
        bus: EventBus,
        name: str = "journal_bot",
        db_path: Optional[str] = None
    ):
        super().__init__(name, bus)
        self.db_path = Path(db_path or "work/runtime/trading_journal.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        self.subscribe(Signal)
        self.subscribe(TradeIntent)
        self.subscribe(DebateResult)
        self.subscribe(RiskDecision)
        self.subscribe(OrderRequest)
        self.subscribe(Fill)
        self.subscribe(PositionClosed)

    def _init_db(self) -> None:
        """Create journal tables with indexes and WAL journal mode."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS signals (
                    timestamp REAL NOT NULL,
                    signal_id TEXT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reasons TEXT,
                    strategy_id TEXT
                );
                CREATE TABLE IF NOT EXISTS trade_intents (
                    timestamp REAL NOT NULL,
                    intent_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    strategy_id TEXT
                );
                CREATE TABLE IF NOT EXISTS debates (
                    timestamp REAL NOT NULL,
                    intent_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    conviction_score REAL NOT NULL,
                    bull_thesis TEXT,
                    bear_thesis TEXT,
                    risk_summary TEXT
                );
                CREATE TABLE IF NOT EXISTS risk_decisions (
                    timestamp REAL NOT NULL,
                    intent_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    veto_reasons TEXT,
                    approved_quantity REAL,
                    position_size_usd REAL,
                    stop_distance_pct REAL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    timestamp REAL NOT NULL,
                    order_id TEXT PRIMARY KEY,
                    intent_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL,
                    stop_price REAL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fills (
                    timestamp REAL NOT NULL,
                    fill_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    fill_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    fee_usd REAL NOT NULL,
                    slippage_pct REAL NOT NULL,
                    stop_order_id TEXT
                );
                CREATE TABLE IF NOT EXISTS positions_closed (
                    timestamp REAL NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    pnl_usd REAL NOT NULL,
                    pnl_pct REAL NOT NULL,
                    duration_seconds REAL NOT NULL,
                    exit_reason TEXT NOT NULL
                );
            """)
            conn.commit()
        finally:
            conn.close()

    async def on_event(self, event: BaseEvent) -> None:
        """Route incoming events into SQLite journal."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            if isinstance(event, Signal):
                reasons_str = "; ".join(event.reasons) if isinstance(event.reasons, list) else str(event.reasons)
                conn.execute(
                    "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (event.timestamp, getattr(event, "signal_id", ""), event.symbol, event.direction,
                     event.confidence, reasons_str, getattr(event, "strategy_id", "core"))
                )
            elif isinstance(event, TradeIntent):
                conn.execute(
                    "INSERT OR REPLACE INTO trade_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (event.timestamp, event.intent_id, event.symbol, event.direction,
                     event.entry_price, event.stop_loss, event.take_profit, getattr(event, "strategy_id", ""))
                )
            elif isinstance(event, DebateResult):
                conn.execute(
                    "INSERT OR REPLACE INTO debates VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (event.timestamp, event.intent_id, event.symbol, event.verdict,
                     event.conviction_score, event.bull_thesis, event.bear_thesis, event.risk_summary)
                )
            elif isinstance(event, RiskDecision):
                veto_str = "; ".join(event.veto_reasons) if isinstance(event.veto_reasons, list) else str(event.veto_reasons)
                conn.execute(
                    "INSERT OR REPLACE INTO risk_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (event.timestamp, event.intent_id, event.symbol, event.decision,
                     veto_str, event.approved_quantity, event.position_size_usd, event.stop_distance_pct)
                )
            elif isinstance(event, OrderRequest):
                conn.execute(
                    "INSERT OR REPLACE INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (event.timestamp, event.order_id, event.intent_id, event.symbol,
                     event.side, event.order_type, event.quantity, event.price, event.stop_price, "SUBMITTED")
                )
            elif isinstance(event, Fill):
                price = getattr(event, "executed_price", getattr(event, "fill_price", 0.0))
                fee = getattr(event, "fee", getattr(event, "fee_usd", 0.0))
                slippage = getattr(event, "slippage_pct", 0.0)
                conn.execute(
                    "INSERT OR REPLACE INTO fills VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (event.timestamp, event.fill_id, event.order_id, event.symbol,
                     event.side, price, event.quantity, fee, slippage, event.stop_order_id)
                )
            elif isinstance(event, PositionClosed):
                conn.execute(
                    "INSERT INTO positions_closed VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (event.timestamp, event.symbol, event.side, event.entry_price,
                     event.exit_price, event.quantity, event.pnl_usd, event.pnl_pct, event.duration_seconds, event.exit_reason)
                )
            conn.commit()
        except Exception as exc:
            logger.error("[%s] Database write error on event %s: %s", self.name, event.event_type, exc)
        finally:
            conn.close()

    def get_performance_metrics(self, window_days: int = 1) -> Dict[str, Any]:
        """Compute performance metrics across the given historical window."""
        cutoff = time.time() - (window_days * 86400.0)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM positions_closed WHERE timestamp >= ? ORDER BY timestamp ASC", (cutoff,))
            trades = [dict(r) for r in cur.fetchall()]

            cur.execute("SELECT fee_usd, slippage_pct FROM fills WHERE timestamp >= ?", (cutoff,))
            fills = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

        total_trades = len(trades)
        if total_trades == 0:
            return {
                "period_days": window_days,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "expectancy_usd": 0.0,
                "net_pnl_usd": 0.0,
                "max_drawdown_usd": 0.0,
                "total_fees_usd": sum(f.get("fee_usd", 0.0) for f in fills),
                "avg_slippage_pct": 0.0
            }

        pnls = [t["pnl_usd"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0

        total_gross_win = sum(wins)
        total_gross_loss = sum(losses)
        profit_factor = round(total_gross_win / total_gross_loss, 2) if total_gross_loss > 0 else 999.0

        p_win = win_count / total_trades
        p_loss = loss_count / total_trades
        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
        expectancy = (p_win * avg_win) - (p_loss * avg_loss)

        # Cumulative drawdown calculation
        cum_pnl = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            cum_pnl += p
            if cum_pnl > peak:
                peak = cum_pnl
            dd = peak - cum_pnl
            if dd > max_dd:
                max_dd = dd

        total_fees = sum(f.get("fee_usd", 0.0) for f in fills)
        avg_slippage = (sum(f.get("slippage_pct", 0.0) for f in fills) / len(fills)) if fills else 0.0

        return {
            "period_days": window_days,
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": profit_factor,
            "expectancy_usd": round(expectancy, 2),
            "net_pnl_usd": round(sum(pnls), 2),
            "max_drawdown_usd": round(max_dd, 2),
            "total_fees_usd": round(total_fees, 2),
            "avg_slippage_pct": round(avg_slippage, 4)
        }

    def generate_report(self, period: str = "daily") -> str:
        """Render a formatted performance summary report."""
        days = 1 if period == "daily" else 7
        m = self.get_performance_metrics(window_days=days)
        title = f"📊 ZILLERS {period.upper()} PERFORMANCE REPORT ({days}D)"
        pnl_symbol = "🟢" if m["net_pnl_usd"] >= 0 else "🔴"
        pnl_str = f"+${m['net_pnl_usd']:,.2f}" if m["net_pnl_usd"] >= 0 else f"-${abs(m['net_pnl_usd']):,.2f}"
        exp_str = f"+${m['expectancy_usd']:,.2f}" if m["expectancy_usd"] >= 0 else f"-${abs(m['expectancy_usd']):,.2f}"

        lines = [
            f"<b>{title}</b>",
            f"━━━━━━━━━━━━━━━━━━━",
            f"{pnl_symbol} <b>Net PnL:</b> {pnl_str}",
            f"🎯 <b>Win Rate:</b> {m['win_rate_pct']:.1f}% ({m['winning_trades']}W / {m['losing_trades']}L / {m['total_trades']} Total)",
            f"📈 <b>Profit Factor:</b> {m['profit_factor']}",
            f"🎲 <b>Trade Expectancy:</b> {exp_str}/trade",
            f"📉 <b>Max Drawdown:</b> ${m['max_drawdown_usd']:,.2f}",
            f"⛽ <b>Fees Paid:</b> ${m['total_fees_usd']:,.2f}",
            f"⚡ <b>Avg Slippage:</b> {m['avg_slippage_pct']:.4f}%",
            f"━━━━━━━━━━━━━━━━━━━"
        ]
        return "\n".join(lines)
