"""Exchange-side stop handling: offline fills are booked and missing stops are repaired."""
from unittest.mock import MagicMock

from cryptoscope.execution.binance_testnet import BinanceClientError
from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.tests.exchange_fixtures import symbol_info, with_fees


def make_bot(tmp_path):
    bot = ExecutionBot(EventBus(), mode="TESTNET", db_path=str(tmp_path / "execution.db"))
    bot.binance_client = MagicMock()
    bot.binance_client.get_symbol_info.side_effect = symbol_info
    return bot


def position(stop_order_id="11"):
    return dict(symbol="BTCUSDT", side="BUY", quantity=0.01, entry_price=100.0, stop_price=95.0,
                target_price=110.0, stop_order_id=stop_order_id, mode="TESTNET")


def stop_order(status, executed="0", quote="0", order_id=11):
    base = dict(orderId=order_id, symbol="BTCUSDT", side="SELL", type="STOP_LOSS", status=status,
                origQty="0.01", executedQty=executed, cummulativeQuoteQty=quote)
    return with_fees(base) if float(executed) else base


def test_stop_filled_while_offline_is_booked_and_position_closed(tmp_path):
    bot = make_bot(tmp_path)
    pos = position()
    bot.active_positions["BTCUSDT"] = pos
    bot._save_position_db(pos)
    bot.binance_client.get_order.return_value = stop_order("FILLED", executed="0.01", quote="0.95")
    bot.reconcile_testnet_positions()
    assert "BTCUSDT" not in bot.active_positions
    assert not bot.halt_state.snapshot()["halted"]
    bot.binance_client.create_order.assert_not_called()


def test_cancelled_stop_is_replaced_when_price_is_above_stop(tmp_path):
    bot = make_bot(tmp_path)
    pos = position()
    bot.active_positions["BTCUSDT"] = pos
    bot._save_position_db(pos)
    bot.binance_client.get_order.return_value = stop_order("CANCELED")
    bot.binance_client.get_open_orders.return_value = []
    bot.binance_client.get_ticker_price.return_value = 105.0
    bot.binance_client.create_order.return_value = dict(orderId=77, symbol="BTCUSDT", side="SELL", status="NEW", origQty="0.01")
    bot.reconcile_testnet_positions()
    call = bot.binance_client.create_order.call_args.kwargs
    assert call["side"] == "SELL" and call["order_type"] == "STOP_LOSS" and call["stop_price"] == 95.0
    assert bot.active_positions["BTCUSDT"]["stop_order_id"] == "77"
    assert bot.binance_client.create_order.call_count == 1


def test_cancelled_stop_with_price_through_stop_closes_at_market(tmp_path):
    bot = make_bot(tmp_path)
    pos = position()
    bot.active_positions["BTCUSDT"] = pos
    bot._save_position_db(pos)
    bot.binance_client.get_order.return_value = stop_order("CANCELED")
    bot.binance_client.get_open_orders.return_value = []
    bot.binance_client.get_ticker_price.return_value = 90.0
    bot.binance_client.create_order.return_value = with_fees(
        dict(orderId=5, symbol="BTCUSDT", side="SELL", type="MARKET", status="FILLED", executedQty="0.01", cummulativeQuoteQty="0.9"))
    bot.reconcile_testnet_positions()
    call = bot.binance_client.create_order.call_args.kwargs
    assert call["order_type"] == "MARKET" and call["side"] == "SELL"
    assert "BTCUSDT" not in bot.active_positions


def test_existing_owned_stop_is_adopted_not_duplicated(tmp_path):
    bot = make_bot(tmp_path)
    pos = position(stop_order_id=None)
    bot.active_positions["BTCUSDT"] = pos
    bot._save_position_db(pos)
    bot.binance_client.get_open_orders.return_value = [
        dict(orderId=88, side="SELL", type="STOP_LOSS", clientOrderId="stop_abc", origQty="0.01")]
    bot.reconcile_testnet_positions()
    assert bot.active_positions["BTCUSDT"]["stop_order_id"] == "88"
    bot.binance_client.create_order.assert_not_called()


def test_repair_is_rate_limited_and_halts_when_it_keeps_failing(tmp_path):
    bot = make_bot(tmp_path)
    pos = position(stop_order_id=None)
    bot.active_positions["BTCUSDT"] = pos
    bot._save_position_db(pos)
    bot.binance_client.get_open_orders.return_value = []
    bot.binance_client.get_ticker_price.return_value = 105.0
    bot.binance_client.create_order.side_effect = BinanceClientError("down")
    bot.binance_client.get_order.side_effect = BinanceClientError("down")
    for _ in range(5):
        bot.reconcile_testnet_positions()
    assert bot.binance_client.create_order.call_count == 3  # 4th and 5th blocked by the limiter
    assert bot.halt_state.snapshot()["halted"]
    assert "BTCUSDT" in bot.active_positions
