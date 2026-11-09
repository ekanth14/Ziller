"""Portfolio Risk Manager for Multi-Coin Crypto Universe (Phase 5.3).

Deterministic portfolio-level risk engine:
1. Correlation-Cluster Limits: Caps exposure to any single economic cluster
   (Core L1, Alt L1, DeFi, PoW/Legacy, Payments).
2. Total Exposure Cap: Total active notional / NAV <= max_total_exposure_pct.
3. Max Concurrent Positions: Caps count of simultaneous active symbols.
4. Per-Coin Size Limit: Caps single symbol exposure / NAV.
5. Liquidity Depth Constraint: Order notional never exceeds a set fraction
   (e.g., 5%) of typical 1% depth.
6. Portfolio Drawdown Halt (10% peak-to-trough) & Daily Loss Halt (3%).
7. Trigger Logging: Records exact counts of every limit fired in backtest runs.
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("cryptoscope.research.multi_coin.portfolio_risk")

DEFAULT_CLUSTERS: Dict[str, Set[str]] = {
    "CORE": {"BTCUSDT", "ETHUSDT"},
    "L1_ALT": {"SOLUSDT", "BNBUSDT", "ADAUSDT", "AVAXUSDT", "NEARUSDT", "DOTUSDT"},
    "DEFI": {"UNIUSDT", "LINKUSDT", "ATOMUSDT"},
    "POW_LEGACY": {"LTCUSDT", "DOGEUSDT"},
    "PAYMENTS": {"XRPUSDT"},
}


@dataclass
class PortfolioRiskConfig:
    """Configurable constraints for multi-asset risk control."""
    max_total_exposure_pct: float = 0.80     # Max 80% portfolio total exposure
    max_concurrent_positions: int = 4        # Max 4 open positions
    max_per_coin_pct: float = 0.25           # Max 25% portfolio in any one symbol
    max_cluster_exposure_pct: float = 0.50   # Max 50% portfolio in any single cluster
    max_fraction_of_depth: float = 0.05      # Order <= 5% of estimated 1% depth
    max_drawdown_halt_pct: float = 0.10      # 10% peak-to-trough drawdown triggers halt
    max_daily_loss_halt_pct: float = 0.03    # 3% daily loss triggers halt
    min_notional_usd: float = 10.0           # Minimum Binance order notional


@dataclass
class RiskCheckResult:
    """Outcome of risk gating evaluation."""
    approved: bool
    approved_size_usd: float
    veto_reason: Optional[str] = None
    applied_caps: List[str] = field(default_factory=list)


class MultiCoinPortfolioRiskManager:
    """Evaluates multi-coin portfolio risk invariants deterministically."""

    def __init__(
        self,
        initial_nav: float = 1000.0,
        config: Optional[PortfolioRiskConfig] = None,
        clusters: Optional[Dict[str, Set[str]]] = None,
    ):
        self.initial_nav = initial_nav
        self.current_nav = initial_nav
        self.peak_nav = initial_nav
        self.config = config or PortfolioRiskConfig()
        self.clusters = clusters or DEFAULT_CLUSTERS
        
        # State tracking
        self.positions: Dict[str, float] = {}  # symbol -> current notional USD
        self.drawdown_halt_active: bool = False
        self.daily_loss_halt_active: bool = False
        
        self.day_start_nav: float = initial_nav
        self.current_day_start_ms: int = 0

        # Trigger counters for backtest reporting
        self.trigger_counts: Dict[str, int] = {
            "drawdown_halt": 0,
            "daily_loss_halt": 0,
            "max_positions": 0,
            "max_total_exposure": 0,
            "cluster_limit": 0,
            "per_coin_cap": 0,
            "liquidity_depth_cap": 0,
            "min_notional_fail": 0,
        }

    def get_symbol_cluster(self, symbol: str) -> str:
        """Maps symbol to its correlation cluster."""
        sym = symbol.upper()
        for c_name, members in self.clusters.items():
            if sym in members:
                return c_name
        return "OTHER"

    def update_equity(self, current_nav: float, timestamp_ms: int) -> None:
        """Updates portfolio NAV and checks drawdown and daily loss circuits."""
        self.current_nav = max(current_nav, 0.01)
        
        # Check day boundary (rolling 24h or day reset)
        day_boundary_ms = 86400 * 1000
        if self.current_day_start_ms == 0 or timestamp_ms >= self.current_day_start_ms + day_boundary_ms:
            self.current_day_start_ms = timestamp_ms
            self.day_start_nav = self.current_nav
            # Clear daily loss halt on new day if drawdown allows
            self.daily_loss_halt_active = False

        # Peak tracking
        if self.current_nav > self.peak_nav:
            self.peak_nav = self.current_nav

        # Drawdown check
        drawdown_pct = (self.peak_nav - self.current_nav) / self.peak_nav
        if drawdown_pct >= self.config.max_drawdown_halt_pct:
            if not self.drawdown_halt_active:
                self.trigger_counts["drawdown_halt"] += 1
            self.drawdown_halt_active = True

        # Daily loss check
        if self.day_start_nav > 0:
            daily_loss_pct = (self.day_start_nav - self.current_nav) / self.day_start_nav
            if daily_loss_pct >= self.config.max_daily_loss_halt_pct:
                if not self.daily_loss_halt_active:
                    self.trigger_counts["daily_loss_halt"] += 1
                self.daily_loss_halt_active = True

    def evaluate_order(
        self,
        symbol: str,
        side: str,
        requested_size_usd: float,
        est_depth_1pct_usd: float,
        current_nav: Optional[float] = None,
        timestamp_ms: Optional[int] = None,
    ) -> RiskCheckResult:
        """Determines whether a proposed order meets all portfolio risk gates.
        
        Down-scales order size if capped, or vetos if hard limits are exceeded.
        """
        sym = symbol.upper()
        side_clean = side.upper()

        if current_nav is not None and timestamp_ms is not None:
            self.update_equity(current_nav, timestamp_ms)

        # Exits are always permitted (reducing risk)
        if side_clean == "SELL" and sym in self.positions:
            return RiskCheckResult(
                approved=True,
                approved_size_usd=min(requested_size_usd, self.positions[sym]),
                veto_reason=None,
            )

        # 1. Circuit breakers
        if self.drawdown_halt_active:
            self.trigger_counts["drawdown_halt"] += 1
            return RiskCheckResult(
                approved=False,
                approved_size_usd=0.0,
                veto_reason="veto_drawdown_halt_engaged",
            )

        if self.daily_loss_halt_active:
            self.trigger_counts["daily_loss_halt"] += 1
            return RiskCheckResult(
                approved=False,
                approved_size_usd=0.0,
                veto_reason="veto_daily_loss_halt_engaged",
            )

        # 2. Max concurrent positions
        if sym not in self.positions and len(self.positions) >= self.config.max_concurrent_positions:
            self.trigger_counts["max_positions"] += 1
            return RiskCheckResult(
                approved=False,
                approved_size_usd=0.0,
                veto_reason="veto_max_concurrent_positions_reached",
            )

        target_size = requested_size_usd
        applied_caps: List[str] = []

        # 3. Liquidity Depth Constraint (order <= max_fraction_of_depth)
        if est_depth_1pct_usd > 0:
            max_depth_notional = est_depth_1pct_usd * self.config.max_fraction_of_depth
            if target_size > max_depth_notional:
                target_size = max_depth_notional
                applied_caps.append("liquidity_depth_cap")
                self.trigger_counts["liquidity_depth_cap"] += 1

        # 4. Per-coin Position Cap (notional <= max_per_coin_pct * NAV)
        current_coin_notional = self.positions.get(sym, 0.0)
        max_allowed_for_coin = (self.current_nav * self.config.max_per_coin_pct) - current_coin_notional
        if max_allowed_for_coin <= 0:
            self.trigger_counts["per_coin_cap"] += 1
            return RiskCheckResult(
                approved=False,
                approved_size_usd=0.0,
                veto_reason="veto_per_coin_cap_exceeded",
            )
        if target_size > max_allowed_for_coin:
            target_size = max_allowed_for_coin
            applied_caps.append("per_coin_cap")
            self.trigger_counts["per_coin_cap"] += 1

        # 5. Correlation-Cluster Limit
        cluster = self.get_symbol_cluster(sym)
        current_cluster_notional = sum(
            notional for s, notional in self.positions.items()
            if self.get_symbol_cluster(s) == cluster
        )
        max_cluster_allowed = (self.current_nav * self.config.max_cluster_exposure_pct) - current_cluster_notional
        if max_cluster_allowed <= 0:
            self.trigger_counts["cluster_limit"] += 1
            return RiskCheckResult(
                approved=False,
                approved_size_usd=0.0,
                veto_reason=f"veto_cluster_{cluster}_cap_exceeded",
            )
        if target_size > max_cluster_allowed:
            target_size = max_cluster_allowed
            applied_caps.append("cluster_limit")
            self.trigger_counts["cluster_limit"] += 1

        # 6. Total Portfolio Exposure Cap
        current_total_exposure = sum(self.positions.values())
        max_total_allowed = (self.current_nav * self.config.max_total_exposure_pct) - current_total_exposure
        if max_total_allowed <= 0:
            self.trigger_counts["max_total_exposure"] += 1
            return RiskCheckResult(
                approved=False,
                approved_size_usd=0.0,
                veto_reason="veto_total_exposure_cap_exceeded",
            )
        if target_size > max_total_allowed:
            target_size = max_total_allowed
            applied_caps.append("max_total_exposure")
            self.trigger_counts["max_total_exposure"] += 1

        # 7. Minimum Notional Check
        if target_size < self.config.min_notional_usd:
            self.trigger_counts["min_notional_fail"] += 1
            return RiskCheckResult(
                approved=False,
                approved_size_usd=0.0,
                veto_reason="veto_below_min_notional",
            )

        return RiskCheckResult(
            approved=True,
            approved_size_usd=round(target_size, 2),
            veto_reason=None,
            applied_caps=applied_caps,
        )

    def record_fill(self, symbol: str, side: str, notional_usd: float) -> None:
        """Updates internal position state upon fill confirmation."""
        sym = symbol.upper()
        side_clean = side.upper()
        if side_clean == "BUY":
            self.positions[sym] = self.positions.get(sym, 0.0) + notional_usd
        elif side_clean == "SELL":
            existing = self.positions.get(sym, 0.0)
            if existing <= notional_usd:
                self.positions.pop(sym, None)
            else:
                self.positions[sym] = existing - notional_usd

    def get_trigger_report(self) -> Dict[str, Any]:
        """Returns structured summary of portfolio risk limit firings."""
        return {
            "initial_nav": self.initial_nav,
            "current_nav": round(self.current_nav, 2),
            "peak_nav": round(self.peak_nav, 2),
            "drawdown_halt_active": self.drawdown_halt_active,
            "daily_loss_halt_active": self.daily_loss_halt_active,
            "active_positions_count": len(self.positions),
            "active_positions": self.positions,
            "trigger_counts": self.trigger_counts,
        }
