"""Tests for TelegramGateway: authentication whitelist, safety invariants, and offline fallback.

A1 security invariants tested:
- is_authorized() checks BOTH chat_id AND user_id
- After /kill, Telegram /resume is ALWAYS rejected regardless of args/password
- Telegram cannot change modes, risk limits, or resume after /kill
- Group chat (different chat_id type) is rejected
- Unauthorised sender rejected
- Confirmation that BOTH chat ID and user ID are checked
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from telegram import Chat, Message, Update, User
from cryptoscope.telegram.gateway import TelegramGateway


@pytest.fixture(autouse=True)
def clean_telegram_env(monkeypatch):
    """Ensure tests in this module run hermetically without leaking ambient environment variables."""
    monkeypatch.setenv("TELEGRAM_OWNER_USER_ID", '12345')
    monkeypatch.delenv("TELEGRAM_OWNER_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)


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


# ---------------------------------------------------------------------------
# A1.2  — whitelist tests (chat_id only, no user_id configured)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# A1.2  — BOTH chat_id AND user_id are checked
# ---------------------------------------------------------------------------

def test_both_chat_id_and_user_id_checked():
    """When TELEGRAM_OWNER_USER_ID is configured, is_authorized must reject any
    message whose user_id does not match, even if the chat_id matches."""
    gateway = TelegramGateway(token="dummy_token", owner_chat_id=999888)
    gateway.owner_user_id = 7777777  # explicit user ID guard

    # Correct chat_id AND correct user_id -> PASS
    good = make_mock_update(chat_id=999888, user_id=7777777)
    assert gateway.is_authorized(good) is True

    # Correct chat_id but WRONG user_id -> FAIL
    wrong_user = make_mock_update(chat_id=999888, user_id=1111111)
    assert gateway.is_authorized(wrong_user) is False

    # Wrong chat_id -> FAIL (doesn't matter what user_id is)
    wrong_chat = make_mock_update(chat_id=111222, user_id=7777777)
    assert gateway.is_authorized(wrong_chat) is False


def test_group_chat_different_chat_id_rejected():
    """A message arriving in a group (different chat_id) must be rejected,
    even if the effective_user.id matches the owner user ID."""
    GROUP_CHAT_ID = -100123456789  # group chats use negative IDs in Telegram
    OWNER_CHAT_ID = 999888
    OWNER_USER_ID = 7777777

    gateway = TelegramGateway(token="dummy_token", owner_chat_id=OWNER_CHAT_ID)
    gateway.owner_user_id = OWNER_USER_ID

    # Group chat: chat_id is the group, user_id is the owner
    group_update = make_mock_update(chat_id=GROUP_CHAT_ID, user_id=OWNER_USER_ID)
    assert gateway.is_authorized(group_update) is False


def test_no_owner_chat_id_configured_denies_all():
    """If OWNER_CHAT_ID is not configured, every request must be denied."""
    gateway = TelegramGateway(token="dummy_token", owner_chat_id=None)
    update = make_mock_update(chat_id=999888, user_id=7777777)
    assert gateway.is_authorized(update) is False


def test_missing_owner_user_denies_even_matching_chat():
    gateway = TelegramGateway(token='fixture-token', owner_chat_id=999888, owner_user_id=None)
    assert gateway.is_authorized(make_mock_update(chat_id=999888)) is False


# ---------------------------------------------------------------------------
# A1.3  — Telegram cannot change modes or risk limits
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# A1.1  — /kill then /resume: Telegram CANNOT resume, ever
# ---------------------------------------------------------------------------

def test_kill_cannot_be_resumed_via_telegram_ever():
    """Core A1 invariant: after /kill, every Telegram /resume attempt — with no
    args, with 'confirm', with a correct password, with any string — must be
    REJECTED and the kill switch must stay active."""
    async def _test():
        resume_called = []

        mock_strat = MagicMock()
        mock_strat.paused = False

        def _pause(reason=""):
            mock_strat.paused = True

        def _resume():
            mock_strat.paused = False
            resume_called.append(True)

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
        # Set a known admin password — it must NEVER be honoured from Telegram
        gateway.admin_password = "secret_admin_pass"

        # --- 1. Trigger /kill ---
        update_kill = make_mock_update(chat_id=999888, text="/kill")
        await gateway.cmd_kill(update_kill, MagicMock())

        assert gateway.kill_switch_active is True
        assert mock_strat.paused is True
        mock_exec.emergency_protect_positions.assert_called_once()

        kill_reply = update_kill.message.reply_html.call_args[0][0]
        assert "EMERGENCY KILL ACTIVATED" in kill_reply
        # The kill reply must NOT instruct the user to run /resume <password>
        assert "/resume" not in kill_reply
        assert "admin_password" not in kill_reply

        # --- 2a. /resume with no args -> BLOCKED ---
        update_no_args = make_mock_update(chat_id=999888, text="/resume")
        ctx_no_args = MagicMock()
        ctx_no_args.args = []
        await gateway.cmd_resume(update_no_args, ctx_no_args)

        assert gateway.kill_switch_active is True, "kill still active after /resume (no args)"
        assert mock_strat.paused is True
        reply_no_args = update_no_args.message.reply_html.call_args[0][0]
        assert "KILL SWITCH LOCKED" in reply_no_args
        # Must NOT hint at password-based recovery
        assert "admin_password" not in reply_no_args
        assert "/resume" not in reply_no_args

        # --- 2b. /resume confirm -> BLOCKED ---
        update_confirm = make_mock_update(chat_id=999888, text="/resume confirm")
        ctx_confirm = MagicMock()
        ctx_confirm.args = ["confirm"]
        await gateway.cmd_resume(update_confirm, ctx_confirm)

        assert gateway.kill_switch_active is True, "kill still active after /resume confirm"
        assert mock_strat.paused is True

        # --- 2c. /resume <correct_password> -> BLOCKED (not honoured) ---
        update_correct_pwd = make_mock_update(chat_id=999888, text="/resume secret_admin_pass")
        ctx_correct_pwd = MagicMock()
        ctx_correct_pwd.args = ["secret_admin_pass"]
        await gateway.cmd_resume(update_correct_pwd, ctx_correct_pwd)

        assert gateway.kill_switch_active is True, "kill still active even with correct password"
        assert mock_strat.paused is True, "strategy still paused — Telegram cannot lift kill"

        # --- 2d. /resume with arbitrary string -> BLOCKED ---
        update_arb = make_mock_update(chat_id=999888, text="/resume anything_at_all")
        ctx_arb = MagicMock()
        ctx_arb.args = ["anything_at_all"]
        await gateway.cmd_resume(update_arb, ctx_arb)

        assert gateway.kill_switch_active is True, "kill still active after arbitrary /resume arg"
        assert mock_strat.paused is True

        # --- Verify strategy.resume() was NEVER called ---
        assert resume_called == [], f"strategy.resume() must never be called from Telegram after /kill; calls={resume_called}"

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Original tests preserved
# ---------------------------------------------------------------------------

def test_pause_and_resume_with_confirmation():
    """Normal pause/resume cycle (no kill switch) works as expected."""
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


def test_kill_message_does_not_hint_at_telegram_resume():
    """/kill response must not instruct the user to /resume via Telegram."""
    async def _test():
        mock_strat = MagicMock()
        mock_strat.pause = MagicMock()
        mock_exec = MagicMock()
        mock_exec.emergency_protect_positions = AsyncMock()

        gateway = TelegramGateway(
            token="dummy_token",
            owner_chat_id=999888,
            strategy_bot=mock_strat,
            execution_bot=mock_exec,
        )
        update_kill = make_mock_update(chat_id=999888, text="/kill")
        await gateway.cmd_kill(update_kill, MagicMock())

        kill_reply = update_kill.message.reply_html.call_args[0][0]
        assert "EMERGENCY KILL ACTIVATED" in kill_reply
        assert "admin_password" not in kill_reply, (
            "kill reply must not mention admin_password -- would hint at Telegram resume path"
        )
        assert "/resume" not in kill_reply, (
            "kill reply must not instruct user to /resume via Telegram"
        )

    asyncio.run(_test())


def test_callback_confirm_resume_blocked_when_kill_active():
    """Inline 'Confirm Resume' button must be blocked when kill switch is active."""
    async def _test():
        gateway = TelegramGateway(token="dummy_token", owner_chat_id=999888, owner_user_id=999888)
        gateway.kill_switch_active = True

        query = AsyncMock()
        query.answer = AsyncMock()
        query.data = "confirm_resume"
        query.edit_message_text = AsyncMock()

        update = MagicMock(spec=Update)
        chat = MagicMock()
        chat.id = 999888
        update.effective_chat = chat
        update.effective_user = MagicMock()
        update.effective_user.id = 999888
        update.effective_user.username = "owner"
        update.callback_query = query

        # owner_user_id not set -> only chat_id check
        await gateway.handle_callback_query(update, MagicMock())

        query.edit_message_text.assert_called_once()
        blocked_text = query.edit_message_text.call_args[0][0]
        assert "RESUME BLOCKED" in blocked_text
        assert "/resume" not in blocked_text, (
            "confirm_resume callback must not hint at /resume <password>"
        )
        assert "admin_password" not in blocked_text

    asyncio.run(_test())
