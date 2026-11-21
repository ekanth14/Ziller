"""Minimal one-shot Telegram sender, run as a child process.

Usage:  python -m cryptoscope.telegram.notify --test
        python -m cryptoscope.telegram.notify --text "Fleet stopped"

The dashboard deliberately runs without Telegram credentials in its environment. It calls this
module in a short-lived subprocess that reads TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_CHAT_ID from the
environment or the project .env, sends one message to the owner chat, and prints a JSON status.
The token is never printed, logged or returned.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_CHAT_ID")
IST = timezone(timedelta(hours=5, minutes=30))


def read_config(env_file: Path = ROOT / ".env") -> dict:
    cfg = {k: (os.environ.get(k) or "").strip() for k in KEYS}
    if env_file.is_file() and not all(cfg.values()):
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k in KEYS and not cfg[k]:
                cfg[k] = v.strip().strip("\"'")
    return cfg


def configured(env_file: Path = ROOT / ".env") -> dict:
    """Presence only, never values."""
    cfg = read_config(env_file)
    chat_ok = cfg["TELEGRAM_OWNER_CHAT_ID"].lstrip("-").isdigit()
    return {"token_set": bool(cfg["TELEGRAM_BOT_TOKEN"]), "owner_chat_set": chat_ok,
            "configured": bool(cfg["TELEGRAM_BOT_TOKEN"]) and chat_ok}


def send(text: str, cfg: dict | None = None, timeout: float = 10.0) -> dict:
    cfg = cfg or read_config()
    if not cfg["TELEGRAM_BOT_TOKEN"] or not cfg["TELEGRAM_OWNER_CHAT_ID"].lstrip("-").isdigit():
        return {"ok": False, "error": "Telegram is not configured (TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_CHAT_ID in .env)"}
    body = urlencode({"chat_id": cfg["TELEGRAM_OWNER_CHAT_ID"], "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": "true"}).encode()
    url = f"https://api.telegram.org/bot{cfg['TELEGRAM_BOT_TOKEN']}/sendMessage"
    try:
        with urlopen(Request(url, data=body), timeout=timeout) as resp:  # noqa: S310 - fixed Telegram host
            out = json.loads(resp.read())
        return {"ok": bool(out.get("ok")), "message_id": (out.get("result") or {}).get("message_id")}
    except HTTPError as exc:
        # Telegram's description (e.g. "chat not found") is safe; the URL with the token is not echoed.
        try:
            desc = json.loads(exc.read()).get("description", "")
        except Exception:
            desc = ""
        return {"ok": False, "error": f"Telegram HTTP {exc.code}: {desc}"[:200]}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--test", action="store_true")
    group.add_argument("--text")
    args = ap.parse_args(argv)
    stamp = datetime.now(IST).strftime("%d %b %Y %H:%M:%S IST")
    text = ("✅ <b>ZILLERS test message</b>\nTelegram notifications are working. You will get a message for every "
            f"bot fill, closed position and halt.\n<i>{stamp}</i>") if args.test else f"{args.text}\n<i>{stamp}</i>"
    result = send(text)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
