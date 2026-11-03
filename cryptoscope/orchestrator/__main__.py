"""CLI Entry point for ZILLERS Multi-Bot Autonomous Orchestrator.

Usage:
    python -m cryptoscope.orchestrator [--mode PAPER|TESTNET|OBSERVE] [--symbols BTCUSDT ETHUSDT SOLUSDT]
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from typing import Optional

from cryptoscope.orchestrator.engine import OrchestratorEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cryptoscope.orchestrator")


def load_credentials_env():
    """Load credentials from credentials.env if available."""
    env_path = "credentials.env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k and k not in os.environ:
                    os.environ[k] = v


async def run_orchestrator(mode: str, symbols: list[str]):
    load_credentials_env()

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_owner_chat_id = os.getenv("TELEGRAM_OWNER_CHAT_ID")
    env_mode = os.getenv("TRADING_MODE", mode).upper()

    print(f"============================================================", flush=True)
    print(f"  ZILLERS AUTONOMOUS MULTI-BOT TRADING FLEET", flush=True)
    print(f"  Execution Mode: {env_mode}", flush=True)
    print(f"  Active Universe: {', '.join(symbols)}", flush=True)
    print(f"  Telegram Alerts: {'CONFIGURED' if telegram_token and telegram_owner_chat_id else 'OFFLINE SPOOL'}", flush=True)
    print(f"============================================================", flush=True)

    engine = OrchestratorEngine(
        mode=env_mode,
        symbols=symbols,
        telegram_token=telegram_token,
        telegram_owner_chat_id=telegram_owner_chat_id,
    )

    stop_event = asyncio.Event()

    def _signal_handler():
        print("\n[ZILLERS] Shutdown signal received. Stopping fleet...", flush=True)
        stop_event.set()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for s in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(s, _signal_handler)

    try:
        await engine.start()
        print(f"[ZILLERS] Autonomous fleet online. Press Ctrl+C to stop.", flush=True)
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await engine.stop()
        print("[ZILLERS] Orchestrator shutdown complete.", flush=True)


def main():
    parser = argparse.ArgumentParser(description="ZILLERS Multi-Bot Autonomous Orchestrator")
    parser.add_argument("--mode", type=str, default="PAPER", choices=["OBSERVE", "PAPER", "TESTNET", "LIVE"], help="Trading mode")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT"], help="Trading symbols")
    args = parser.parse_args()

    try:
        asyncio.run(run_orchestrator(args.mode, args.symbols))
    except KeyboardInterrupt:
        print("\n[ZILLERS] Stopped by operator.", flush=True)


if __name__ == "__main__":
    main()
