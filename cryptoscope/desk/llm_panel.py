"""Local LLM panel: every installed Ollama chat model gives a BUY/HOLD/SELL view on the latest closed bar.

Ollama on CPU takes ~10-60 s per answer, so calls never block the dashboard:
- a single background worker processes one model at a time;
- answers are cached per (model, symbol, interval, bar time) and reused until a new bar closes;
- only the newest request per (symbol, interval) is kept in the queue.

The prompt contains only numbers computed from real exchange candles. Answers are parsed as
strict JSON; anything else is recorded as an error, never guessed.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

ACTIONS = {"BUY", "HOLD", "SELL"}
PROMPT = (
    "You are one analyst on a crypto spot trading desk. Use ONLY the numbers below; do not invent data.\n"
    "Long-only spot account: BUY opens/keeps a long, SELL exits to cash, HOLD keeps the current state.\n"
    "Market {symbol} on {interval} bars, last closed bar {bar}:\n{facts}\n"
    'Reply with JSON only: {{"action":"BUY|HOLD|SELL","confidence":0.0-1.0,"reason":"max 25 words"}}'
)


def _facts(desk: Dict[str, Any]) -> str:
    t, r, dec = desk["ticker"], desk["risk"], desk["decision"]

    def f(v, pct=False, nd=2):
        if v is None:
            return "n/a"
        return f"{v * 100:+.{nd}f}%" if pct else f"{v:,.{nd}f}"

    lines = [
        f"close {f(t['close'], nd=6 if t['close'] < 1 else 2)}; change {f(t['chg'], True)}",
        f"SMA10 {f(t['sma10'])}, SMA30 {f(t['sma30'])}; 20-bar return {f(t['r20'], True)}",
        f"RSI14 {f(t['rsi14'], nd=1)}; MACD histogram {f(t['macd_hist'], nd=4)}; Bollinger %b {f(t['bb_pct'])}",
        f"volume vs 20-bar average {f(t['vol_ratio'])}x; drawdown from peak {f(t['dd'], True)}",
        f"ATR14 {f(r['atr14'])}; annualised volatility {f(r['vol20'], True, 1)}; 1-bar VaR95 {f(r['var95_1d'], True)}",
        "rule models: " + ", ".join(f"{k} {v:+d}" for k, v in dec["votes"].items()) + f"; PM {dec['action']} score {dec['score']:+.2f}",
        f"desk position: {'long since ' + str(desk['position']['sessions']) + ' bars' if desk.get('position') else 'flat'}",
    ]
    return "\n".join("- " + ln for ln in lines)


class LLMPanel:
    def __init__(self, host: Optional[str] = None, models: Optional[List[str]] = None, timeout: float = 180.0,
                 cache_size: int = 300, discover_ttl: float = 300.0, gate=None):
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").strip().rstrip("/")
        if not self.host.startswith(("http://", "https://")):  # Ollama accepts a bare host:port in OLLAMA_HOST
            self.host = "http://" + self.host
        env_models = [m.strip() for m in os.environ.get("ZILLERS_LLM_MODELS", "").split(",") if m.strip()]
        self.fixed_models = models or env_models or None
        self.timeout = timeout
        self.cache_size = cache_size
        self.discover_ttl = discover_ttl
        self._models: tuple[float, List[str]] = (0.0, [])
        self._cache: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()
        self._queue: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()  # (symbol, interval) -> job
        self._busy: Optional[tuple] = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._worker: Optional[threading.Thread] = None
        # gate() -> False while the master kill switch is engaged; no model is called then.
        self.gate = gate or (lambda: True)

    # ---------------------------------------------------------- discovery
    def models(self) -> List[str]:
        if self.fixed_models:
            return list(self.fixed_models)
        now = time.time()
        if now - self._models[0] < self.discover_ttl:
            return list(self._models[1])
        try:
            with urlopen(Request(self.host + "/api/tags"), timeout=5) as resp:  # noqa: S310 - local Ollama
                tags = json.loads(resp.read())["models"]
            # chat models only: skip embedding/classifier models (e.g. the ModernBERT Laya head)
            names = [m["name"] for m in tags
                     if "bert" not in str(m.get("details", {}).get("family", "")).lower()
                     and not str(m.get("details", {}).get("parameter_size", "")).upper().endswith("M")]
        except Exception:
            names = []
        self._models = (now, names)
        return list(names)

    # ---------------------------------------------------------- public API
    def halt(self) -> Dict[str, Any]:
        """Kill switch: drop every queued job and unload all models from Ollama memory."""
        with self._lock:
            dropped = sum(len(j["models"]) for j in self._queue.values())
            self._queue.clear()
        unloaded = []
        try:
            with urlopen(Request(self.host + "/api/ps"), timeout=5) as resp:  # noqa: S310 - local Ollama
                loaded = [m["name"] for m in json.loads(resp.read()).get("models", [])]
            for name in loaded:
                body = json.dumps({"model": name, "keep_alive": 0}).encode()
                with urlopen(Request(self.host + "/api/generate", data=body, headers={"Content-Type": "application/json"}), timeout=15):  # noqa: S310
                    unloaded.append(name)
        except Exception:
            pass
        return {"queued_jobs_dropped": dropped, "models_unloaded": unloaded}

    def request(self, symbol: str, interval: str, bar_time: float, desk: Dict[str, Any]) -> Dict[str, Any]:
        """Return what is known now; schedule missing answers for this bar in the background."""
        if not self.gate():
            return {"models": [], "ready": 0, "total": 0, "panel_action": None, "host": self.host,
                    "available": False, "halted": True}
        models = self.models()
        results, missing = [], []
        with self._lock:
            for m in models:
                hit = self._cache.get((m, symbol, interval, bar_time))
                if hit:
                    results.append(hit)
                else:
                    state = "running" if self._busy == (m, symbol, interval, bar_time) else "queued"
                    results.append({"model": m, "status": state})
                    missing.append(m)
            if missing:
                self._queue.pop((symbol, interval), None)
                self._queue[(symbol, interval)] = {"symbol": symbol, "interval": interval, "bar_time": bar_time,
                                                   "prompt": PROMPT.format(symbol=symbol, interval=interval, bar=int(bar_time),
                                                                           facts=_facts(desk)), "models": missing}
                while len(self._queue) > 6:
                    self._queue.popitem(last=False)
        if missing:
            self._ensure_worker()
            self._wake.set()
        ready = [r for r in results if r.get("status") == "ready"]
        votes = [r["action"] for r in ready]
        panel = max(ACTIONS, key=lambda a: (votes.count(a), a == "HOLD")) if votes else None
        return {"models": results, "ready": len(ready), "total": len(models), "panel_action": panel,
                "host": self.host, "available": bool(models)}

    # ---------------------------------------------------------- worker
    def _ensure_worker(self):
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._run, name="llm-panel", daemon=True)
            self._worker.start()

    def _run(self):
        while True:
            self._wake.wait(30)
            self._wake.clear()
            while True:
                with self._lock:
                    if not self.gate():
                        self._queue.clear()
                    if not self._queue:
                        break
                    key, job = self._queue.popitem(last=True)  # newest first
                    model = job["models"].pop(0)
                    if job["models"]:
                        self._queue[key] = job
                    ck = (model, job["symbol"], job["interval"], job["bar_time"])
                    if ck in self._cache:
                        continue
                    self._busy = ck
                result = self._ask(model, job["prompt"])
                with self._lock:
                    self._busy = None
                    if not self.gate():  # kill switch engaged while the model was answering: discard
                        continue
                    self._cache[ck] = result
                    while len(self._cache) > self.cache_size:
                        self._cache.popitem(last=False)

    def _ask(self, model: str, prompt: str) -> Dict[str, Any]:
        started = time.perf_counter()
        body = {"model": model, "prompt": prompt, "format": "json", "stream": False, "think": False,
                "options": {"temperature": 0, "num_predict": 160}, "keep_alive": "2m"}
        try:
            req = Request(self.host + "/api/generate", data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - local Ollama
                out = json.loads(resp.read())
            parsed = json.loads(out.get("response") or "")
            action = str(parsed.get("action", "")).strip().upper()
            if action not in ACTIONS:
                raise ValueError("action outside BUY/HOLD/SELL")
            conf = float(parsed.get("confidence", 0))
            return {"model": model, "status": "ready", "action": action,
                    "confidence": max(0.0, min(1.0, conf)), "reason": str(parsed.get("reason", ""))[:240],
                    "latency_ms": round((time.perf_counter() - started) * 1000), "answered_at": time.time()}
        except Exception as exc:
            return {"model": model, "status": "error", "error": type(exc).__name__,
                    "latency_ms": round((time.perf_counter() - started) * 1000), "answered_at": time.time()}
