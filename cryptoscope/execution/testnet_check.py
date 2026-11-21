"""One-shot Binance Spot TESTNET account check, run as a child process.

Usage:  python -m cryptoscope.execution.testnet_check

Reads BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_API_SECRET from the environment or the project
.env, makes ONE signed read-only call (GET /api/v3/account) and prints a JSON summary:
{"ok", "can_trade", "usdt_free", "assets", "error"}. Keys are never printed, logged or returned.
The dashboard calls this in a subprocess so its own process never holds exchange keys.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYS = ("BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET")


def _load_env(env_file: Path = ROOT / ".env") -> None:
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k in KEYS and not os.environ.get(k):
            os.environ[k] = v.strip().strip("\"'")


def check() -> dict:
    _load_env()
    if not all(os.environ.get(k) for k in KEYS):
        return {"ok": False, "error": "testnet keys missing in .env"}
    from cryptoscope.execution.binance_testnet import BinanceAuthError, BinanceClientError, BinanceTestnetClient
    try:
        acct = BinanceTestnetClient(timeout=10).get_account()
    except BinanceAuthError:
        return {"ok": False, "error": "testnet keys rejected (invalid or expired; testnet keys reset periodically)"}
    except BinanceClientError as exc:
        return {"ok": False, "error": f"testnet unavailable ({type(exc).__name__})"}
    bal = {b["asset"]: float(b.get("free", 0)) for b in acct.get("balances", [])}
    usdt = bal.get("USDT", 0.0)
    can = bool(acct.get("canTrade", False))
    return {"ok": can and usdt > 0, "can_trade": can, "usdt_free": usdt,
            "assets": sum(1 for v in bal.values() if v > 0),
            "error": None if can and usdt > 0 else ("trading disabled on this key" if not can else "no USDT balance")}


if __name__ == "__main__":
    try:
        out = check()
    except Exception as exc:  # never leak details that could include request data
        out = {"ok": False, "error": f"check failed ({type(exc).__name__})"}
    sys.stdout.write(json.dumps(out))
