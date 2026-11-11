import pytest
from core.quant.microstructure.protections import (
    CooldownPeriodGuard,
    ConsecutiveStoplossGuard,
    BracketOrderSimulator,
    BracketOrderStatus,
    OrderSide,
)

def test_cooldown_period_guard():
    guard = CooldownPeriodGuard(cooldown_bars=3, only_on_loss=True)

    # Initial state: can trade
    allowed, reason = guard.can_trade(current_bar=0)
    assert allowed is True

    # Winning trade at bar 1: no cooldown since only_on_loss is True
    guard.record_trade(pnl=50.0, bar_index=1)
    allowed, _ = guard.can_trade(current_bar=2)
    assert allowed is True

    # Losing trade at bar 3: triggers 3-bar cooldown (bars 4, 5, 6)
    guard.record_trade(pnl=-20.0, bar_index=3)
    allowed, reason = guard.can_trade(current_bar=4)
    assert allowed is False
    assert "Cooldown active" in reason

    allowed, _ = guard.can_trade(current_bar=6)
    assert allowed is False

    # At bar 7 (3 bars after 3), cooldown expires
    allowed, _ = guard.can_trade(current_bar=7)
    assert allowed is True

def test_consecutive_stoploss_guard():
    guard = ConsecutiveStoplossGuard(max_stoplosses=2, lockout_bars=10)

    assert guard.can_trade(0)[0] is True

    # First stoploss at bar 1
    guard.record_trade(pnl=-10.0, was_stoploss=True, bar_index=1)
    assert guard.consecutive_stoplosses == 1
    assert guard.can_trade(2)[0] is True

    # Second consecutive stoploss at bar 2 -> triggers lockout for 10 bars (until bar 12)
    guard.record_trade(pnl=-15.0, was_stoploss=True, bar_index=2)
    assert guard.consecutive_stoplosses == 2
    allowed, reason = guard.can_trade(3)
    assert allowed is False
    assert "Consecutive stoploss lockout" in reason

    # Still locked at bar 11
    assert guard.can_trade(11)[0] is False

    # Unlocked at bar 13
    assert guard.can_trade(13)[0] is True

    # Winning trade resets consecutive count
    guard.record_trade(pnl=100.0, was_stoploss=False, bar_index=14)
    assert guard.consecutive_stoplosses == 0

def test_bracket_order_simulator_take_profit_long():
    order = BracketOrderSimulator(
        side=OrderSide.LONG,
        entry_price=100.0,
        position_size=1.0,
        take_profit_price=110.0,
        stop_loss_price=95.0,
    )
    assert order.status == BracketOrderStatus.OPEN

    # Bar 1: inside bracket range [98, 105] -> stays open
    fill = order.update(high=105.0, low=98.0, close=103.0, bar_index=1)
    assert fill is None
    assert order.status == BracketOrderStatus.OPEN

    # Bar 2: high touches 112.0 >= TP (110.0) -> triggers TP fill
    fill = order.update(high=112.0, low=101.0, close=111.0, bar_index=2)
    assert fill is not None
    assert order.status == BracketOrderStatus.FILLED_TP
    assert fill["exit_reason"] == "take_profit"
    assert fill["exit_price"] == pytest.approx(110.0)
    assert fill["realized_pnl"] == pytest.approx(10.0)

def test_bracket_order_simulator_stop_loss_short():
    order = BracketOrderSimulator(
        side=OrderSide.SHORT,
        entry_price=100.0,
        position_size=2.0,
        take_profit_price=90.0,
        stop_loss_price=105.0,
    )
    # Price rises and breaches SL at 106.0
    fill = order.update(high=106.0, low=99.0, close=104.0, bar_index=1)
    assert fill is not None
    assert order.status == BracketOrderStatus.FILLED_SL
    assert fill["exit_reason"] == "stop_loss"
    assert fill["exit_price"] == pytest.approx(105.0)
    # Short entered at 100, exited at 105 with size 2.0 -> loss of (100 - 105) * 2 = -10.0
    assert fill["realized_pnl"] == pytest.approx(-10.0)

def test_bracket_order_simulator_trailing_stop_long():
    order = BracketOrderSimulator(
        side=OrderSide.LONG,
        entry_price=100.0,
        position_size=1.0,
        take_profit_price=150.0,
        stop_loss_price=90.0,
        trailing_stop_pct=0.05, # Trails 5% below peak
    )
    # Bar 1: rallies to 120 -> peak is 120, trailing stop raises to 120 * (1 - 0.05) = 114.0
    order.update(high=120.0, low=99.0, close=119.0, bar_index=1)
    assert order.stop_loss_price == pytest.approx(114.0)
    assert order.status == BracketOrderStatus.OPEN

    # Bar 2: price drops to 113.0 <= 114.0 -> trailing stop hit
    fill = order.update(high=118.0, low=113.0, close=114.0, bar_index=2)
    assert fill is not None
    assert order.status == BracketOrderStatus.FILLED_SL
    assert fill["exit_reason"] == "trailing_stop"
    assert fill["realized_pnl"] == pytest.approx(14.0) # bought 100, exited at 114
