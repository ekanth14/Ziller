"""THX-02 / Laya meta-label filter: sidecar protocol, fail-open client, shadow vs enforced veto, journal."""
import asyncio
import importlib.util
import json
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from cryptoscope.agents import decision_models as dm

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "t" * 24


def _server_module():
    spec = importlib.util.spec_from_file_location("zillers_sidecar", ROOT / "cryptoscope" / "models_sidecar" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sidecar(tmp_path):
    """The real sidecar HTTP handler with stand-in models (no torch needed)."""
    mod = _server_module()
    seen = []

    def fake(p_yes, name):
        def ask(model, state, questions):
            seen.append((name, state))
            return {"take": {"type": "noul", "noul": p_yes}, "quality": {"type": "score", "score": 3.0}}
        return (lambda: object(), ask)
    mod.LOADERS.update({"thx02": fake(0.30, "thx02"), "laya": fake(0.10, "laya")})
    slots = {n: mod.Slot(n) for n in ("thx02", "laya")}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), mod.make_handler(slots, TOKEN))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    rt = tmp_path / "models_sidecar.json"
    rt.write_text(json.dumps({"url": url, "token": TOKEN}))
    yield {"url": url, "runtime": rt, "seen": seen}
    httpd.shutdown()


def test_sidecar_requires_token_and_answers_both_models(sidecar):
    bad = dm.MetaLabeler(url=sidecar["url"], token="wrong-token-wrong-token")
    assert bad.health()["running"] is False
    good = dm.MetaLabeler(runtime_file=sidecar["runtime"])
    assert set(good.health()["models"]) == {"thx02", "laya"}
    m = good.assess("ADAUSDT", "BUY", 1.0, 0.9948, 1.0075, 4.0, {"rsi": 58, "tier": "SHORT_TERM", "r4h": 0.004})
    assert m["thx02_p"] == 0.3 and m["laya_p"] == 0.1 and m["mean_p"] == 0.2 and m["quality"] == 3.0
    state = sidecar["seen"][0][1]
    assert "ADAUSDT" in state and "take-profit" in state and "RSI(14): 58" in state and "SHORT_TERM" in state


def test_client_fails_open_without_sidecar(tmp_path):
    m = dm.MetaLabeler(runtime_file=tmp_path / "missing.json").assess("ADAUSDT", "BUY", 1.0, 0.99, 1.01)
    assert m["mean_p"] is None and "sidecar" in m["errors"]
    assert dm.veto_reason(m) is None


def test_veto_only_when_enforced(monkeypatch):
    low = {"mean_p": 0.2}
    monkeypatch.delenv("ZILLERS_META_ENFORCE", raising=False)
    assert dm.veto_reason(low) is None                                  # shadow mode: never vetoes
    monkeypatch.setenv("ZILLERS_META_ENFORCE", "1")
    assert dm.veto_reason(low).startswith("META_LABEL_SKIP")
    assert dm.veto_reason({"mean_p": 0.7}) is None
    assert dm.veto_reason({"mean_p": None}) is None                     # no opinion never vetoes
    monkeypatch.setenv("ZILLERS_META_MIN_P", "0.1")
    assert dm.veto_reason(low) is None


def test_state_text_states_fee_maths():
    s = dm.build_state("XRPUSDT", "BUY", 2.0, 1.99, 2.02, 4, {})
    assert "+1.00%" in s and "break-even win rate" in s


def test_debate_attaches_meta_and_risk_vetoes_when_enforced(sidecar, monkeypatch, tmp_path):
    from cryptoscope.orchestrator.bots.debate_bot import DebateBot
    from cryptoscope.orchestrator.bots.journal_bot import JournalBot
    from cryptoscope.orchestrator.bots.risk_bot import RiskBot
    from cryptoscope.orchestrator.event_bus import EventBus
    from cryptoscope.orchestrator.events import DebateResult, RiskDecision, RiskPreApproved, TradeIntent

    async def run(enforce):
        monkeypatch.setenv("ZILLERS_META_ENFORCE", "1" if enforce else "0")
        bus = EventBus()
        bot = DebateBot(bus, timeout_seconds=5)
        bot.meta_labeler = dm.MetaLabeler(runtime_file=sidecar["runtime"])
        bot.deliberation_engine.deliberate_combined = lambda **_: {
            "verdict": "APPROVE", "conviction_score": 8, "bull_thesis": "", "bear_thesis": "", "reason": "",
            "fallback_used": False}
        out = []

        async def emit(ev):
            out.append(ev)
        bot.emit = emit
        intent = TradeIntent(symbol="ADAUSDT", direction="BUY", entry_price=1.0, stop_loss=0.99, take_profit=1.01,
                             horizon_bars=16, metadata={"features": {"rsi": 55}})
        await bot._run_debate(RiskPreApproved(intent_id=intent.intent_id, symbol="ADAUSDT", direction="BUY",
                                              entry_price=1.0, stop_loss=0.99, take_profit=1.01,
                                              strategy_id="t", intent=intent))
        res = next(e for e in out if isinstance(e, DebateResult))
        risk = RiskBot(EventBus())
        risk.cached_intents[intent.intent_id] = intent
        decisions = []

        async def remit(ev):
            decisions.append(ev)
        risk.emit = remit
        await risk._evaluate_risk(res)
        journal = JournalBot(EventBus(), db_path=str(tmp_path / f"j{int(enforce)}.db"))
        await journal.on_event(res)
        return res, next(e for e in decisions if isinstance(e, RiskDecision)), tmp_path / f"j{int(enforce)}.db"

    res, dec, db = asyncio.run(run(False))
    assert res.meta["mean_p"] == 0.2 and res.meta["enforced"] is False and res.meta["vetoed"] is False
    assert not any("META_LABEL" in r for r in dec.veto_reasons)          # shadow: logged, not acted on
    row = sqlite3.connect(db).execute("SELECT thx02_p, laya_p, mean_p, enforced, vetoed FROM meta_labels").fetchone()
    assert row == (0.3, 0.1, 0.2, 0, 0)

    res, dec, _ = asyncio.run(run(True))
    assert res.meta["vetoed"] is True and dec.decision == "VETOED"
    assert any(r.startswith("META_LABEL_SKIP") for r in dec.veto_reasons)


def test_manager_refuses_to_start_without_install(tmp_path):
    mgr = dm.SidecarManager(python=tmp_path / "nope.exe", runtime_file=tmp_path / "rt.json",
                            models_dir=tmp_path / "models", wsl=False)
    res = mgr.start()
    assert res["ok"] is False and not mgr.running() and not (tmp_path / "rt.json").exists()


def test_pnl_report_compares_take_vs_skip():
    from cryptoscope.desk.pnl import meta_label_report
    labels = [{"timestamp": 100, "symbol": "AUSDT", "thx02_p": 0.8, "laya_p": 0.6, "mean_p": 0.7},
              {"timestamp": 100, "symbol": "BUSDT", "thx02_p": 0.2, "laya_p": 0.2, "mean_p": 0.2},
              {"timestamp": 9000, "symbol": "AUSDT", "thx02_p": 0.1, "laya_p": 0.1, "mean_p": 0.1}]
    closed = [{"symbol": "AUSDT", "timestamp": 1000, "duration_seconds": 600, "pnl_usd": 4.0},   # opened at 400 -> take
              {"symbol": "BUSDT", "timestamp": 1000, "duration_seconds": 600, "pnl_usd": -6.0},  # skip
              {"symbol": "CUSDT", "timestamp": 1000, "duration_seconds": 600, "pnl_usd": 1.0}]   # no answer
    r = meta_label_report(closed, labels, min_p=0.5, needed=2)
    row = {(x["model"], x["group"]): x for x in r["rows"]}
    assert row[("THX-02 + Laya", "take")]["realized"] == 4.0 and row[("THX-02 + Laya", "skip")]["realized"] == -6.0
    assert row[("THX-02 + Laya", "no opinion")]["trades"] == 1 and r["judged"] == 2
    assert "would have helped" in r["verdict"]
    assert "Keep shadow" in meta_label_report(closed, labels, needed=100)["verdict"]
