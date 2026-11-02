"""Typed event models for the ZILLERS multi-bot autonomous trading system."""

from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional
import uuid


def _gen_id(prefix: str = "evt") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass
class BaseEvent:
    """Root event schema for all event bus messages."""
    event_id: str = field(default_factory=_gen_id)
    timestamp: float = field(default_factory=time.time)

    @property
    def event_type(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


@dataclass
class MarketUpdate(BaseEvent):
    """Normalized price and order-book telemetry for a specific trading pair."""
    symbol: str = "BTCUSDT"
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    volume_24h: float = 0.0
    spread_pct: float = 0.0
    candles: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "aggregated"


@dataclass
class Signal(BaseEvent):
    """Raw directional alpha signal emitted by Market Analyst or Quant bot."""
    signal_id: str = field(default_factory=lambda: _gen_id("sig"))
    strategy_id: str = "core"
    symbol: str = "BTCUSDT"
    timeframe: str = "15m"
    direction: str = "HOLD"  # 'BUY', 'SELL', 'HOLD'
    confidence: float = 0.0   # 0.0 to 1.0
    indicators: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


@dataclass
class TradeIntent(BaseEvent):
    """Proposed tactical trade submitted by StrategyBot to the Debate layer."""
    intent_id: str = field(default_factory=lambda: _gen_id("intent"))
    strategy_id: str = "ema_trend"
    symbol: str = "BTCUSDT"
    direction: str = "BUY"  # 'BUY' (long) or 'SELL' (short)
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    horizon_bars: int = 48
    reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DebateResult(BaseEvent):
    """Consensus score and multi-perspective deliberation verdict."""
    debate_id: str = field(default_factory=lambda: _gen_id("deb"))
    intent_id: str = ""
    symbol: str = "BTCUSDT"
    conviction_score: float = 0.0  # -100 to +100
    verdict: str = "REJECT"        # 'APPROVE' or 'REJECT'
    bull_thesis: str = ""
    bear_thesis: str = ""
    risk_summary: str = ""
    latency_ms: float = 0.0
    fallback_used: bool = False


@dataclass
class RiskDecision(BaseEvent):
    """Deterministic capital allocation, position sizing, and hard safety veto."""
    decision_id: str = field(default_factory=lambda: _gen_id("risk"))
    intent_id: str = ""
    symbol: str = "BTCUSDT"
    decision: str = "VETOED"  # 'APPROVED' or 'VETOED'
    approved_quantity: float = 0.0
    position_size_usd: float = 0.0
    risk_usd: float = 0.0
    kelly_fraction_used: float = 0.5
    stop_distance_pct: float = 0.0
    veto_reasons: List[str] = field(default_factory=list)
    limits_snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderRequest(BaseEvent):
    """Dispatched order specification delivered exclusively to ExecutionBot."""
    order_id: str = field(default_factory=lambda: _gen_id("ord"))
    intent_id: str = ""
    symbol: str = "BTCUSDT"
    side: str = "BUY"             # 'BUY' or 'SELL'
    order_type: str = "MARKET"    # 'MARKET', 'LIMIT', 'STOP_LOSS_LIMIT'
    quantity: float = 0.0
    price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    mode: str = "PAPER"           # 'OBSERVE', 'PAPER', 'TESTNET', 'LIVE'


@dataclass
class Fill(BaseEvent):
    """Trade execution fill confirmation report from the broker or exchange."""
    fill_id: str = field(default_factory=lambda: _gen_id("fill"))
    order_id: str = ""
    client_order_id: str = ""
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    quantity: float = 0.0
    executed_price: float = 0.0
    fee: float = 0.0
    fee_asset: str = "USDT"
    mode: str = "PAPER"
    stop_order_id: Optional[str] = None


@dataclass
class PositionClosed(BaseEvent):
    """Life-cycle completion of an open position with realized accounting."""
    position_id: str = field(default_factory=lambda: _gen_id("pos"))
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    pnl_usd: float = 0.0
    pnl_pct: float = 0.0
    duration_seconds: float = 0.0
    exit_reason: str = "TAKE_PROFIT"  # 'STOP_LOSS', 'TAKE_PROFIT', 'TIMEOUT', 'MANUAL_FLATTEN'


@dataclass
class SystemAlert(BaseEvent):
    """Health, fault detection, and administrative telemetry notification."""
    alert_id: str = field(default_factory=lambda: _gen_id("alt"))
    severity: str = "INFO"  # 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    source: str = "system"
    title: str = ""
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SupervisorHeartbeat(BaseEvent):
    """Watchdog pulse emitted periodically by SupervisorBot to ensure liveness."""
    supervisor_id: str = "supervisor-main"
    active_bots: List[str] = field(default_factory=list)
    degraded_bots: List[str] = field(default_factory=list)
    unhealthy_bots: List[str] = field(default_factory=list)
    system_uptime_seconds: float = 0.0
