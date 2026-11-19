"""START ALL: self-test runner semantics and the default check list wiring."""
import threading

import pytest

from cryptoscope.desk.startup import Check, StartupRunner, build_default_checks


def _runner(checks):
    return StartupRunner(lambda mode: checks)


def _run(checks, mode="PAPER"):
    r = _runner(checks)
    r.start(mode, "admin")
    r.wait(10)
    return r.status()


def test_all_ok_means_on_board_and_launch_runs_last():
    order = []
    mk = lambda k, **kw: Check(k, k, "G", lambda: (order.append(k) or ("ok", k)), **kw)  # noqa: E731
    s = _run([mk("launch1", launch=True), mk("a", critical=True), mk("b")])
    assert s["on_board"] is True and s["summary"].startswith("All 2 models") and "Bots launched" in s["summary"]
    assert order == ["a", "b", "launch1"] and all(x["status"] == "ok" for x in s["steps"])
    assert all(x["latency_ms"] is not None for x in s["steps"]) and not s["running"]


def test_critical_failure_blocks_launch():
    launched = []
    s = _run([Check("data", "Market data", "D", lambda: ("fail", "offline"), critical=True),
              Check("x", "X", "D", lambda: ("ok", "")),
              Check("fleet", "Fleet", "B", lambda: launched.append(1) or ("ok", ""), launch=True)])
    assert s["on_board"] is False and launched == []
    fleet = next(x for x in s["steps"] if x["key"] == "fleet")
    assert fleet["status"] == "skipped" and "Market data" in fleet["detail"]
    assert s["critical_failed"] == ["Market data"] and "NOT on board" in s["summary"]


def test_warnings_launch_but_not_on_board_and_exceptions_are_failures():
    def boom():
        raise RuntimeError("model crashed")
    s = _run([Check("w", "W", "G", lambda: ("warn", "slow")), Check("e", "E", "G", boom),
              Check("odd", "Odd", "G", lambda: ("maybe", "")), Check("l", "L", "B", lambda: ("ok", ""), launch=True)])
    st = {x["key"]: x for x in s["steps"]}
    assert st["e"]["status"] == "fail" and "model crashed" in st["e"]["detail"]
    assert st["odd"]["status"] == "fail" and st["l"]["status"] == "ok"
    assert s["on_board"] is False and s["summary"].startswith("Partly on board")


def test_refuses_live_and_double_start():
    gate = threading.Event()
    r = _runner([Check("slow", "Slow", "G", lambda: (gate.wait(5), ("ok", ""))[1])])
    with pytest.raises(ValueError):
        r.start("LIVE", "admin")
    r.start("PAPER", "admin")
    with pytest.raises(RuntimeError):
        r.start("PAPER", "admin")
    gate.set()
    r.wait(5)
    assert r.status()["on_board"] is True


class _Panel:
    host = "http://127.0.0.1:9"

    def models(self):
        return ["a-chat:1b", "debate:12b"]


def test_default_checks_cover_every_model_and_mark_criticals(monkeypatch):
    monkeypatch.setattr("cryptoscope.agents.consensus.resolve_debate_model", lambda: "debate:12b")
    checks = build_default_checks("PAPER", kill_switch=None, risk_governor=None, fleet=None, autopilot=None, scanner=None,
                                  paper_bots=None, llm_panel=_Panel(), laya_evaluator=None, klines=None,
                                  telegram_status=lambda: {})
    keys = [c.key for c in checks]
    assert "llm:a-chat:1b" in keys and "llm:debate:12b" not in keys            # debate model gets the full debate test
    assert keys.index("debate") > keys.index("llm:a-chat:1b")                  # debate last so it stays warm
    assert {c.key for c in checks if c.critical} == {"kill", "governor", "data", "ollama", "debate"}
    assert {c.key for c in checks if c.launch} == {"bots", "autopilot", "telegram", "panel"}
    for k in ("ocaml", "native", "scanner", "desk", "smc", "committee", "strategies", "hmm", "lab"):
        assert k in keys


def test_launch_warning_does_not_hide_models_on_board():
    s = _run([Check("m", "Model", "G", lambda: ("ok", "")),
              Check("fleet", "Fleet", "B", lambda: ("warn", "no eligible coin"), launch=True)])
    assert s["on_board"] is True and "no eligible coin" in s["summary"]


def test_testnet_mode_adds_critical_account_check(monkeypatch):
    monkeypatch.setattr("cryptoscope.agents.consensus.resolve_debate_model", lambda: "debate:12b")
    kw = dict(kill_switch=None, risk_governor=None, fleet=None, autopilot=None, scanner=None, paper_bots=None,
              llm_panel=_Panel(), laya_evaluator=None, klines=None, telegram_status=lambda: {})
    assert "testnet" not in [c.key for c in build_default_checks("PAPER", **kw)]
    bad = build_default_checks("TESTNET", testnet_account=lambda: {"ok": False, "error": "testnet keys rejected"}, **kw)
    chk = next(c for c in bad if c.key == "testnet")
    assert chk.critical and chk.fn() == ("fail", "testnet keys rejected")
    good = build_default_checks("TESTNET", testnet_account=lambda: {"ok": True, "usdt_free": 9972.2}, **kw)
    status, detail = next(c for c in good if c.key == "testnet").fn()
    assert status == "ok" and "9,972.20" in detail


class _Fleet:
    def __init__(self, mode):
        self.st, self.stopped = {"running": True, "mode": mode, "symbols": ["MMTUSDT"]}, []

    def status(self):
        return self.st

    def stop(self, reason=""):
        self.stopped.append(reason); self.st = {"running": False}


class _Auto:
    def __init__(self, fleet, open_positions):
        self.fleet, self.n = fleet, open_positions

    def positions_open(self):
        return self.n

    def start(self, mode, actor):
        self.fleet.st = {"running": True, "mode": mode, "symbols": ["MMTUSDT"]}
        return {"autopilot": {"last": {"action": "started"}}}


def test_switching_paper_fleet_to_testnet(monkeypatch):
    monkeypatch.setattr("cryptoscope.agents.consensus.resolve_debate_model", lambda: "d")
    monkeypatch.setattr("cryptoscope.desk.startup.time.sleep", lambda s: None)
    for open_pos, expect in ((0, "ok"), (2, "fail")):
        f = _Fleet("PAPER")
        checks = build_default_checks("TESTNET", kill_switch=None, risk_governor=None, fleet=f, autopilot=_Auto(f, open_pos),
                                      scanner=None, paper_bots=None, llm_panel=_Panel(), laya_evaluator=None, klines=None,
                                      telegram_status=lambda: {})
        status, detail = next(c for c in checks if c.key == "autopilot").fn()
        assert status == expect, detail
        assert bool(f.stopped) == (open_pos == 0)
