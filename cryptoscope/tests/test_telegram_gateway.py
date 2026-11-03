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


def test_kill_emergency_stop_requires_admin_password_to_resume():
    async def _test():
        mock_strat = MagicMock()
        mock_strat.paused = False
        def _pause(reason=""):
            mock_strat.paused = True
        def _resume():
            mock_strat.paused = False
        mock_strat.pause = _pause
        mock_strat.resume = _resume

        mock_exec = MagicMock()
        mock_exec.emergency_protect_positions = AsyncMock()

        gateway = TelegramGateway(
            token="dummy_token",
            owner_chat_id=999888,
            strategy_bot=mock_strat,
            execution_bot=mock_exec,
        )
        gateway.admin_password = "secret_admin_pass"

        # 1. Trigger /kill
        update_kill = make_mock_update(chat_id=999888, text="/kill")
        await gateway.cmd_kill(update_kill, MagicMock())

        assert gateway.kill_switch_active is True
        assert mock_strat.paused is True
        mock_exec.emergency_protect_positions.assert_called_once()
        assert "EMERGENCY KILL ACTIVATED" in update_kill.message.reply_html.call_args[0][0]

        # 2a. Try /resume without args -> prompts that kill switch is locked and requires password
        update_res_no_args = make_mock_update(chat_id=999888, text="/resume")
        ctx_no_args = MagicMock()
        ctx_no_args.args = []
        await gateway.cmd_resume(update_res_no_args, ctx_no_args)

        assert gateway.kill_switch_active is True
        assert mock_strat.paused is True
        assert "KILL SWITCH LOCKED" in update_res_no_args.message.reply_html.call_args[0][0]

        # 2b. Try /resume confirm -> rejected as invalid password
        update_res_confirm = make_mock_update(chat_id=999888, text="/resume confirm")
        ctx_confirm = MagicMock()
        ctx_confirm.args = ["confirm"]
        await gateway.cmd_resume(update_res_confirm, ctx_confirm)

        assert gateway.kill_switch_active is True
        assert mock_strat.paused is True
        assert "Authentication Failed" in update_res_confirm.message.reply_html.call_args[0][0]

        # 3. Try /resume with wrong password -> BLOCKED
        update_res_wrong = make_mock_update(chat_id=999888, text="/resume wrong_pass")
        ctx_wrong = MagicMock()
        ctx_wrong.args = ["wrong_pass"]
        await gateway.cmd_resume(update_res_wrong, ctx_wrong)

        assert gateway.kill_switch_active is True
        assert mock_strat.paused is True
        assert "Authentication Failed" in update_res_wrong.message.reply_html.call_args[0][0]

        # 4. Try /resume with correct password -> UNLOCKED and RESUMED
        update_res_correct = make_mock_update(chat_id=999888, text="/resume secret_admin_pass")
        ctx_correct = MagicMock()
        ctx_correct.args = ["secret_admin_pass"]
        await gateway.cmd_resume(update_res_correct, ctx_correct)

        assert gateway.kill_switch_active is False
        assert mock_strat.paused is False
        assert "AUTHENTICATED" in update_res_correct.message.reply_html.call_args[0][0]

    asyncio.run(_test())

