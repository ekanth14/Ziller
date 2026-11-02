"""Tests for JournalBot (auditing & analytics) and NotifierBot (alerting & offline spool)."""

import asyncio
from pathlib import Path
import tempfile
import time
from typing import List

from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import (
    DebateResult,
    Fill,
    OrderRequest,
    PositionClosed,
    RiskDecision,
    Signal,
    SystemAlert,
    TradeIntent,
)
from cryptoscope.orchestrator.bots.journal_bot import JournalBot
from cryptoscope.orchestrator.bots.notifier_bot import NotifierBot


def test_journal_bot_auditing_and_analytics():
    async def _test():
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "test_journal.db")
            bus = EventBus()
            journal = JournalBot(bus, db_path=db_path)
            await journal.start()

            now = time.time()
            # 1. Log Signal
            await bus.publish(Signal(
                timestamp=now,
                symbol="BTCUSDT",
                direction="BUY",
                confidence=0.88,
                reasons=["EMA cross 9/21 golden cross"],
                strategy_id="analyst_bot"
            ))

            # 2. Log TradeIntent
            await bus.publish(TradeIntent(
                intent_id="intent_101",
                timestamp=now,
                symbol="BTCUSDT",
                direction="BUY",
                entry_price=65000.0,
                stop_loss=63500.0,
                take_profit=68000.0,
                strategy_id="Trend_EMA"
            ))

            # 3. Log DebateResult
            await bus.publish(DebateResult(
                intent_id="intent_101",
                timestamp=now,
                symbol="BTCUSDT",
                verdict="APPROVED",
                conviction_score=82.5,
                bull_thesis="Strong volume confirmation"
            ))

            # 4. Log RiskDecision
            await bus.publish(RiskDecision(
                intent_id="intent_101",
                timestamp=now,
                symbol="BTCUSDT",
                decision="APPROVED",
                approved_quantity=0.1,
                position_size_usd=6500.0,
                stop_distance_pct=2.31
            ))

            # 5. Log OrderRequest & Fill
            await bus.publish(OrderRequest(
                order_id="ord_101",
                intent_id="intent_101",
                symbol="BTCUSDT",
                side="BUY",
                order_type="MARKET",
                quantity=0.1,
                price=65000.0,
                stop_price=63500.0
            ))

            await bus.publish(Fill(
                fill_id="fill_101",
                order_id="ord_101",
                symbol="BTCUSDT",
                side="BUY",
                executed_price=65010.0,
                quantity=0.1,
                fee=6.50,
                stop_order_id="stop_ord_101"
            ))

            # 6. Log two closed positions (1 Win, 1 Loss)
            await bus.publish(PositionClosed(
                timestamp=now + 100,
                symbol="BTCUSDT",
                side="BUY",
                entry_price=65010.0,
                exit_price=68000.0,
                quantity=0.1,
                pnl_usd=299.0,
                pnl_pct=4.60,
                duration_seconds=3600.0,
                exit_reason="TAKE_PROFIT"
            ))

            await bus.publish(PositionClosed(
                timestamp=now + 200,
                symbol="ETHUSDT",
                side="BUY",
                entry_price=3500.0,
                exit_price=3400.0,
                quantity=1.0,
                pnl_usd=-100.0,
                pnl_pct=-2.86,
                duration_seconds=1800.0,
                exit_reason="STOP_LOSS"
            ))

            await asyncio.sleep(0.1)

            # Evaluate Metrics
            metrics = journal.get_performance_metrics(window_days=1)
            assert metrics["total_trades"] == 2
            assert metrics["winning_trades"] == 1
            assert metrics["losing_trades"] == 1
            assert metrics["win_rate_pct"] == 50.0
            assert metrics["net_pnl_usd"] == 199.0
            assert metrics["profit_factor"] == 2.99
            # Expectancy: (0.5 * 299) - (0.5 * 100) = 149.5 - 50 = 99.5
            assert metrics["expectancy_usd"] == 99.5
            assert metrics["total_fees_usd"] == 6.50

            report = journal.generate_report(period="daily")
            assert "ZILLERS DAILY PERFORMANCE REPORT" in report
            assert "+$199.00" in report
            assert "50.0%" in report

            await journal.stop()
            await bus.stop()

    asyncio.run(_test())


def test_notifier_bot_formatting_and_offline_spool():
    async def _test():
        bus = EventBus()
        delivered_messages: List[str] = []

        # Simulated dispatch callback
        async def mock_telegram_dispatch(text: str):
            delivered_messages.append(text)

        notifier = NotifierBot(
            bus=bus,
            rate_limit_per_minute=60,
            dispatch_callback=mock_telegram_dispatch
        )
        await notifier.start()

        # Cache intent and debate
        intent = TradeIntent(
            intent_id="intent_n1",
            symbol="SOLUSDT",
            direction="BUY",
            entry_price=150.0,
            stop_loss=142.5,
            take_profit=165.0,
            strategy_id="VolatilityBreakout"
        )
        await bus.publish(intent)

        debate = DebateResult(
            intent_id="intent_n1",
            symbol="SOLUSDT",
            verdict="APPROVED",
            conviction_score=85.0,
            bull_thesis="Institutional volume and low volatility squeeze"
        )
        await bus.publish(debate)

        # Trigger Fill -> Should emit rich entry alert
        fill = Fill(
            fill_id="fill_sol",
            order_id="ord_sol",
            symbol="SOLUSDT",
            side="BUY",
            executed_price=150.2,
            quantity=20.0,
            fee=3.0,
            stop_order_id="stop_sol"
        )
        await bus.publish(fill)

        await asyncio.sleep(0.05)
        assert len(delivered_messages) >= 1
        entry_alert = delivered_messages[0]
        assert "EXECUTION ENTRY: SOLUSDT" in entry_alert
        assert "$150.2000" in entry_alert
        assert "VolatilityBreakout" in entry_alert
        assert "Exchange Gated" in entry_alert
        assert "Institutional volume" in entry_alert

        # Trigger PositionClosed -> Should emit exit alert
        closed = PositionClosed(
            symbol="SOLUSDT",
            side="BUY",
            entry_price=150.2,
            exit_price=165.0,
            quantity=20.0,
            pnl_usd=296.0,
            pnl_pct=9.85,
            duration_seconds=7200.0,
            exit_reason="TAKE_PROFIT"
        )
        await bus.publish(closed)
        await asyncio.sleep(0.05)

        assert len(delivered_messages) >= 2
        exit_alert = delivered_messages[1]
        assert "POSITION CLOSED: SOLUSDT (TAKE_PROFIT)" in exit_alert
        assert "+$296.00" in exit_alert
        assert "120m 0s" in exit_alert

        # Test Offline Spooling when Telegram is unreachable
        async def failing_dispatch(text: str):
            raise ConnectionError("Telegram API unreachable / timeout")

        notifier.dispatch_callback = failing_dispatch

        # Dispatch critical system alert
        alert = SystemAlert(
            severity="CRITICAL",
            source="supervisor_bot",
            title="Feed Disconnected",
            message="Binance websocket disconnected, retrying..."
        )
        await bus.publish(alert)
        await asyncio.sleep(0.1)

        # Alert should fail delivery and be stored in offline_spool
        assert len(notifier.offline_spool) >= 1
        assert "Feed Disconnected" in notifier.offline_spool[0].text

        await notifier.stop()
        await bus.stop()

    asyncio.run(_test())
