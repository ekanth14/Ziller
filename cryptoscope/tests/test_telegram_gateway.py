"""Tests for TelegramGateway: authentication whitelist, safety invariants, and offline fallback."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from telegram import Chat, Message, Update, User
from cryptoscope.telegram.gateway import TelegramGateway


def make_mock_update(chat_id: int, text: str = "/status", user_id: int = 12345):
    update = MagicMock(spec=Update)
    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    user = MagicMock(spec=User)
    user.id = user_id
    user.username = "testuser"
    msg = MagicMock(spec=Message)
    msg.reply_html = AsyncMock()
    msg.text = text

    update.effective_chat = chat
    update.effective_user = user
    update.message = msg
    return update


def test_telegram_whitelist_authorization():
    gateway = TelegramGateway(token="dummy_token", owner_chat_id=999888)

    # Authorized owner update
    auth_update = make_mock_update(chat_id=999888)
    assert gateway.is_authorized(auth_update) is True

    # Unauthorized stranger update
    unauth_update = make_mock_update(chat_id=111222)
    assert gateway.is_authorized(unauth_update) is False

    # Empty/None chat update
    empty_update = MagicMock(spec=Update)
    empty_update.effective_chat = None
    assert gateway.is_authorized(empty_update) is False


def test_security_invariant_prohibits_live_mode_elevation():
    async def _test():
        gateway = TelegramGateway(token="dummy_token", owner_chat_id=999888)
        update = make_mock_update(chat_id=999888, text="/mode LIVE")
        context = MagicMock()

        await gateway.cmd_prohibited_security_action(update, context)

        update.message.reply_html.assert_called_once()
        call_arg = update.message.reply_html.call_args[0][0]
        assert "SECURITY INVARIANT VIOLATION" in call_arg
        assert "5 institutional safety gates" in call_arg

    asyncio.run(_test())


def test_pause_and_resume_with_confirmation():
    async def _test():
        mock_strat = MagicMock()
        mock_strat.paused = False
        def _pause(reason=""):
            mock_strat.paused = True
        def _resume():
            mock_strat.paused = False
        mock_strat.pause = _pause
        mock_strat.resume = _resume

        gateway = TelegramGateway(token="dummy_token", owner_chat_id=999888, strategy_bot=mock_strat)

        # 1. /pause
        update_pause = make_mock_update(chat_id=999888, text="/pause")
        await gateway.cmd_pause(update_pause, MagicMock())
        assert mock_strat.paused is True
        assert "PAUSED" in update_pause.message.reply_html.call_args[0][0]

        # 2. /resume without confirm -> prompts for confirmation
        update_res_prompt = make_mock_update(chat_id=999888, text="/resume")
        ctx = MagicMock()
        ctx.args = []
        await gateway.cmd_resume(update_res_prompt, ctx)
        assert mock_strat.paused is True  # Still paused
        assert "Confirm Resume" in update_res_prompt.message.reply_html.call_args[0][0]

        # 3. /resume confirm -> confirms and unpauses
        update_res_confirmed = make_mock_update(chat_id=999888, text="/resume confirm")
        ctx.args = ["confirm"]
        await gateway.cmd_resume(update_res_confirmed, ctx)
        assert mock_strat.paused is False
        assert "RESUMED successfully" in update_res_confirmed.message.reply_html.call_args[0][0]

    asyncio.run(_test())


def test_flatten_requires_confirmation():
    async def _test():
        mock_exec = MagicMock()
        mock_exec.flatten_all_positions = AsyncMock(return_value=3)

        gateway = TelegramGateway(token="dummy_token", owner_chat_id=999888, execution_bot=mock_exec)

        # 1. /flatten without confirm
        update_prompt = make_mock_update(chat_id=999888, text="/flatten")
        ctx = MagicMock()
        ctx.args = []
        await gateway.cmd_flatten(update_prompt, ctx)
        mock_exec.flatten_all_positions.assert_not_called()
        assert "IMMEDIATE LIQUIDATION" in update_prompt.message.reply_html.call_args[0][0]

        # 2. /flatten confirm
        update_confirmed = make_mock_update(chat_id=999888, text="/flatten confirm")
        ctx.args = ["confirm"]
        await gateway.cmd_flatten(update_confirmed, ctx)
        mock_exec.flatten_all_positions.assert_called_once()
        assert "Closed 3 positions" in update_confirmed.message.reply_html.call_args[0][0]

    asyncio.run(_test())


def test_telegram_offline_resilience():
    async def _test():
        # Gateway with no app started should raise ConnectionError when attempting to send
        gateway = TelegramGateway(token="", owner_chat_id=999888)
        with pytest.raises(ConnectionError) as exc_info:
            await gateway.send_alert("Test alert")
        assert "not active or unconfigured" in str(exc_info.value)

    asyncio.run(_test())
