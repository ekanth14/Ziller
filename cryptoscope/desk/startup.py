"""START ALL: bring every LLM, decision model and bot online, test each one, and report.

Runs in a background thread (a full pass takes minutes: each local 12B model needs ~30-100 s on
CPU). The page polls `status()`.

Order
1. Safety      - kill switch released, risk governor answers, OCaml shadow gate agrees with Python,
                 native C++ kernels (or the Python fallback).
2. Data        - live Binance candles, market scanner.
3. Decision    - rule desk, SMC + tier-2 classifier, hedge-fund committee + formula ensemble,
                 strategy library, HMM regime model, Strategy Lab, and the real THX-02 + Laya
                 meta-label sidecar (started here; WSL on Windows).
4. LLMs        - Ollama server, a short JSON test on every installed chat model, then one full
                 fleet debate on the debate model (left warm for the fleet).
5. Launch      - paper bots loop, autopilot (scanner -> fleet on the eligible top picks),
                 Telegram, LLM panel.

"All models on board" = every model/system check passed (launch steps are reported separately:
the fleet may legitimately wait when no coin is eligible). Critical checks (kill switch, market data, risk
governor, debate model) must pass before the fleet is launched; other failures are reported but
do not block the launch. Nothing here can enable LIVE trading.
"""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

CheckFn = Callable[[], Tuple[str, str]]  # -> (status: ok|warn|fail, detail)


@dataclass
class Step:
    key: str
    label: str
    group: str
    critical: bool = False
    launch: bool = False
    status: str = "pending"          # pending | running | ok | warn | fail | skipped
    detail: str = ""
    latency_ms: Optional[float] = None


@dataclass
class Check:
    key: str
    label: str
    group: str
    fn: CheckFn
    critical: bool = False
    launch: bool = False              # launch steps run only after the checks, and only if criticals passed


class StartupRunner:
    def __init__(self, build_checks: Callable[[str], List[Check]]):
        self.build_checks = build_checks
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._state: Dict[str, Any] = {"running": False, "steps": [], "on_board": None, "summary": "Not started"}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            s = dict(self._state)
            s["steps"] = [asdict(x) for x in self._state.get("steps", [])]
        return s

    def start(self, mode: str, actor: str) -> Dict[str, Any]:
        mode = str(mode or "PAPER").upper()
        if mode not in {"PAPER", "TESTNET"}:
            raise ValueError("START ALL runs in PAPER or TESTNET only")
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("Startup is already running")
            checks = self.build_checks(mode)
            self._state = {"running": True, "mode": mode, "actor": actor, "started_at": time.time(), "finished_at": None,
                           "steps": [Step(c.key, c.label, c.group, c.critical, c.launch) for c in checks],
                           "on_board": None, "summary": "Running checks…"}
            self._thread = threading.Thread(target=self._run, args=(checks,), daemon=True, name="startup")
            self._thread.start()
        return self.status()

    def wait(self, timeout: Optional[float] = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _set(self, i: int, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self._state["steps"][i], k, v)

    def _run(self, checks: List[Check]) -> None:
        critical_failed: List[str] = []
        for phase_launch in (False, True):
            for i, c in enumerate(checks):
                if c.launch != phase_launch:
                    continue
                if c.launch and critical_failed:
                    self._set(i, status="skipped", detail="not launched: " + ", ".join(critical_failed) + " failed")
                    continue
                self._set(i, status="running")
                t0 = time.perf_counter()
                try:
                    status, detail = c.fn()
                except Exception as exc:  # a broken check is a failed check, never a crash
                    status, detail = "fail", f"{type(exc).__name__}: {exc}"[:300]
                    traceback.print_exc()
                if status not in {"ok", "warn", "fail"}:
                    status = "fail"
                self._set(i, status=status, detail=str(detail)[:400], latency_ms=round((time.perf_counter() - t0) * 1000, 1))
                if status == "fail" and c.critical:
                    critical_failed.append(c.label)
        with self._lock:
            steps = self._state["steps"]
            counts = {k: sum(1 for s in steps if s.status == k) for k in ("ok", "warn", "fail", "skipped")}
            models = [x for x in steps if not x.launch]
            launch = [x for x in steps if x.launch]
            bad = [x.label for x in models if x.status != "ok"]
            on_board = not bad
            launch_note = ""
            if launch:
                if any(x.status == "skipped" for x in launch):
                    launch_note = " Bots were NOT launched."
                else:
                    issues = [f"{x.label}: {x.detail}" for x in launch if x.status != "ok"]
                    launch_note = " Bots launched." if not issues else " Bots launched; " + " | ".join(issues)
            if on_board:
                summary = f"All {len(models)} models and systems are on board." + launch_note
            elif critical_failed:
                summary = f"NOT on board: critical check failed ({', '.join(critical_failed)})." + launch_note
            else:
                summary = f"Partly on board: {len(models) - len(bad)}/{len(models)} ok; needs attention: {', '.join(bad)}." + launch_note
            self._state.update(running=False, finished_at=time.time(), on_board=on_board, counts=counts,
                               critical_failed=critical_failed, summary=summary)


# ----------------------------------------------------------------------------- concrete checks
def _lab_count() -> int:
    try:
        from cryptoscope.desk.strategy_lab import STRATEGIES
        return len(STRATEGIES)
    except Exception:
        return 0


def build_default_checks(mode: str, *, kill_switch, risk_governor, fleet, autopilot, scanner, paper_bots,
                         llm_panel, laya_evaluator, klines, telegram_status, symbol: str = "ADAUSDT",
                         llm_ping: Optional[Callable[[str], Tuple[str, str]]] = None,
                         debate: Optional[Callable[[], Dict[str, Any]]] = None,
                         testnet_account: Optional[Callable[[], Dict[str, Any]]] = None,
                         decision_sidecar=None, sidecar_wait_s: float = 300.0) -> List[Check]:
    """The real checks, wired to the dashboard's live objects (all injectable for tests)."""
    shared: Dict[str, Any] = {}

    def candles():
        if "candles" not in shared:
            shared["candles"] = klines(symbol, "1d", 300)
        return shared["candles"]

    def desk():
        if "desk" not in shared:
            from cryptoscope.desk.engine import build_desk
            shared["desk"] = build_desk(candles(), symbol=symbol, interval="1d")
        return shared["desk"]

    def c_kill():
        return ("fail", "Emergency halt is engaged — resume the governor first") if kill_switch.halted else ("ok", "released")

    def c_governor():
        ok, reasons = risk_governor.check_pre_trade(symbol=symbol, action="BUY", requested_value=10.0,
                                                    total_portfolio_equity=10_000.0, current_open_orders_count=0,
                                                    feed_age_seconds=0.5, cross_source_divergence_pct=0.1, day_pnl=0.0,
                                                    day_start_equity=10_000.0)
        return "ok", "sample order " + ("allowed" if ok else "blocked: " + "; ".join(r.split(":", 1)[0] for r in reasons))

    def c_ocaml():
        from cryptoscope.execution import shadow_gate as sg
        from cryptoscope.execution.governor import RiskGovernor
        binary = sg.find_binary()
        if binary is None:
            return "warn", "binary not built (run ocaml/risk_gate/build_wsl.sh)"

        class _Quiet:
            def dispatch(self, *a, **k):
                pass
        res = sg.shadow_check(RiskGovernor(alert_service=_Quiet()), binary, now=1_000_000.0, symbol=symbol, action="BUY",
                              requested_value=100.0, total_portfolio_equity=10_000.0, current_open_orders_count=0,
                              feed_age_seconds=0.5, cross_source_divergence_pct=0.1, day_pnl=0.0, day_start_equity=10_000.0)
        via = "WSL" if sg.gate_command(binary)[0] == "wsl.exe" else "native"
        return ("ok", f"agrees with Python governor ({via})") if res.match else ("fail", "; ".join(res.differences))

    def c_native():
        from core.quant import native
        # The Python kernels are the reference implementation; C++ only makes them faster.
        return "ok", "C++ kernels loaded" if native.AVAILABLE else "Python kernels (C++ build blocked by Windows; same results, slower)"

    def c_data():
        c = candles()
        age_h = (time.time() - c[-1]["open_time"]) / 3600
        return ("ok", f"{len(c)} daily candles for {symbol}, last bar {age_h:.1f} h old") if len(c) >= 60 else ("fail", f"only {len(c)} candles")

    def c_scanner():
        r = scanner.scan(mode)
        top = r.get("top", [])
        msg = f"{r['counts']['universe']} coins scanned, {r['counts']['scored']} scored, eligible: {', '.join(top) or 'none right now'}"
        return "ok", msg

    def c_desk():
        d = desk()
        return ("ok", f"PM says {d['decision']['action']} (score {d['decision']['score']:+.2f})") if d.get("status") == "OK" else ("fail", d.get("status"))

    def c_smc():
        from cryptoscope.desk.ai_layer import _smc_laya
        from cryptoscope.autotrader.decision import FastDecisionLayer
        r = _smc_laya(candles()[-200:], symbol, FastDecisionLayer(), 86400)
        st = laya_evaluator.get_status()
        laya = "tier-2 classifier loaded" if st.get("checkpoint_loaded") or st.get("in_process_serving_loaded") else "tier-2 classifier NOT loaded"
        return ("ok" if "NOT" not in laya else "warn"), f"{r['action']} · tier1 {r['tier1']['action']} · {laya}"

    def c_committee():
        from cryptoscope.desk.ai_layer import _committee
        r = _committee(candles(), symbol, desk())
        thx = r.get("thx02") or {}
        return "ok", f"{r['action']} · conviction {r['conviction']:.2f} · formula ensemble {thx.get('action', '—')} ({thx.get('regime', '—')})"

    def c_strats():
        from cryptoscope.desk.ai_layer import _strategies
        r = _strategies(candles(), 86400)
        errs = [s["name"] for s in r["signals"] if s["action"] == "ERROR"]
        return ("fail", "errors: " + ", ".join(errs)) if errs else ("ok", f"{len(r['signals'])} strategies ran · {r['action']}")

    def c_hmm():
        import math
        from core.quant.levels.level10_research import detect_regimes_hmm
        c = [x["close"] for x in candles()]
        rets = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
        r = detect_regimes_hmm(rets, n_states=2)
        calm = min(range(2), key=lambda k: r["state_stds"][k])
        return "ok", f"2-state model fitted · now in {'calm' if r['current_regime'] == calm else 'volatile'} regime"

    def c_promoted():
        """Which Lab strategies passed the gate and will trade in the fleet (LabSignalBot)."""
        from cryptoscope.desk.strategy_lab import load_promoted_strategies
        p = load_promoted_strategies()
        fleet = [x for x in p if x.get("interval") == "15m"]
        if not p:
            return "ok", "none promoted yet — LabSignalBot idle; fleet trades the analyst/quant signals only"
        return "ok", (f"{len(fleet)} on the fleet's 15m bars: " + ", ".join(f"{x['symbol']}:{x['strategy']}" for x in fleet)
                      if fleet else f"{len(p)} promoted, none on 15m bars (the fleet's interval)")

    def c_lab():
        from cryptoscope.desk.strategy_lab import run_lab
        r = run_lab(candles(), "1d", 10)
        ok = [x for x in r.get("results", []) if "error" not in x]
        if r["status"] != "OK" or not ok:
            return "fail", r.get("status", "no results")
        best = ok[0]
        errs = len(r["results"]) - len(ok)
        return ("ok" if not errs else "warn"), f"{len(ok)} strategies backtested · best {best['label']} Sharpe {best['sharpe']:.2f}" + (f" · {errs} errored" if errs else "")

    def c_ollama():
        import json
        from urllib.request import urlopen
        with urlopen(llm_panel.host + "/api/version", timeout=5) as resp:  # noqa: S310 - local Ollama
            ver = json.loads(resp.read()).get("version")
        models = llm_panel.models()
        shared["models"] = models
        return ("ok", f"Ollama {ver} · {len(models)} chat models: {', '.join(models)}") if models else ("fail", "no chat models installed")

    def _default_ping(model):
        from cryptoscope.providers.deadline_http import post_json_deadline
        body = post_json_deadline(llm_panel.host + "/api/generate", {
            "model": model, "prompt": 'Reply with exactly this JSON: {"ok": true}', "format": "json", "think": False,
            "stream": False, "keep_alive": "2m", "options": {"temperature": 0, "num_predict": 16}}, 240.0)
        txt = str(body.get("response", "")).strip()
        import json
        ok = json.loads(txt).get("ok") is True if txt.startswith("{") else False
        secs = (body.get("total_duration") or 0) / 1e9
        return ("ok" if ok else "warn"), f"answered in {secs:.0f} s" + ("" if ok else f" but not valid JSON: {txt[:60]}")

    ping = llm_ping or _default_ping

    def model_check(model):
        return lambda: ping(model)

    def c_debate():
        from cryptoscope.agents.consensus import DeliberationConsensusEngine, resolve_debate_model
        r = debate() if debate else DeliberationConsensusEngine().deliberate_combined(
            symbol, "BUY", 1.0, 0.98, 1.04, {"price": 1.0, "atr": 0.01, "strategy": "startup_self_test"}, timeout_sec=240)
        if r.get("fallback_used"):
            return "fail", f"{r.get('model') or resolve_debate_model()} did not answer in time (fails closed)"
        return "ok", f"{r.get('model')} debated a test trade: {r['verdict']} · conviction {r['conviction_score']:.0f} · {r.get('reason', '')}"

    def c_testnet():
        if testnet_account:
            a = testnet_account()
        else:
            import json
            import subprocess
            import sys
            from pathlib import Path
            root = Path(__file__).resolve().parents[2]
            out = subprocess.run([sys.executable, "-B", "-m", "cryptoscope.execution.testnet_check"], cwd=str(root),
                                 env={k: v for k, v in __import__("os").environ.items() if not k.startswith("BINANCE_")},
                                 capture_output=True, text=True, timeout=40)
            a = json.loads(out.stdout or "{}") if out.stdout.strip().startswith("{") else {"ok": False, "error": "check crashed"}
        if a.get("ok"):
            return "ok", f"keys valid · trading enabled · {a['usdt_free']:,.2f} test USDT"
        return "fail", a.get("error") or "account check failed"

    def c_bots():
        paper_bots.ensure_running()
        n = len(paper_bots.list())
        return "ok", f"grid/DCA loop running · {n} bot(s)"

    def c_autopilot():
        cur = fleet.status()
        if cur.get("running") and cur.get("mode") != mode:
            if autopilot.positions_open():
                return "fail", f"fleet is running in {cur.get('mode')} with open positions; close them before switching to {mode}"
            fleet.stop(reason=f"START ALL switching {cur.get('mode')} -> {mode}")
        out = autopilot.start(mode, "start-all")
        last = out["autopilot"].get("last", {})
        time.sleep(3)
        st = fleet.status()
        if st.get("running"):
            return "ok", f"fleet running in {st.get('mode')} on {', '.join(st.get('symbols', []))}"
        if last.get("action") == "no eligible symbols":
            return "warn", "autopilot on, but no coin is eligible right now — it rescans every 4 h"
        return "fail", f"fleet not running ({last.get('action', 'unknown')}, exit {st.get('exit_code')})"

    def c_telegram():
        t = telegram_status()
        return ("ok", "configured") if t.get("configured") else ("warn", "not configured (alerts off)")

    def c_panel():
        return "ok", "ready on the desk (pauses while the fleet uses Ollama)"

    def c_sidecar():
        """Start the THX-02 + Laya sidecar (WSL on Windows) and wait until its models have loaded."""
        if decision_sidecar is None:
            return "warn", "not configured"
        inst = decision_sidecar.installed()
        if not inst.get("venv") or not any((inst.get("weights") or {}).values()):
            return "warn", ("not installed — see scripts/download_decision_models.py "
                            "(WSL needs: sudo apt install python3.14-venv)")
        started = decision_sidecar.start()
        if not started.get("ok"):
            return "fail", started.get("error", "could not start")
        deadline = time.time() + sidecar_wait_s
        wanted = [n for n, ok in inst["weights"].items() if ok]
        while time.time() < deadline:
            h = decision_sidecar.status().get("health") or {}
            models = h.get("models") or {}
            if wanted and all((models.get(n) or {}).get("loaded") or (models.get(n) or {}).get("error") for n in wanted):
                bad = [f"{n}: {models[n]['error']}" for n in wanted if models[n].get("error")]
                if bad:
                    return "fail", "; ".join(bad)[:200]
                return "ok", " · ".join(f"{n} loaded in {models[n].get('load_s')} s" for n in wanted) + f" ({inst.get('runtime')})"
            time.sleep(2)
        return "fail", f"models still loading after {sidecar_wait_s:.0f} s"

    def meta_check(name):
        def run():
            from cryptoscope.agents.decision_models import QUESTIONS, MetaLabeler, build_state
            if decision_sidecar is None or not (decision_sidecar.installed().get("weights") or {}).get(name):
                return "warn", "not installed"
            t0 = time.time()
            try:
                res = MetaLabeler(timeout=120).ask(build_state(symbol, "BUY", 1.0, 0.9948, 1.0075, 4,
                                                               {"rsi": 56, "tier": "SHORT_TERM", "r4h": 0.004}),
                                                   QUESTIONS, models=[name], timeout=120)
            except Exception as exc:
                return "fail", f"{type(exc).__name__}: {exc}"[:200]
            r = (res.get("models") or {}).get(name) or {}
            if r.get("error"):
                return "fail", r["error"][:200]
            p = (r.get("answers", {}).get("take") or {}).get("noul")
            if p is None:
                return "fail", "no probability returned"
            mode = "ENFORCED veto" if __import__("os").environ.get("ZILLERS_META_ENFORCE") == "1" else "shadow (logged only)"
            return "ok", f"test trade: P(target first) {float(p):.0%} in {(time.time() - t0) * 1000:.0f} ms · {mode}"
        return run

    checks = [
        Check("kill", "Kill switch released", "Safety", c_kill, critical=True),
        Check("governor", "Risk governor", "Safety", c_governor, critical=True),
        Check("ocaml", "OCaml shadow risk gate", "Safety", c_ocaml),
        Check("native", "C++ quant kernels", "Safety", c_native),
        Check("data", "Binance market data", "Data", c_data, critical=True),
        *([Check("testnet", "Binance testnet account", "Data", c_testnet, critical=True)] if mode == "TESTNET" else []),
        Check("scanner", "Market scanner", "Data", c_scanner),
        Check("desk", "Rule models + PM", "Decision models", c_desk),
        Check("smc", "SMC + tier-2 classifier", "Decision models", c_smc),
        Check("committee", "Hedge-fund committee + formula ensemble", "Decision models", c_committee),
        Check("strategies", "Strategy library", "Decision models", c_strats),
        Check("hmm", "HMM regime model", "Decision models", c_hmm),
        Check("lab", f"Strategy Lab ({_lab_count()} strategies)", "Decision models", c_lab),
        Check("promoted", "Lab → fleet (promoted strategies)", "Decision models", c_promoted),
        Check("sidecar", "THX-02 + Laya sidecar", "Decision models", c_sidecar),
        Check("meta:thx02", "THX-02 meta-label (HAL-X-AI)", "Decision models", meta_check("thx02")),
        Check("meta:laya", "Laya meta-label (convaiinnovations)", "Decision models", meta_check("laya")),
        Check("ollama", "Ollama server", "LLMs", c_ollama, critical=True),
    ]
    try:
        from cryptoscope.agents.consensus import resolve_debate_model
        debate_model = resolve_debate_model()
    except Exception:
        debate_model = None
    for m in llm_panel.models():
        if m != debate_model:
            checks.append(Check(f"llm:{m}", f"LLM {m}", "LLMs", model_check(m)))
    checks.append(Check("debate", f"Fleet debate model ({debate_model or 'auto'})", "LLMs", c_debate, critical=True))
    checks += [
        Check("bots", "Paper bots (grid/DCA)", "Bots", c_bots, launch=True),
        Check("autopilot", f"Autopilot + fleet ({mode})", "Bots", c_autopilot, launch=True),
        Check("telegram", "Telegram alerts", "Bots", c_telegram, launch=True),
        Check("panel", "LLM panel", "Bots", c_panel, launch=True),
    ]
    return checks
