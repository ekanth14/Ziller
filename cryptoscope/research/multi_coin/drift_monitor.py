"""Live-vs-Backtest Drift Monitor & Auto-Pause Sentinel (Phase 7.1).

Continuously tracks live operational execution against backtested baselines:
1. Realized slippage vs backtest expectation.
2. Order fill rate (partially filled or rejected orders).
3. Rolling trade win rate degradation.
4. Peak-to-trough portfolio drawdown.
5. Automatic pause latch: freezes entry orders when drift exceeds limits.
6. Formats Telegram alert payloads without leaking secrets or tokens.
"""

from dataclasses import dataclass, field
import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("cryptoscope.research.multi_coin.drift_monitor")


@dataclass
class DriftBaseline:
    """Expected baseline metrics derived from 4-year backtest (Phase 6)."""
    expected_slippage_bps: float = 8.5       # Typical dynamic slippage
    expected_fill_rate_pct: float = 95.0     # Expected fill completion
    expected_win_rate_pct: float = 45.0      # Expected win rate
    max_acceptable_dd_pct: float = 10.0      # Hard drawdown budget


@dataclass
class DriftThresholds:
    """Tolerance boundaries before triggering an automated pause."""
    max_slippage_drift_bps: float = 15.0     # Pause if realized > 23.5 bps
    min_fill_rate_pct: float = 85.0          # Pause if fill rate < 85%
    min_win_rate_pct: float = 25.0           # Pause if win rate < 25% (min 15 trades)
    min_trades_for_win_rate: int = 15        # Minimum sample size
    max_drawdown_pct: float = 10.0           # Pause if DD >= 10%


@dataclass
class DriftReport:
    """Diagnostic report on execution health and drift status."""
    timestamp_utc: str
    pause_engaged: bool
    pause_reasons: List[str]
    total_trades: int
    realized_slippage_bps: float
    slippage_drift_bps: float
    fill_rate_pct: float
    win_rate_pct: float
    current_drawdown_pct: float
    baseline: Dict[str, float]


class LiveDriftMonitor:
    """Monitors live execution drift and activates deterministic circuit pauses."""

    def __init__(
        self,
        baseline: Optional[DriftBaseline] = None,
        thresholds: Optional[DriftThresholds] = None,
        initial_nav: float = 1000.0,
    ):
        self.baseline = baseline or DriftBaseline()
        self.thresholds = thresholds or DriftThresholds()
        
        self.initial_nav = initial_nav
        self.current_nav = initial_nav
        self.peak_nav = initial_nav

        # Operational records
        self.trade_records: List[Dict[str, Any]] = []
        self.submitted_notional_usd: float = 0.0
        self.filled_notional_usd: float = 0.0
        
        # Latch
        self.pause_engaged: bool = False
        self.pause_reasons: List[str] = []

    def record_order_submission(self, notional_usd: float) -> None:
        """Records submitted order intent notional for fill-rate monitoring."""
        self.submitted_notional_usd += max(0.0, notional_usd)

    def record_fill(
        self,
        symbol: str,
        side: str,
        filled_notional_usd: float,
        nominal_price: float,
        effective_price: float,
    ) -> None:
        """Records filled trade details and calculates instantaneous slippage."""
        self.filled_notional_usd += max(0.0, filled_notional_usd)
        
        # Calculate realized slippage in bps
        if nominal_price > 0:
            if side.upper() == "BUY":
                slip_fraction = (effective_price - nominal_price) / nominal_price
            else:
                slip_fraction = (nominal_price - effective_price) / nominal_price
            slip_bps = max(0.0, slip_fraction * 10000.0)
        else:
            slip_bps = 0.0

        self.trade_records.append({
            "symbol": symbol.upper(),
            "side": side.upper(),
            "notional_usd": filled_notional_usd,
            "slippage_bps": slip_bps,
            "pnl_usd": 0.0,  # Updated on closure
            "closed": False,
        })

    def record_position_closed(self, symbol: str, net_pnl_usd: float, current_nav: float) -> None:
        """Records closed trade PnL and updates NAV tracking."""
        self.current_nav = current_nav
        if self.current_nav > self.peak_nav:
            self.peak_nav = self.current_nav

        # Attach PnL to matching open record
        for tr in reversed(self.trade_records):
            if tr["symbol"] == symbol.upper() and not tr["closed"]:
                tr["pnl_usd"] = net_pnl_usd
                tr["closed"] = True
                break

        # Re-check drift after closure
        self.evaluate_drift()

    def evaluate_drift(self) -> DriftReport:
        """Evaluates current live execution metrics against baseline and thresholds."""
        pause_triggers = []

        # 1. Realized slippage
        slips = [t["slippage_bps"] for t in self.trade_records]
        avg_slippage = (sum(slips) / len(slips)) if slips else self.baseline.expected_slippage_bps
        slippage_drift = avg_slippage - self.baseline.expected_slippage_bps

        if slippage_drift > self.thresholds.max_slippage_drift_bps:
            pause_triggers.append(
                f"Slippage drift (+{slippage_drift:.1f} bps) exceeds threshold (+{self.thresholds.max_slippage_drift_bps:.1f} bps)"
            )

        # 2. Fill rate
        if self.submitted_notional_usd > 0:
            fill_rate = (self.filled_notional_usd / self.submitted_notional_usd) * 100.0
        else:
            fill_rate = 100.0

        if fill_rate < self.thresholds.min_fill_rate_pct and self.submitted_notional_usd >= 100.0:
            pause_triggers.append(
                f"Fill rate ({fill_rate:.1f}%) dropped below threshold ({self.thresholds.min_fill_rate_pct:.1f}%)"
            )

        # 3. Rolling win rate
        closed_trades = [t for t in self.trade_records if t["closed"]]
        if len(closed_trades) >= self.thresholds.min_trades_for_win_rate:
            wins = len([t for t in closed_trades if t["pnl_usd"] > 0])
            win_rate = (wins / len(closed_trades)) * 100.0
            if win_rate < self.thresholds.min_win_rate_pct:
                pause_triggers.append(
                    f"Win rate ({win_rate:.1f}%) dropped below threshold ({self.thresholds.min_win_rate_pct:.1f}%) across {len(closed_trades)} trades"
                )
        else:
            win_rate = self.baseline.expected_win_rate_pct

        # 4. Drawdown
        current_dd = ((self.peak_nav - self.current_nav) / self.peak_nav) * 100.0 if self.peak_nav > 0 else 0.0
        if current_dd >= self.thresholds.max_drawdown_pct:
            pause_triggers.append(
                f"Portfolio drawdown ({current_dd:.1f}%) breached limit ({self.thresholds.max_drawdown_pct:.1f}%)"
            )

        # Engage pause if any trigger fired
        if pause_triggers and not self.pause_engaged:
            self.pause_engaged = True
            self.pause_reasons = pause_triggers
            logger.warning("AUTOMATIC PAUSE ENGAGED: %s", " | ".join(pause_triggers))

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return DriftReport(
            timestamp_utc=now_str,
            pause_engaged=self.pause_engaged,
            pause_reasons=self.pause_reasons,
            total_trades=len(self.trade_records),
            realized_slippage_bps=round(avg_slippage, 2),
            slippage_drift_bps=round(slippage_drift, 2),
            fill_rate_pct=round(fill_rate, 2),
            win_rate_pct=round(win_rate, 2),
            current_drawdown_pct=round(max(0.0, current_dd), 2),
            baseline={
                "expected_slippage_bps": self.baseline.expected_slippage_bps,
                "expected_fill_rate_pct": self.baseline.expected_fill_rate_pct,
                "expected_win_rate_pct": self.baseline.expected_win_rate_pct,
                "max_acceptable_dd_pct": self.baseline.max_acceptable_dd_pct,
            },
        )

    def format_telegram_alert(self, report: DriftReport) -> str:
        """Constructs sanitized Telegram alert message without secrets."""
        status_icon = "🚨 [DRIFT PAUSE ENGAGED]" if report.pause_engaged else "ℹ️ [EXECUTION STABLE]"
        lines = [
            f"{status_icon}",
            f"UTC: {report.timestamp_utc}",
            f"Realized Slippage: {report.realized_slippage_bps} bps (Baseline: {report.baseline['expected_slippage_bps']} bps)",
            f"Fill Rate: {report.fill_rate_pct}% (Min: {self.thresholds.min_fill_rate_pct}%)",
            f"Win Rate: {report.win_rate_pct}% (Baseline: {report.baseline['expected_win_rate_pct']}%)",
            f"Drawdown: {report.current_drawdown_pct}% (Max: {report.baseline['max_acceptable_dd_pct']}%)",
        ]
        if report.pause_engaged:
            lines.append("\nViolations:")
            for r in report.pause_reasons:
                lines.append(f" • {r}")
            lines.append("\nAction: Trading entry paused. Manual dashboard re-auth required.")

        return "\n".join(lines)

    def clear_pause(self) -> None:
        """Clears pause state upon explicit operator re-authentication."""
        self.pause_engaged = False
        self.pause_reasons = []
        logger.info("Drift pause cleared by authorized operator.")
