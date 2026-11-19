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
    assert {s["key"] for s in out["systems"]} == {"smc_laya", "committee", "strategies"}
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


# ------------------------------------------------------------------ LLM panel and strategy library
def test_strategy_library_runs_on_real_shaped_candles():
    out = ai_overlay(_candles(), "BTCUSDT", _desk_with("HOLD"), layer=_Layer("STAND_ASIDE"))
    strat = next(s for s in out["systems"] if s["key"] == "strategies")
    assert strat["status"] == "OK" and len(strat["signals"]) == 4
    assert all(g["action"] in {"BUY", "SELL", "NONE"} for g in strat["signals"])


def test_llm_panel_answers_in_background_and_caches_per_bar(monkeypatch):
    import time
    from cryptoscope.desk import llm_panel as lp

    calls = []

    def fake_ask(self, model, prompt):
        calls.append(model)
        assert "Use ONLY the numbers below" in prompt and "BTCUSDT" in prompt
        return {"model": model, "status": "ready", "action": "SELL" if model == "b" else "HOLD", "confidence": 0.6,
                "reason": "test", "latency_ms": 1}

    monkeypatch.setattr(lp.LLMPanel, "_ask", fake_ask)
    panel = lp.LLMPanel(models=["a", "b", "c"])
    desk = _desk_with("BUY")
    first = panel.request("BTCUSDT", "1d", 1.0, desk)
    assert first["ready"] == 0 and {m["status"] for m in first["models"]} <= {"queued", "running"}
    for _ in range(50):
        time.sleep(0.05)
        res = panel.request("BTCUSDT", "1d", 1.0, desk)
        if res["ready"] == 3:
            break
    assert res["ready"] == 3 and res["panel_action"] == "HOLD"  # majority, not any single model
    assert sorted(calls) == ["a", "b", "c"]
    panel.request("BTCUSDT", "1d", 1.0, desk)
    assert len(calls) == 3  # cached for this bar


def test_llm_panel_rejects_non_json_answers(monkeypatch):
    from cryptoscope.desk import llm_panel as lp

    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(lp, "urlopen", lambda req, timeout=0: Resp(b'{"response": "I think you should buy"}'))
    out = lp.LLMPanel(models=["x"])._ask("x", "prompt")
    assert out["status"] == "error"
    monkeypatch.setattr(lp, "urlopen", lambda req, timeout=0: Resp(b'{"response": "{\\"action\\": \\"YOLO\\"}"}'))
    assert lp.LLMPanel(models=["x"])._ask("x", "prompt")["status"] == "error"


def test_llm_panel_host_without_scheme_is_normalised(monkeypatch):
    from cryptoscope.desk.llm_panel import LLMPanel

    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11434")
    assert LLMPanel().host == "http://127.0.0.1:11434"


def test_ai_overlay_vetoes_buy_when_llm_panel_majority_sells():
    class Panel:
        def request(self, *a):
            return {"models": [], "ready": 3, "total": 3, "panel_action": "SELL", "available": True}

    out = ai_overlay(_candles(), "BTCUSDT", _desk_with("BUY"), layer=_Layer("STAND_ASIDE"), llm_panel=Panel())
    assert out["final_action"] == "HOLD"
    assert any("LLM panel" in v for v in out["vetoes"])
