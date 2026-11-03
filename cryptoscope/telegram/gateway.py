"""Telegram Autonomous Trading Gateway.

Provides secure, whitelisted remote control and institutional alert dispatching
for the ZILLERS multi-bot autonomous trading fleet.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logger = logging.getLogger("cryptoscope.telegram.gateway")


class TelegramGateway:
    """Institutional Telegram gateway interface for ZILLERS.

    Security Policies:
    - Whitelist strict check: Only TELEGRAM_OWNER_CHAT_ID is processed; all other users are silently ignored.
    - Safety invariant: Risk limits and autonomy modes CANNOT be elevated or switched to LIVE via Telegram.
    - Destructive actions (/flatten, /resume) require explicit two-step confirmation.
    - Offline tolerance: If Telegram API is unreachable, trading proceeds unaffected and alerts buffer locally.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        owner_chat_id: Optional[int | str] = None,
        supervisor=None,
        strategy_bot=None,
        risk_bot=None,
        execution_bot=None,
        journal_bot=None,
        notifier_bot=None,
    ):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        raw_owner = owner_chat_id or os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
        try:
            self.owner_chat_id: Optional[int] = int(raw_owner) if raw_owner else None
        except ValueError:
            self.owner_chat_id = None

        self.supervisor = supervisor
        self.strategy_bot = strategy_bot
        self.risk_bot = risk_bot
        self.execution_bot = execution_bot
        self.journal_bot = journal_bot
        self.notifier_bot = notifier_bot

        self.app: Optional[Application] = None
        self._running = False
        self.kill_switch_active: bool = False
        self.admin_password: str = (
            os.environ.get("ADMIN_PASSWORD")
            or os.environ.get("ZILLERS_ADMIN_PASSWORD")
            or "admin123"
        )

    def is_authorized(self, update: Update) -> bool:
        """Check if message originated from the whitelisted owner chat ID."""
        if not self.owner_chat_id:
            logger.warning("[TelegramGateway] OWNER_CHAT_ID not configured. Denying all requests.")
            return False
        if not update.effective_chat or update.effective_chat.id != self.owner_chat_id:
            user = update.effective_user.username if update.effective_user else "unknown"
            cid = update.effective_chat.id if update.effective_chat else "unknown"
            logger.warning("[TelegramGateway] Unauthorized access attempt by %s (chat_id=%s). Silently dropped.", user, cid)
            return False
        return True

    def build_application(self) -> Optional[Application]:
        """Construct python-telegram-bot Application instance with command handlers."""
        if not self.token:
            logger.warning("[TelegramGateway] TELEGRAM_BOT_TOKEN missing. Gateway running in disabled mode.")
            return None

        app = Application.builder().token(self.token).build()

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("positions", self.cmd_positions))
        app.add_handler(CommandHandler("pnl", self.cmd_pnl))
        app.add_handler(CommandHandler("pause", self.cmd_pause))
        app.add_handler(CommandHandler("resume", self.cmd_resume))
        app.add_handler(CommandHandler("kill", self.cmd_kill))
        app.add_handler(CommandHandler("flatten", self.cmd_flatten))
        app.add_handler(CommandHandler("mode", self.cmd_prohibited_security_action))
        app.add_handler(CommandHandler("risk", self.cmd_prohibited_security_action))
        app.add_handler(CallbackQueryHandler(self.handle_callback_query))

        self.app = app
        return app

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            return
        msg = (
            "🤖 <b>ZILLERS AUTONOMOUS TRADING TERMINAL</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Owner authenticated.\n\n"
            "<b>Available Commands:</b>\n"
            "/status - Inspect micro-bot health & state\n"
            "/positions - View active working positions\n"
            "/pnl - View performance analytics & metrics\n"
            "/pause - Pause strategy signal generation\n"
            "/resume - Resume strategy execution\n"
            "/flatten - Liquidate all open positions\n"
            "/kill - Trigger emergency order cancellation\n"
            "━━━━━━━━━━━━━━━━━━━"
        )
        keyboard = [
            [
                InlineKeyboardButton("⏸️ Pause Strategy", callback_data="action_pause"),
                InlineKeyboardButton("🛑 Emergency Flatten", callback_data="req_flatten")
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="action_status"),
                InlineKeyboardButton("📈 PnL", callback_data="action_pnl")
            ]
        ]
        await update.message.reply_html(msg, reply_markup=InlineKeyboardMarkup(keyboard))

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            return
        status_text = self._format_status_text()
        await update.message.reply_html(status_text)

    def _format_status_text(self) -> str:
        lines = [
            "⚡ <b>ZILLERS FLEET HEALTH & STATUS</b>",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        mode = getattr(self.execution_bot, "mode", "PAPER") if self.execution_bot else "UNKNOWN"
        lines.append(f"🌐 <b>Autonomy Mode:</b> <code>{mode}</code>")
        
        paused = getattr(self.strategy_bot, "paused", False) if self.strategy_bot else False
        lines.append(f"🚦 <b>Trading State:</b> {'⏸️ PAUSED' if paused else '▶️ RUNNING'}")

        if self.supervisor:
            report = self.supervisor.health_report()
            lines.append(f"🤖 <b>Fleet Health:</b> {report.get('healthy_bots_count', 0)}/{report.get('total_bots_count', 0)} Healthy")
            lines.append("━━━━━━━━━━━━━━━━━━━")
            for name, details in report.get("bots", {}).items():
                icon = "🟢" if details.get("status") == "HEALTHY" else "🔴"
                lines.append(f"{icon} <b>{name}</b>: {details.get('status')} (err: {details.get('error_count', 0)})")
        else:
            lines.append("⚠️ Supervisor not linked.")

        lines.append("━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            return
        if not self.execution_bot:
            await update.message.reply_html("⚠️ ExecutionBot not attached.")
            return

        positions = self.execution_bot.active_positions
        if not positions:
            await update.message.reply_html("📭 <b>No active positions open.</b>")
            return

        lines = [
            f"💼 <b>OPEN POSITIONS ({len(positions)})</b>",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        for sym, pos in positions.items():
            side_emoji = "🟢" if pos.get("side") == "BUY" else "🔴"
            lines.append(
                f"{side_emoji} <b>{sym} ({pos.get('side')})</b>\n"
                f"  • Qty: {pos.get('quantity')}\n"
                f"  • Entry: ${pos.get('entry_price', 0.0):,.4f}\n"
                f"  • Stop: ${pos.get('stop_price', 0.0):,.4f} [Exchange Gated]\n"
                f"  • Target: ${pos.get('target_price', 0.0):,.4f}"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━")
        await update.message.reply_html("\n".join(lines))

    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            return
        if not self.journal_bot:
            await update.message.reply_html("⚠️ JournalBot not attached.")
            return

        report = self.journal_bot.generate_report(period="daily")
        await update.message.reply_html(report)

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            return
        if self.strategy_bot:
            self.strategy_bot.pause("Paused by owner via Telegram")
            keyboard = [[InlineKeyboardButton("▶️ Resume Trading", callback_data="req_resume")]]
            await update.message.reply_html(
                "⏸️ <b>Strategy signal generation PAUSED.</b>\nActive positions remain protected with existing stops.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_html("⚠️ StrategyBot not linked.")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            return
        args = context.args or []

        # If kill switch is engaged, require local admin password authentication
        if self.kill_switch_active:
            if not args:
                await update.message.reply_html(
                    "⛔ <b>KILL SWITCH LOCKED:</b> Emergency kill is active.\n"
                    "Resuming requires local admin password:\n"
                    "Usage: <code>/resume &lt;admin_password&gt;</code>"
                )
                return
            provided_pwd = args[0].strip()
            if provided_pwd != self.admin_password:
                logger.warning("[TelegramGateway] Failed resume attempt with invalid admin password.")
                await update.message.reply_html("❌ <b>Authentication Failed:</b> Invalid admin password. System remains killed.")
                return

            self.kill_switch_active = False
            if self.strategy_bot:
                self.strategy_bot.resume()
            logger.info("[TelegramGateway] Emergency kill switch cleared via authenticated admin password.")
            await update.message.reply_html("🔓 <b>AUTHENTICATED:</b> Emergency kill cleared. Strategy execution RESUMED successfully.")
            return

        if "confirm" in [a.lower() for a in args]:
            if self.strategy_bot:
                self.strategy_bot.resume()
                await update.message.reply_html("▶️ <b>Strategy execution RESUMED successfully.</b>")
            else:
                await update.message.reply_html("⚠️ StrategyBot not linked.")
        else:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm Resume", callback_data="confirm_resume"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")
                ]
            ]
            await update.message.reply_html(
                "⚠️ <b>Confirm Resume:</b> Re-enabling autonomous signal submission.\n"
                "Type <code>/resume confirm</code> or tap below:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def cmd_flatten(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            return
        args = context.args or []
        if "confirm" in [a.lower() for a in args]:
            if self.execution_bot:
                count = await self.execution_bot.flatten_all_positions(reason="Owner Telegram /flatten confirm")
                await update.message.reply_html(f"🛑 <b>FLATTEN COMPLETE:</b> Closed {count} positions immediately.")
            else:
                await update.message.reply_html("⚠️ ExecutionBot not linked.")
        else:
            keyboard = [
                [
                    InlineKeyboardButton("🛑 Confirm FLATTEN ALL", callback_data="confirm_flatten"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")
                ]
            ]
            await update.message.reply_html(
                "🚨 <b>WARNING: IMMEDIATE LIQUIDATION REQUESTED</b>\n"
                "This will market-close all active positions across the portfolio.\n"
                "Type <code>/flatten confirm</code> or tap below to proceed:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def cmd_kill(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            return
        self.kill_switch_active = True
        if self.strategy_bot:
            self.strategy_bot.pause("Emergency KILL by owner via Telegram")
        if self.execution_bot:
            await self.execution_bot.emergency_protect_positions("Emergency KILL triggered via Telegram")
        await update.message.reply_html(
            "🚨 <b>EMERGENCY KILL ACTIVATED:</b>\n"
            "• All autonomous trading is hard halted.\n"
            "• StrategyBot paused.\n"
            "• Open positions stops tightened to break-even/entry.\n"
            "• Pending entries vetoed.\n\n"
            "🔒 <b>SECURITY LOCK:</b> Resuming requires admin password authentication:\n"
            "<code>/resume &lt;admin_password&gt;</code>"
        )

    async def cmd_prohibited_security_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Reject any attempt to change mode or raise risk limits via Telegram."""
        if not self.is_authorized(update):
            return
        await update.message.reply_html(
            "⛔ <b>SECURITY INVARIANT VIOLATION:</b>\n"
            "Telegram commands are strictly prohibited from altering Autonomy Modes (e.g. switching to LIVE) "
            "or elevating Risk Limits. Live trading activation requires local terminal re-authentication "
            "and completion of all 5 institutional safety gates."
        )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline button actions."""
        if not self.is_authorized(update):
            return
        query = update.callback_query
        await query.answer()

        data = query.data
        if data == "action_pause":
            if self.strategy_bot:
                self.strategy_bot.pause("Paused via inline Telegram button")
                await query.edit_message_text("⏸️ Strategy signal generation PAUSED.")
        elif data == "req_resume":
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm Resume", callback_data="confirm_resume"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")
                ]
            ]
            await query.edit_message_text(
                "⚠️ Confirm resumption of autonomous signal execution:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif data == "confirm_resume":
            if self.kill_switch_active:
                await query.edit_message_text(
                    "⛔ RESUME BLOCKED: Emergency kill switch is engaged.\n"
                    "Resuming requires the admin password via chat:\n"
                    "/resume <admin_password>"
                )
            elif self.strategy_bot:
                self.strategy_bot.resume()
                await query.edit_message_text("▶️ Strategy execution RESUMED successfully.")
        elif data == "req_flatten":
            keyboard = [
                [
                    InlineKeyboardButton("🛑 Confirm FLATTEN ALL", callback_data="confirm_flatten"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")
                ]
            ]
            await query.edit_message_text(
                "🚨 <b>WARNING: Immediate Position Liquidation</b>\nMarket-close all active positions?",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif data == "confirm_flatten":
            if self.execution_bot:
                count = await self.execution_bot.flatten_all_positions(reason="Owner Telegram inline button confirm")
                await query.edit_message_text(f"🛑 FLATTEN COMPLETE: Market closed {count} positions.")
        elif data == "action_status":
            await query.message.reply_html(self._format_status_text())
        elif data == "action_pnl":
            if self.journal_bot:
                await query.message.reply_html(self.journal_bot.generate_report(period="daily"))
        elif data == "cancel_action":
            await query.edit_message_text("❌ Action cancelled.")

    async def send_alert(self, text: str) -> bool:
        """Deliver alert to owner chat. Raises ConnectionError if Telegram API fails."""
        if not self.app or not self.token or not self.owner_chat_id:
            # Cannot deliver via network
            raise ConnectionError("Telegram bot application is not active or unconfigured.")

        try:
            await self.app.bot.send_message(
                chat_id=self.owner_chat_id,
                text=text,
                parse_mode="HTML"
            )
            return True
        except Exception as exc:
            logger.warning("[TelegramGateway] Network dispatch error: %s", exc)
            raise ConnectionError(f"Telegram network delivery failed: {exc}") from exc
