"""Unit and integration tests for Binance Spot Testnet execution and safety controls."""

import asyncio
import os
import tempfile
import time
from unittest.mock import MagicMock, patch
import pytest

from cryptoscope.execution.binance_testnet import (
    BinanceTestnetClient,
    BinanceClientError,
    BinanceAuthError,
    BinanceOrderFilterError,
    BinanceInsufficientBalanceError,
)
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import (
    Fill,
    OrderRequest,
    PositionClosed,
    RiskDecision,
    SystemAlert,
    TradeIntent,
)
from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot


def test_binance_testnet_live_ping_and_server_time():
    """Real network ping and time synchronization test against testnet.binance.vision."""
    client = BinanceTestnetClient()
    # Ping
    assert client.ping() is True
    # Server time
    st = client.get_server_time()
    assert isinstance(st, int)
    assert st > 1700000000000  # Reasonable epoch timestamp in ms
    # Time delta should be within 10 seconds of local time
    local_ms = int(time.time() * 1000)
    assert abs(st - local_ms) < 10000


def test_binance_testnet_live_symbol_info_and_filters():
    """Real network fetch of exchange filters (LOT_SIZE, MIN_NOTIONAL) on BTCUSDT."""
    client = BinanceTestnetClient()
    sym_info = client.get_symbol_info("BTCUSDT")
    assert sym_info["symbol"] == "BTCUSDT"
    assert sym_info["status"] == "TRADING"

    filters = {f["filterType"]: f for f in sym_info["filters"]}
    assert "LOT_SIZE" in filters
    assert float(filters["LOT_SIZE"]["minQty"]) > 0
    assert "PRICE_FILTER" in filters
    assert float(filters["PRICE_FILTER"]["tickSize"]) > 0
    # Must have NOTIONAL or MIN_NOTIONAL filter
    assert "NOTIONAL" in filters or "MIN_NOTIONAL" in filters


def test_binance_testnet_live_ticker_price():
    """Real network fetch of live price quote on BTCUSDT."""
    client = BinanceTestnetClient()
    price = client.get_ticker_price("BTCUSDT")
    assert isinstance(price, float)
    assert price > 1000.0  # BTC price is well above $1,000


def test_binance_testnet_auth_failure_semantics():
    """Verify that invalid/unauthorized keys raise BinanceAuthError without secret leakage."""
    client = BinanceTestnetClient(
        api_key="1cBpRwd0gFW3UWIveqYupflo7o19bQRJZim90ppezrqswH0GHCkHDU99L1xgHrPe",
        api_secret="dummy_secret_for_test",
    )
    assert client.masked_api_key == "1cBp...HrPe"
    assert "dummy_secret" not in repr(client)

    with pytest.raises(BinanceAuthError) as exc_info:
        client.get_account()

    err_str = str(exc_info.value)
    assert "Authentication failed" in err_str
    # Verify the secret is never present in the error string
    assert "dummy_secret" not in err_str


def test_binance_testnet_client_request_construction():
    """Verify URL and parameter construction for orders."""
    client = BinanceTestnetClient(api_key="test_key_12345678", api_secret="test_secret_12345678")

    captured_requests = []

    def mock_request(method, path, params=None, signed=False):
        captured_requests.append({
            "method": method,
            "path": path,
            "params": params,
            "signed": signed,
        })
        return {
            "orderId": 987654321,
            "symbol": params.get("symbol"),
            "status": "FILLED",
            "executedQty": params.get("quantity"),
            "cummulativeQuoteQty": "500.00",
        }

    client._request = mock_request

    # Test market order
    res = client.create_order("BTCUSDT", "BUY", "MARKET", 0.005, client_order_id="cli_1")
    assert res["orderId"] == 987654321
    assert captured_requests[0]["params"]["symbol"] == "BTCUSDT"
    assert captured_requests[0]["params"]["side"] == "BUY"
    assert captured_requests[0]["params"]["type"] == "MARKET"
    assert captured_requests[0]["signed"] is True

    # Test stop loss limit order
    client.create_order(
        "BTCUSDT", "SELL", "STOP_LOSS_LIMIT", 0.005,
        price=60000.0, stop_price=60500.0, client_order_id="stop_1"
    )
    assert captured_requests[1]["params"]["type"] == "STOP_LOSS_LIMIT"
    assert captured_requests[1]["params"]["stopPrice"] == "60500.00"
    assert captured_requests[1]["params"]["price"] == "60000.00"


def test_execution_bot_testnet_order_flow_and_exchange_stop_loss():
    """Verify ExecutionBot in TESTNET mode registers entry and exchange-level protective stop-loss."""
    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = os.path.join(tmpdir, "testnet_exec.db")
            bus = EventBus()
            bot = ExecutionBot(
                bus=bus,
                name="exec_testnet",
                mode="TESTNET",
                db_path=db_file,
                exchange_api_key="mock_testnet_key",
                exchange_api_secret="mock_testnet_secret",
            )

            # Mock the BinanceTestnetClient order creation
            created_orders = []

            def mock_create_order(symbol, side, order_type, quantity, price=None, stop_price=None, client_order_id=None, **kwargs):
                ord_id = len(created_orders) + 1001
                rec = {
                    "orderId": ord_id,
                    "symbol": symbol,
                    "side": side,
                    "type": order_type,
                    "quantity": quantity,
                    "price": price,
                    "stop_price": stop_price,
                    "executedQty": str(quantity),
                    "cummulativeQuoteQty": str(quantity * 65000.0),
                    "status": "FILLED" if order_type == "MARKET" else "NEW",
                }
                created_orders.append(rec)
                return rec

            bot.binance_client.create_order = mock_create_order

            # Cache TradeIntent
            intent = TradeIntent(
                intent_id="intent_t1",
                strategy_id="volatility_breakout",
                symbol="BTCUSDT",
                direction="BUY",
                entry_price=65000.0,
                stop_loss=63500.0,
                take_profit=68000.0,
                horizon_bars=48,
                reasons=["Breakout signal"],
            )
            await bot.on_event(intent)

            # Emit Approved RiskDecision
            emitted_events = []
            async def mock_emit(evt):
                emitted_events.append(evt)
            bot.emit = mock_emit

            decision = RiskDecision(
                intent_id="intent_t1",
                symbol="BTCUSDT",
                decision="APPROVED",
                approved_quantity=0.015,
                position_size_usd=975.0,
                risk_usd=50.0,
                stop_distance_pct=2.31,
            )
            await bot.on_event(decision)

            # Verify entry order + exchange stop-loss order placed
            assert len(created_orders) == 2
            entry_ord = created_orders[0]
            stop_ord = created_orders[1]

            # Entry order check
            assert entry_ord["side"] == "BUY"
            assert entry_ord["type"] == "MARKET"
            assert entry_ord["quantity"] == 0.015

            # Exchange stop-loss order check
            assert stop_ord["side"] == "SELL"
            assert stop_ord["type"] == "STOP_LOSS_LIMIT"
            assert stop_ord["stop_price"] == 63500.0
            assert stop_ord["quantity"] == 0.015

            # Verify position stored in active positions and SQLite DB with exchange stop_order_id
            assert "BTCUSDT" in bot.active_positions
            assert bot.active_positions["BTCUSDT"]["stop_order_id"] == str(stop_ord["orderId"])

            # Verify emitted events: OrderRequest, Fill
            fills = [e for e in emitted_events if isinstance(e, Fill)]
            assert len(fills) == 1
            assert fills[0].stop_order_id == str(stop_ord["orderId"])
            assert fills[0].mode == "TESTNET"

    asyncio.run(_run())


def test_execution_bot_testnet_flatten_cancels_stop_and_closes():
    """Verify flatten_all_positions on testnet cancels exchange stop and market closes."""
    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = os.path.join(tmpdir, "testnet_exec.db")
            bus = EventBus()
            bot = ExecutionBot(
                bus=bus,
                name="exec_testnet",
                mode="TESTNET",
                db_path=db_file,
            )

            bot.active_positions["BTCUSDT"] = {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.02,
                "entry_price": 65000.0,
                "stop_price": 63500.0,
                "target_price": 68000.0,
                "stop_order_id": "1002",
            }

            canceled_orders = []
            market_orders = []

            bot.binance_client.cancel_order = lambda symbol, order_id=None, **kw: canceled_orders.append((symbol, order_id))
            bot.binance_client.create_order = lambda symbol, side, order_type, quantity, **kw: market_orders.append((symbol, side, order_type, quantity))

            count = await bot.flatten_all_positions("Operator test flatten")
            assert count == 1
            assert len(canceled_orders) == 1
            assert canceled_orders[0] == ("BTCUSDT", 1002)

            assert len(market_orders) == 1
            assert market_orders[0] == ("BTCUSDT", "SELL", "MARKET", 0.02)
            assert len(bot.active_positions) == 0

    asyncio.run(_run())


def test_execution_bot_testnet_rejection_fails_closed():
    """Verify that when Binance testnet rejects an order, ExecutionBot fails closed with zero lingering position."""
    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = os.path.join(tmpdir, "testnet_exec.db")
            bus = EventBus()
            bot = ExecutionBot(
                bus=bus,
                name="exec_testnet",
                mode="TESTNET",
                db_path=db_file,
            )

            def mock_reject(*args, **kwargs):
                raise BinanceOrderFilterError("Filter failure: MIN_NOTIONAL (code=-1013)", code=-1013)

            bot.binance_client.create_order = mock_reject

            intent = TradeIntent(
                intent_id="intent_t2",
                strategy_id="volatility_breakout",
                symbol="BTCUSDT",
                direction="BUY",
                entry_price=65000.0,
                stop_loss=63500.0,
                take_profit=68000.0,
                horizon_bars=48,
                reasons=["Breakout signal"],
            )
            await bot.on_event(intent)

            emitted_alerts = []
            async def mock_emit(evt):
                if isinstance(evt, SystemAlert):
                    emitted_alerts.append(evt)
            bot.emit = mock_emit

            decision = RiskDecision(
                intent_id="intent_t2",
                symbol="BTCUSDT",
                decision="APPROVED",
                approved_quantity=0.00001,
                position_size_usd=0.65,
                risk_usd=1.0,
                stop_distance_pct=2.31,
            )
            await bot.on_event(decision)

            # Fails closed: zero active positions
            assert len(bot.active_positions) == 0
            # Emitted ERROR SystemAlert
            assert len(emitted_alerts) == 1
            assert emitted_alerts[0].severity == "ERROR"
            assert "MIN_NOTIONAL" in emitted_alerts[0].message

    asyncio.run(_run())
