"""Dashboard process settings must not inherit order credentials or enable live."""
import os
from pathlib import Path
import runpy


def test_online_dashboard_launch_excludes_execution_settings_without_editing_parent(monkeypatch):
    monkeypatch.setenv('EXCHANGE_API_KEY', 'fixture-only')
    monkeypatch.setenv('BINANCE_LIVE_API_SECRET', 'fixture-only')
    monkeypatch.setenv('LIVE_TRADING', 'true')
    monkeypatch.setenv('SIGNUP_MODE', 'open')
    parent = dict(os.environ)
    launcher = runpy.run_path(str(Path('scripts/run_dashboard.py')))
    child = launcher['dashboard_environment']()
    assert child['EXCHANGE_API_KEY'] == child['BINANCE_LIVE_API_SECRET'] == ''
    assert child['TRADING_MODE'] == 'OBSERVE'
    assert child['LIVE_TRADING'] == 'false'
    assert child['SIGNUP_MODE'] == 'invite'
    assert child['OLLAMA_MODEL'] == 'qwen3:8b'
    assert dict(os.environ) == parent
