"""Master kill switch: halts trading, stops the fleet and every AI system served by the dashboard."""
import json
import math
import os
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from cryptoscope.desk.feed import DeskFeed
from cryptoscope.desk.llm_panel import LLMPanel


def _candles(n=200):
    out, prev = [], 100.0
    for i in range(n):
        c = 100 * (1 + 0.25 * math.sin(i / 9)) + i * 0.05
        out.append({"open_time": 1_700_000_000 + i * 86400, "open": prev, "high": max(prev, c) * 1.01,
                    "low": min(prev, c) * 0.99, "close": c, "volume": 100.0})
        prev = c
    return out


def test_desk_ai_layer_is_skipped_and_cache_bypassed_while_killed():
    allowed = {"v": True}
    feed = DeskFeed(fetcher=lambda s, i: _candles(), ai_gate=lambda: allowed["v"], ttl_seconds=60)
    live = feed.desk("BTCUSDT")
    assert "systems" in live["ai"] and not live["ai"].get("halted")
    allowed["v"] = False
    killed = feed.desk("BTCUSDT")  # must not serve the cached pre-kill AI result
    assert killed["ai"]["halted"] is True and killed["ai"]["final_action"] == "HOLD"
    assert killed["ai"]["systems"] == []


def test_llm_panel_refuses_work_and_drops_queue_when_killed(monkeypatch):
    allowed = {"v": True}
    panel = LLMPanel(models=["m1", "m2"], gate=lambda: allowed["v"], host="http://127.0.0.1:9")
    monkeypatch.setattr(LLMPanel, "_ensure_worker", lambda self: None)  # keep jobs queued for inspection
    from cryptoscope.desk.engine import build_desk
    panel.request("BTCUSDT", "1d", 1.0, build_desk(_candles()))
    assert panel._queue
    allowed["v"] = False
    out = panel.halt()
    assert out["queued_jobs_dropped"] == 2 and not panel._queue
    assert panel.request("BTCUSDT", "1d", 2.0, {})["halted"] is True


@pytest.fixture()
def server(monkeypatch, tmp_path):
    from cryptoscope.auth.security import AccountLockoutManager, RateLimiter
    from cryptoscope.auth.store import AuthStore
    from cryptoscope.dashboard.__main__ import handler_for
    from cryptoscope.dashboard.data import DashboardData
    from cryptoscope.market_data.aggregator import MarketDataAggregator

    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")  # never touch the developer's real Ollama
    monkeypatch.setenv("ADMIN_EMAIL", "admin@zillers.local")
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "AdminSuperSecurePass2026!#")
    store = AuthStore(tmp_path / "auth.db")
    admin = store.bootstrap_admin("admin@zillers.local")
    root = Path(__file__).resolve().parents[1]
    data = DashboardData(root, {"symbols": ["BTCUSDT"], "interval": "15m", "model": "gemma4:12b",
                                "ollama_url": "http://127.0.0.1:9", "model_timeout_seconds": 1,
                                "model_max_output_tokens": 10, "model_thinking": False})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(data, store, RateLimiter(limit=50, window_sec=60),
                                                            AccountLockoutManager(), None, MarketDataAggregator(["BTCUSDT"])))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    token, csrf = store.create_session(admin)
    yield f"http://127.0.0.1:{srv.server_address[1]}", token, csrf
    srv.shutdown()
    srv.server_close()


def test_kill_switch_endpoint_stops_background_and_reports_it(server):
    base, token, csrf = server
    req = Request(base + "/api/governor/kill_switch", data=json.dumps({"action": "HALT"}).encode(),
                  headers={"Cookie": f"session_token={token}", "X-CSRF-Token": csrf, "Content-Type": "application/json",
                           "Host": base.split("//")[1]})
    with urlopen(req, timeout=20) as resp:
        body = json.load(resp)
    assert body["background"]["ai_layer"] == "stopped"
    assert body["background"]["fleet"]["running"] is False
    with urlopen(base + "/api/governor/status", timeout=10) as resp:
        status = json.load(resp)
    assert status["kill_switch_engaged"] is True and status["ai_layer"] == "stopped" and status["fleet_running"] is False
    # the fleet cannot be restarted while the latch is engaged
    start = Request(base + "/api/fleet/start", data=json.dumps({"mode": "PAPER"}).encode(),
                    headers={"Cookie": f"session_token={token}", "X-CSRF-Token": csrf, "Content-Type": "application/json"})
    from urllib.error import HTTPError
    with pytest.raises(HTTPError) as err:
        urlopen(start, timeout=10)
    assert err.value.code == 409
