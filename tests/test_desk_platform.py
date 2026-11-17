"""AI overlay (veto-only), symbol directory, system monitor and fleet manager guards."""
import math
from pathlib import Path

import pytest

from cryptoscope.desk.ai_layer import ai_overlay, _kelly
from cryptoscope.desk.engine import build_desk
from cryptoscope.desk.feed import SymbolDirectory
from cryptoscope.desk.fleet import FleetManager
from cryptoscope.desk import system_monitor as sm


def _candles(n=200):
    out, prev = [], 100.0
    for i in range(n):
        c = 100 * (1 + 0.25 * math.sin(i / 9)) + i * 0.05
        out.append({"open_time": 1_700_000_000 + i * 86400, "open": prev, "high": max(prev, c) * 1.01,
                    "low": min(prev, c) * 0.99, "close": c, "volume": 100.0})
        prev = c
    return out


class _Layer:
    def __init__(self, action):
        self.action = action

    def decide(self, rows, symbol):
        return {"final_action": self.action, "thesis": "fixture",
                "tier1": {"action": self.action, "score": 0, "setup_type": "X", "reasons": []},
                "tier2": {"status": "SKIPPED", "agreed": False}}


def _desk_with(action):
    d = build_desk(_candles())
    d["decision"]["action"] = action
    return d


def test_ai_layer_runs_real_systems_and_never_creates_a_buy():
    candles = _candles()
    out = ai_overlay(candles, "BTCUSDT", _desk_with("HOLD"), layer=_Layer("LONG"))
    assert {s["key"] for s in out["systems"]} == {"smc_laya", "committee"}
    assert out["final_action"] == "HOLD"  # an AI BUY alone never opens a position


def test_ai_layer_vetoes_rule_buy_on_ai_sell():
    out = ai_overlay(_candles(), "BTCUSDT", _desk_with("BUY"), layer=_Layer("SHORT"))
    assert out["rule_pm"] == "BUY" and out["final_action"] == "HOLD"
    assert any("SMC + Laya" in v for v in out["vetoes"])


def test_ai_layer_survives_a_failing_system():
    class Broken:
        def decide(self, *a):
            raise RuntimeError("boom")

    out = ai_overlay(_candles(), "BTCUSDT", _desk_with("SELL"), layer=Broken())
    smc = next(s for s in out["systems"] if s["key"] == "smc_laya")
    assert smc["status"] == "ERROR" and out["final_action"] == "SELL"


def test_kelly_needs_wins_and_losses():
    assert _kelly([]) == 0.0
    assert _kelly([{"net_pct": 0.1}]) == 0.0
    assert _kelly([{"net_pct": 0.1}, {"net_pct": -0.05}, {"net_pct": 0.1}]) > 0


def test_symbol_directory_caches_and_serves_stale_on_outage():
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("down")
        return [{"symbol": "BTCUSDT", "base": "BTC", "quote": "USDT"}]

    d = SymbolDirectory(ttl_seconds=0, fetcher=fetch)
    assert d.symbols()["status"] == "OK"
    stale = d.symbols()
    assert stale["status"] == "STALE" and stale["symbols"][0]["symbol"] == "BTCUSDT"
    assert SymbolDirectory(fetcher=lambda: (_ for _ in ()).throw(OSError("x"))).symbols()["status"] == "UNAVAILABLE"


def test_system_monitor_snapshot_without_network(monkeypatch):
    monkeypatch.setattr(sm, "_http_rtt", lambda url, timeout=3.0: {"ok": True, "status": 200, "ms": 12.5})
    monkeypatch.setattr(sm, "_clock_offset_ms", lambda: 3.0)
    m = sm.SystemMonitor(feed_status=lambda: {"exchanges": {}, "tickers": {}})
    snap = m.snapshot()
    hw = snap["hardware"]
    assert 0 <= hw["cpu"]["percent"] <= 100 and hw["memory"]["total_gb"] > 0
    assert all(t["ms"] == 12.5 for t in snap["latency"]["targets"])
    assert snap["latency"]["clock_offset_ms"] == 3.0
    assert snap["latency_history"]["Binance REST"] == [12.5]


def test_fleet_refuses_live_and_bad_symbols(tmp_path):
    f = FleetManager(Path(tmp_path))
    with pytest.raises(ValueError):
        f.start("LIVE", ["BTCUSDT"], "t")
    with pytest.raises(ValueError):
        f.start("PAPER", ["BTC USDT; rm"], "t")
    with pytest.raises(ValueError):
        f.start("PAPER", [], "t")
    assert f.status()["running"] is False


def test_fleet_child_env_drops_blanked_keys_and_forces_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "")
    monkeypatch.setenv("TRADING_MODE", "OBSERVE")
    env = FleetManager(Path(tmp_path))._child_env("TESTNET")
    assert "BINANCE_TESTNET_API_KEY" not in env
    assert env["TRADING_MODE"] == "TESTNET" and env["LIVE_TRADING"] == "false"


def test_fleet_log_tail_redacts_secret_like_values(tmp_path):
    f = FleetManager(Path(tmp_path))
    log = Path(tmp_path) / "fleet.log"
    log.write_text("ok line\napi_key=abc123\nsecret: xyz\n", encoding="utf-8")
    f._meta = {"log": "fleet.log"}
    tail = f.tail()
    assert "abc123" not in "".join(tail) and "xyz" not in "".join(tail)
