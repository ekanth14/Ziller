"""Multi-channel alert dispatcher (Discord, Telegram, Webhook) adapted from daily_stock_analysis.

Executes asynchronously in background threads with strict timeouts to guarantee zero latency impact
on trading execution loops.
"""
from dataclasses import dataclass
import json
import logging
import os
import threading
from typing import Any, Dict, Optional
import urllib.error
import urllib.request

logger = logging.getLogger("cryptoscope.autotrader.notifier")


@dataclass
class AlertPayload:
    title: str
    message: str
    symbol: str
    alert_type: str = "INFO"  # 'TRADE_SIGNAL', 'FILL', 'STOP_HIT', 'TARGET_HIT', 'RISK_HALT', 'INFO'
    details: Optional[Dict[str, Any]] = None


class AlertNotifier:
    """Dispatches real-time crypto alerts to Discord, Telegram, and Webhook endpoints."""

    def __init__(
        self,
        discord_webhook_url: Optional[str] = None,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        generic_webhook_url: Optional[str] = None,
    ):
        self.discord_url = discord_webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self.tg_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.tg_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.webhook_url = generic_webhook_url or os.getenv("GENERIC_WEBHOOK_URL", "")

    def is_configured(self) -> bool:
        return bool(self.discord_url or (self.tg_token and self.tg_chat_id) or self.webhook_url)

    def dispatch(self, alert: AlertPayload, sync: bool = False):
        """Dispatch alert across all configured channels."""
        if not self.is_configured():
            return

        if sync:
            self._send_all(alert)
        else:
            # Asynchronous background thread
            t = threading.Thread(target=self._send_all, args=(alert,), daemon=True)
            t.start()

    def _send_all(self, alert: AlertPayload):
        if self.discord_url:
            self._send_discord(alert)
        if self.tg_token and self.tg_chat_id:
            self._send_telegram(alert)
        if self.webhook_url:
            self._send_generic_webhook(alert)

    def _send_discord(self, alert: AlertPayload):
        try:
            # Color coding: Green for BUY, Red for STOP/HALT, Gold for TARGET, Cyan for INFO
            color_map = {
                "TRADE_SIGNAL": 0x10B981,   # Bullish Green
                "FILL": 0x38BDF8,           # Primary Cyan
                "TARGET_HIT": 0xF5A623,     # Warning Gold / Profit
                "STOP_HIT": 0xF43F5E,       # Rose Red
                "RISK_HALT": 0xDC2626,      # Alert Red
                "INFO": 0x71717A,           # Muted Zinc
            }
            color = color_map.get(alert.alert_type, 0x38BDF8)

            fields = [
                {"name": "Asset", "value": f"`{alert.symbol}`", "inline": True},
                {"name": "Type", "value": f"`{alert.alert_type}`", "inline": True},
            ]

            if alert.details:
                for k, v in list(alert.details.items())[:6]:
                    fields.append({"name": str(k).replace("_", " ").title(), "value": str(v), "inline": True})

            embed = {
                "title": f"⚡ ZILLERS: {alert.title}",
                "description": alert.message,
                "color": color,
                "fields": fields,
                "footer": {"text": "ZILLERS Quantitative Trading Engine • Confidential"},
            }

            payload = json.dumps({"embeds": [embed]}).encode("utf-8")
            req = urllib.request.Request(
                self.discord_url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "ZillersNotifier/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                pass
        except Exception as e:
            logger.warning("Failed to dispatch Discord alert: %s", e)

    def _send_telegram(self, alert: AlertPayload):
        try:
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            text = (
                f"⚡ <b>ZILLERS: {alert.title}</b>\n\n"
                f"<b>Asset:</b> <code>{alert.symbol}</code>\n"
                f"<b>Type:</b> <code>{alert.alert_type}</code>\n"
                f"{alert.message}\n"
            )
            if alert.details:
                text += "\n<b>Parameters:</b>\n"
                for k, v in alert.details.items():
                    text += f"• {k}: <code>{v}</code>\n"

            payload = json.dumps({
                "chat_id": self.tg_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                pass
        except Exception as e:
            logger.warning("Failed to dispatch Telegram alert: %s", e)

    def _send_generic_webhook(self, alert: AlertPayload):
        try:
            payload = json.dumps({
                "title": alert.title,
                "symbol": alert.symbol,
                "alert_type": alert.alert_type,
                "message": alert.message,
                "details": alert.details or {},
            }).encode("utf-8")

            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "ZillersNotifier/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                pass
        except Exception as e:
            logger.warning("Failed to dispatch generic webhook alert: %s", e)
