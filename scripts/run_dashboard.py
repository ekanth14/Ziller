"""Run the workspace dashboard with public online data and trading disabled.

Usage: python -B scripts/run_dashboard.py [--port 8910]
Uses existing local users and research records. Never edits .env or starts a bot.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def dashboard_environment():
    env = dict(os.environ)
    # Explicit blanks prevent settings.load_env_file from loading execution
    # credentials into this public-data dashboard process.
    for key in ('EXCHANGE_API_KEY', 'EXCHANGE_API_SECRET',
                'BINANCE_TESTNET_API_KEY', 'BINANCE_TESTNET_API_SECRET',
                'BINANCE_LIVE_API_KEY', 'BINANCE_LIVE_API_SECRET',
                'TELEGRAM_BOT_TOKEN', 'TELEGRAM_OWNER_CHAT_ID', 'TELEGRAM_OWNER_USER_ID'):
        env[key] = ''
    env.update(TRADING_MODE='OBSERVE', LIVE_TRADING='false', SIGNUP_MODE='invite',
               ALLOW_OPEN_SIGNUP='false', BINANCE_TESTNET_BASE_URL='https://testnet.binance.vision',
               OLLAMA_HOST='http://127.0.0.1:11434', OLLAMA_MODEL='gemma4-quant:12b',
               PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8910)
    args = parser.parse_args()
    return subprocess.call([sys.executable, '-B', '-m', 'cryptoscope.dashboard',
                            '--port', str(args.port)], cwd=ROOT, env=dashboard_environment())


if __name__ == '__main__':
    raise SystemExit(main())
