"""Trading Strategy Protections and Bracket Execution Simulator.

Implements execution circuit breakers, cooldown guards, consecutive stoploss guards,
and bracket order (OCO + Trailing Stop) fill simulation inspired by freqtrade and nautilus_trader.
"""

from enum import Enum
from typing import Any, Mapping


class OrderSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    BUY = "buy"
    SELL = "sell"


class BracketOrderStatus(str, Enum):
    OPEN = "open"
    FILLED_TP = "filled_tp"
    FILLED_SL = "filled_sl"
    CANCELLED = "cancelled"


class CooldownPeriodGuard:
    """Enforces an M-bar cooling off period following a losing trade or exit."""

    def __init__(self, cooldown_bars: int = 5, only_on_loss: bool = True) -> None:
        self.cooldown_bars = max(1, int(cooldown_bars))
        self.only_on_loss = only_on_loss
        self._last_trigger_bar: int | None = None

    def record_trade(self, pnl: float, bar_index: int) -> None:
        """Record trade result and activate cooldown if conditions met."""
        if not self.only_on_loss or pnl < 0.0:
            self._last_trigger_bar = int(bar_index)

    def is_in_cooldown(self, current_bar: int) -> bool:
        """Check whether trading is currently prohibited due to cooldown."""
        if self._last_trigger_bar is None:
            return False
        return (int(current_bar) - self._last_trigger_bar) <= self.cooldown_bars

    def can_trade(self, current_bar: int) -> tuple[bool, str]:
        """Return (allowed, reason) for trade entry gate."""
        if self.is_in_cooldown(current_bar):
            remaining = self.cooldown_bars - (int(current_bar) - (self._last_trigger_bar or 0)) + 1
            return False, f"Cooldown active ({remaining} bars remaining)."
        return True, "Trading permitted."

    def reset(self) -> None:
        self._last_trigger_bar = None


class ConsecutiveStoplossGuard:
    """Pauses trading after N consecutive stoploss executions."""

    def __init__(self, max_stoplosses: int = 3, lockout_bars: int = 20) -> None:
        self.max_stoplosses = max(1, int(max_stoplosses))
        self.lockout_bars = max(1, int(lockout_bars))
        self._consecutive_stoplosses: int = 0
        self._lockout_until_bar: int = -1

    @property
    def consecutive_stoplosses(self) -> int:
        return self._consecutive_stoplosses

    def record_trade(self, pnl: float, was_stoploss: bool, bar_index: int) -> None:
        """Record trade outcome and update consecutive stoploss counter."""
        if was_stoploss or pnl < 0.0:
            self._consecutive_stoplosses += 1
            if self._consecutive_stoplosses >= self.max_stoplosses:
                self._lockout_until_bar = int(bar_index) + self.lockout_bars
        else:
            self._consecutive_stoplosses = 0

    def is_locked(self, current_bar: int) -> bool:
        """Check if lockout is currently active."""
        return int(current_bar) <= self._lockout_until_bar

    def can_trade(self, current_bar: int) -> tuple[bool, str]:
        """Check if trading is permitted."""
        if self.is_locked(current_bar):
            remaining = self._lockout_until_bar - int(current_bar) + 1
            return False, f"Consecutive stoploss lockout ({remaining} bars remaining)."
        return True, "Trading permitted."

    def reset(self) -> None:
        self._consecutive_stoplosses = 0
        self._lockout_until_bar = -1


class BracketOrderSimulator:
    """Models Bracket Orders with One-Cancels-the-Other (OCO) Take-Profit & Trailing Stoploss."""

    def __init__(
        self,
        side: OrderSide | str,
        entry_price: float,
        position_size: float = 1.0,
        take_profit_price: float | None = None,
        stop_loss_price: float | None = None,
        trailing_stop_pct: float | None = None,
        slippage_pct: float = 0.0,
    ) -> None:
        if isinstance(side, str):
            side = OrderSide(side.lower())
        self.side = side
        self.entry_price = float(entry_price)
        self.position_size = float(position_size)
        self.take_profit_price = float(take_profit_price) if take_profit_price is not None else None
        self.stop_loss_price = float(stop_loss_price) if stop_loss_price is not None else None
        self.trailing_stop_pct = float(trailing_stop_pct) if trailing_stop_pct is not None else None
        self.slippage_pct = float(slippage_pct)

        self.status = BracketOrderStatus.OPEN
        self.peak_price: float = self.entry_price
        self.trough_price: float = self.entry_price
        self.trailing_activated: bool = False

    def update(
        self,
        high: float,
        low: float,
        close: float,
        bar_index: int,
    ) -> dict[str, Any] | None:
        """Evaluate incoming price bar against bracket levels.

        Returns fill event dictionary if an exit was triggered, else None.
        """
        if self.status != BracketOrderStatus.OPEN:
            return None

        is_long = self.side in (OrderSide.LONG, OrderSide.BUY)

        # 1. Check existing bracket exits against current bar prices (strictly causal)
        if is_long:
            hit_sl = self.stop_loss_price is not None and low <= self.stop_loss_price
            hit_tp = self.take_profit_price is not None and high >= self.take_profit_price

            if hit_sl:
                self.status = BracketOrderStatus.FILLED_SL
                exit_price = (self.stop_loss_price or low) * (1.0 - self.slippage_pct)
                reason = "trailing_stop" if self.trailing_activated else "stop_loss"
                pnl = (exit_price - self.entry_price) * self.position_size
                return {
                    "bar_index": bar_index,
                    "status": self.status.value,
                    "exit_reason": reason,
                    "exit_price": exit_price,
                    "realized_pnl": pnl,
                    "return_pct": (exit_price / self.entry_price - 1.0) * 100.0,
                }
            elif hit_tp:
                self.status = BracketOrderStatus.FILLED_TP
                exit_price = (self.take_profit_price or high) * (1.0 - self.slippage_pct)
                pnl = (exit_price - self.entry_price) * self.position_size
                return {
                    "bar_index": bar_index,
                    "status": self.status.value,
                    "exit_reason": "take_profit",
                    "exit_price": exit_price,
                    "realized_pnl": pnl,
                    "return_pct": (exit_price / self.entry_price - 1.0) * 100.0,
                }

            # 2. Update Trailing Stop for subsequent bars (causal ratcheting)
            if self.trailing_stop_pct is not None and self.trailing_stop_pct > 0.0:
                if high > self.peak_price:
                    self.peak_price = high
                    trail_level = self.peak_price * (1.0 - self.trailing_stop_pct)
                    if self.stop_loss_price is None or trail_level > self.stop_loss_price:
                        self.stop_loss_price = trail_level
                        self.trailing_activated = True
        else:
            # Short position
            hit_sl = self.stop_loss_price is not None and high >= self.stop_loss_price
            hit_tp = self.take_profit_price is not None and low <= self.take_profit_price

            if hit_sl:
                self.status = BracketOrderStatus.FILLED_SL
                exit_price = (self.stop_loss_price or high) * (1.0 + self.slippage_pct)
                reason = "trailing_stop" if self.trailing_activated else "stop_loss"
                pnl = (self.entry_price - exit_price) * self.position_size
                return {
                    "bar_index": bar_index,
                    "status": self.status.value,
                    "exit_reason": reason,
                    "exit_price": exit_price,
                    "realized_pnl": pnl,
                    "return_pct": (1.0 - exit_price / self.entry_price) * 100.0,
                }
            elif hit_tp:
                self.status = BracketOrderStatus.FILLED_TP
                exit_price = (self.take_profit_price or low) * (1.0 + self.slippage_pct)
                pnl = (self.entry_price - exit_price) * self.position_size
                return {
                    "bar_index": bar_index,
                    "status": self.status.value,
                    "exit_reason": "take_profit",
                    "exit_price": exit_price,
                    "realized_pnl": pnl,
                    "return_pct": (1.0 - exit_price / self.entry_price) * 100.0,
                }

            # Update trailing stop for shorts
            if self.trailing_stop_pct is not None and self.trailing_stop_pct > 0.0:
                if low < self.trough_price:
                    self.trough_price = low
                    trail_level = self.trough_price * (1.0 + self.trailing_stop_pct)
                    if self.stop_loss_price is None or trail_level < self.stop_loss_price:
                        self.stop_loss_price = trail_level
                        self.trailing_activated = True

        return None
