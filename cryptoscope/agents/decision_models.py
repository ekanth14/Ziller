"""THX-02 + Laya meta-label filter: client, trade-state builder and sidecar process manager.

The models run in a separate process (`cryptoscope/models_sidecar/server.py`, in `.venv-models`), so
the dashboard and the bot fleet never import torch. This module only speaks HTTP to 127.0.0.1.

Role (meta-labeling, López de Prado): a strategy has already chosen a trade; the models answer
"take or skip?" with a probability. They can only VETO, and only when the operator enforces it
(`ZILLERS_META_ENFORCE=1`). Until then every answer is journalled in shadow so the P&L page can show
whether skipped trades really did worse than taken ones. Any error means "no opinion": the filter
never blocks a trade because a model is down, and never adds a trade or raises a size.

Both models are general decision classifiers (ticket routing / moderation), not trained on markets.
"""
from __future__ import annotations

import json
import logging
import math
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger("cryptoscope.agents.decision_models")

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_FILE = ROOT / "work" / "runtime" / "models_sidecar.json"
MODELS_DIR = ROOT / "work" / "models"
VENV_PY = ROOT / ".venv-models" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
SERVER = ROOT / "cryptoscope" / "models_sidecar" / "server.py"
MODEL_NAMES = ("thx02", "laya")

QUESTIONS: Dict[str, Dict[str, Any]] = {
    "take": {
        "type": "noul",
        "instructions": ("You review one proposed long (buy) crypto spot trade. Will the price reach the "
                         "take-profit level before the stop-loss level within the time limit?"),
        "criteria": {"true": "Yes: target is hit first", "false": "No: stop is hit first or time runs out"},
    },
    "quality": {
        "type": "score",
        "instructions": "Rate the quality of this long trade setup given trend, momentum, volatility and liquidity.",
        "criteria": ["very poor", "poor", "average", "good", "excellent"],
    },
}


def enforce_enabled() -> bool:
    return os.environ.get("ZILLERS_META_ENFORCE", "0") == "1"


def min_probability() -> float:
    try:
        return min(0.95, max(0.05, float(os.environ.get("ZILLERS_META_MIN_P", "0.5"))))
    except ValueError:
        return 0.5


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def build_state(symbol: str, direction: str, entry: float, stop: float, target: float, horizon_hours: float,
                features: Optional[Mapping[str, Any]] = None) -> str:
    """A short, model-readable description of the trade. Only facts known at decision time."""
    up = (target / entry - 1) if entry else 0.0
    down = (1 - stop / entry) if entry else 0.0
    fee = 0.002  # ~0.1% per side round trip
    lines = [
        f"Coin: {symbol} (spot, long only). Direction: {direction}.",
        f"Entry {entry:.8g}; take-profit {target:.8g} (+{up:.2%}); stop-loss {stop:.8g} (-{down:.2%}); "
        f"time limit {horizon_hours:g} h.",
        f"After ~0.2% round-trip fees a win nets {up - fee:+.2%} and a loss costs {-(down + fee):.2%}; "
        f"break-even win rate {(down + fee) / ((up - fee) + (down + fee)):.0%}." if up > fee else
        "The target is smaller than round-trip fees.",
    ]
    feats = []
    for key, label, fmt in (
        ("tier", "Scanner tier", "{}"), ("rsi", "RSI(14)", "{:.0f}"), ("rsi1h", "RSI 1h", "{:.0f}"),
        ("atr_pct", "ATR % of price", "{:.2%}"), ("r4h", "Return last 4h", "{:+.2%}"),
        ("r24h", "Return last 24h", "{:+.2%}"), ("ema_trend", "EMA trend", "{}"),
        ("spread_pct", "Bid-ask spread", "{:.3%}"), ("depth_usd", "Order book within 0.2%", "${:,.0f}"),
        ("book_imbalance", "Order-book imbalance within 0.5% (+1 all bids)", "{:+.2f}"),
        ("vpin", "VPIN toxicity", "{:.2f}"), ("vpin_pctile", "VPIN percentile vs own history", "{:.0%}"),
        ("regime", "Market regime", "{}"), ("market_median_24h", "Median coin 24h", "{:+.2%}"),
        ("confidence", "Strategy confidence", "{:.2f}"), ("strategy", "Strategy", "{}"),
    ):
        if not features or key not in features or features[key] is None:
            continue
        val = features[key]
        try:
            feats.append(f"{label}: {fmt.format(val) if isinstance(val, str) else fmt.format(float(val))}")
        except (TypeError, ValueError):
            continue
    if feats:
        lines.append("; ".join(feats) + ".")
    return "\n".join(lines)


def _p_take(answer: Any) -> Optional[float]:
    if isinstance(answer, Mapping):
        return _num(answer.get("noul"))
    return None


def _quality(answer: Any) -> Optional[float]:
    if isinstance(answer, Mapping):
        return _num(answer.get("score"))
    return None


class MetaLabeler:
    """HTTP client for the sidecar. `assess()` never raises; on any problem it returns no opinion."""

    def __init__(self, url: Optional[str] = None, token: Optional[str] = None, timeout: float = 20.0,
                 runtime_file: Path = RUNTIME_FILE):
        self.url, self.token, self.timeout, self.runtime_file = url, token, timeout, runtime_file

    def _endpoint(self):
        if self.url and self.token:
            return self.url, self.token
        try:
            info = json.loads(Path(self.runtime_file).read_text(encoding="utf-8"))
            return info["url"], info["token"]
        except (OSError, ValueError, KeyError):
            return None, None

    def _call(self, method: str, path: str, body: Optional[dict] = None, timeout: Optional[float] = None) -> dict:
        url, token = self._endpoint()
        if not url:
            raise ConnectionError("decision-model sidecar is not running")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url.rstrip("/") + path, data=data, method=method,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            return json.loads(resp.read())

    def health(self) -> dict:
        try:
            return {"running": True, **self._call("GET", "/health", timeout=3)}
        except Exception as exc:
            return {"running": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    def ask(self, state: str, questions: Optional[dict] = None, models=None, timeout: Optional[float] = None) -> dict:
        return self._call("POST", "/decide", {"state": state, "questions": questions or QUESTIONS,
                                               **({"models": list(models)} if models else {})}, timeout=timeout)

    def assess(self, symbol: str, direction: str, entry: float, stop: float, target: float,
               horizon_hours: float = 4.0, features: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        t0 = time.time()
        out: Dict[str, Any] = {"thx02_p": None, "laya_p": None, "mean_p": None, "quality": None,
                               "errors": {}, "latency_ms": None}
        try:
            res = self.ask(build_state(symbol, direction, entry, stop, target, horizon_hours, features))
        except Exception as exc:
            out["errors"]["sidecar"] = f"{type(exc).__name__}: {exc}"[:200]
            out["latency_ms"] = round((time.time() - t0) * 1000, 1)
            return out
        probs, quals = [], []
        for name in MODEL_NAMES:
            r = (res.get("models") or {}).get(name)
            if not r:
                continue
            if r.get("error"):
                out["errors"][name] = r["error"]
                continue
            answers = r.get("answers") or {}
            p = _p_take(answers.get("take"))
            q = _quality(answers.get("quality"))
            out[f"{name}_p"] = None if p is None else round(p, 4)
            if p is not None:
                probs.append(p)
            if q is not None:
                quals.append(q)
        if probs:
            out["mean_p"] = round(sum(probs) / len(probs), 4)
        if quals:
            out["quality"] = round(sum(quals) / len(quals), 3)   # 0 (very poor) .. 4 (excellent)
        out["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return out


def veto_reason(meta: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The RiskBot veto, or None. Only when enforcement is on AND the models gave an opinion."""
    if not enforce_enabled() or not meta:
        return None
    p = _num(meta.get("mean_p"))
    floor = min_probability()
    if p is None or p >= floor:
        return None
    return f"META_LABEL_SKIP: THX-02/Laya give {p:.0%} that target is hit before stop (minimum {floor:.0%})."


class SidecarManager:
    """Start/stop the model sidecar as a child process of the dashboard. Tokens are never logged.

    On Windows the sidecar runs inside WSL (Ubuntu): Windows Application Control blocks PyTorch's DLLs,
    exactly as it blocks the native C++ / OCaml builds. WSL forwards its 127.0.0.1 ports to Windows.
    Settings travel through WSLENV, so the token never appears on a command line.
    """

    WSL_VENV = os.environ.get("ZILLERS_MODELS_WSL_VENV", "~/.zillers-models-venv")
    WSL_MODELS = os.environ.get("ZILLERS_MODELS_WSL_DIR", "~/zillers-models")

    def __init__(self, port: int = 8950, python: Path = VENV_PY, server: Path = SERVER,
                 runtime_file: Path = RUNTIME_FILE, models_dir: Path = MODELS_DIR, wsl: Optional[bool] = None):
        self.port, self.python, self.server = port, Path(python), Path(server)
        self.runtime_file, self.models_dir = Path(runtime_file), Path(models_dir)
        self.wsl = (os.name == "nt") if wsl is None else wsl
        self.proc: Optional[subprocess.Popen] = None
        self.log_path = self.runtime_file.parent / "models_sidecar.log"
        self._installed_cache: Optional[tuple] = None

    def _wsl_base(self):
        distro = os.environ.get("ZILLERS_WSL_DISTRO")
        return ["wsl.exe", *(["-d", distro] if distro else []), "--exec", "bash", "-lc"]

    def installed(self) -> Dict[str, Any]:
        if not self.wsl:
            weights = {n: (self.models_dir / n).is_dir() and any((self.models_dir / n).rglob("*.safetensors"))
                       for n in MODEL_NAMES}
            return {"venv": self.python.is_file(), "weights": weights, "runtime": "local"}
        if self._installed_cache and time.time() - self._installed_cache[0] < 60:
            return self._installed_cache[1]
        script = (f'ls -d {self.WSL_VENV}/lib/python3*/site-packages/thx02 {self.WSL_VENV}/lib/python3*/site-packages/laya'
                  f' >/dev/null 2>&1 && echo venv; '
                  f'for n in {" ".join(MODEL_NAMES)}; do '
                  f'find {self.WSL_MODELS}/$n -name "*.safetensors" -print -quit 2>/dev/null | grep -q . && echo $n; done')
        try:
            out = subprocess.run([*self._wsl_base(), script], capture_output=True, timeout=30).stdout
            lines = set(out.decode("utf-8", "replace").replace("\x00", "").split())
        except (OSError, subprocess.TimeoutExpired):
            lines = set()
        res = {"venv": "venv" in lines, "weights": {n: n in lines for n in MODEL_NAMES}, "runtime": "wsl"}
        self._installed_cache = (time.time(), res)
        return res

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def command(self) -> list:
        if not self.wsl:
            return [str(self.python), str(self.server)]
        from cryptoscope.execution.shadow_gate import wsl_path
        return [*self._wsl_base(), f'exec {self.WSL_VENV}/bin/python "$1"', "zillers-models", wsl_path(self.server)]

    def start(self) -> Dict[str, Any]:
        inst = self.installed()
        if not inst["venv"] or not any(inst["weights"].values()):
            return {"ok": False, "error": "model venv or weights missing (see scripts/download_decision_models.py)",
                    **inst}
        if self.running():
            return {"ok": True, "already": True}
        # A sidecar from an earlier dashboard run: reuse it if it still answers with our token, else clear it.
        if MetaLabeler(runtime_file=self.runtime_file).health().get("running"):
            return {"ok": True, "already": True, "reused": True}
        if self.wsl:
            try:
                subprocess.run([*self._wsl_base(), "pkill -f models_sidecar/server.py || true"], timeout=15,
                               capture_output=True)
            except (OSError, subprocess.TimeoutExpired):
                pass
        token = secrets.token_urlsafe(24)
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("BINANCE", "TELEGRAM"))}
        settings = {"ZILLERS_SIDECAR_TOKEN": token, "ZILLERS_SIDECAR_PORT": str(self.port),
                    "ZILLERS_MODELS_DIR": self.WSL_MODELS if self.wsl else str(self.models_dir),
                    "ZILLERS_SIDECAR_MODELS": ",".join(n for n, ok in inst["weights"].items() if ok)}
        env.update(settings)
        if self.wsl:
            env["WSLENV"] = ":".join([*(x for x in env.get("WSLENV", "").split(":") if x), *settings])
        self.runtime_file.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "ab")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self.proc = subprocess.Popen(self.command(), env=env, stdout=log, stderr=log,
                                     stdin=subprocess.DEVNULL, cwd=str(ROOT), creationflags=flags)
        info = {"url": f"http://127.0.0.1:{self.port}", "token": token, "pid": self.proc.pid,
                "started_at": time.time(), "runtime": inst.get("runtime")}
        tmp = self.runtime_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(info), encoding="utf-8")
        os.replace(tmp, self.runtime_file)
        return {"ok": True, "pid": self.proc.pid, "runtime": inst.get("runtime")}

    def stop(self) -> None:
        if self.running():
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.wsl:   # ending wsl.exe does not always end the Linux process
            try:
                subprocess.run([*self._wsl_base(), "pkill -f models_sidecar/server.py || true"], timeout=15,
                               capture_output=True)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self.proc = None
        try:
            self.runtime_file.unlink()
        except OSError:
            pass

    def status(self) -> Dict[str, Any]:
        return {"process": self.running(), **self.installed(),
                "health": MetaLabeler(runtime_file=self.runtime_file).health()}
