"""Decision-model sidecar: real THX-02 and Laya behind a token-protected HTTP endpoint on 127.0.0.1.

Runs ONLY in the isolated `.venv-models` (torch + laya + thx02), never in the dashboard process:

    .venv-models/Scripts/python.exe cryptoscope/models_sidecar/server.py

Environment
    ZILLERS_SIDECAR_TOKEN   required; every request must send `Authorization: Bearer <token>`
    ZILLERS_SIDECAR_PORT    default 8950 (the server always binds 127.0.0.1, never all interfaces)
    ZILLERS_MODELS_DIR      default work/models (weights downloaded by scripts/download_decision_models.py)
    ZILLERS_SIDECAR_MODELS  default "thx02,laya"
    ZILLERS_SIDECAR_PRELOAD "1" loads every model at start-up instead of on first use

API
    GET  /health  -> {"models": {name: {loaded, loading, error, load_s}}}
    POST /decide  {"state": str|dict, "questions": {...}, "models": [optional subset]}
               -> {"models": {name: {"answers": {...}, "latency_ms": float} | {"error": str}}}

Both models answer the same typed questions ("noul" yes/no, "score", "choice") with probabilities over
the options they are given. Neither writes free text here: THX-02 runs with think=False (its thinker
needs a GPU vLLM server), Laya never generates text.
"""
from __future__ import annotations

import hmac
import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = Path(os.path.expanduser(os.environ.get("ZILLERS_MODELS_DIR") or str(ROOT / "work" / "models")))
HOST = "127.0.0.1"
MAX_BODY = 64 * 1024


def _load_thx02():
    from thx02 import THX02
    return THX02.load(str(MODELS_DIR / "thx02"), device="cpu")


def _load_laya():
    import laya
    # typed-decisions is the checkpoint fine-tuned for noul/score/choice questions (card: 0.766 vs 0.362 base)
    return laya.load(str(MODELS_DIR / "laya"), device="cpu", subfolder="typed-decisions")


def _ask_thx02(model, state, questions):
    out = model.decide(state, questions, think=False)
    return out.get("answers", {})


def _ask_laya(model, state, questions):
    out = model.predict(state, questions)
    return out.get("answers", out)


LOADERS = {"thx02": (_load_thx02, _ask_thx02), "laya": (_load_laya, _ask_laya)}


class Slot:
    """One model: loaded once, used by one request at a time (neither runtime is documented thread-safe)."""

    def __init__(self, name):
        self.name, self.model, self.error, self.load_s = name, None, None, None
        self.loading = False
        self._load_lock, self._use_lock = threading.Lock(), threading.Lock()

    def get(self):
        if self.model is not None:
            return self.model
        with self._load_lock:
            if self.model is None:
                self.loading, t0 = True, time.time()
                try:
                    self.model = LOADERS[self.name][0]()
                    self.error = None
                except Exception as exc:  # report, do not crash the server
                    self.error = f"{type(exc).__name__}: {exc}"[:300]
                    traceback.print_exc()
                finally:
                    self.loading, self.load_s = False, round(time.time() - t0, 1)
        if self.model is None:
            raise RuntimeError(self.error or "model failed to load")
        return self.model

    def ask(self, state, questions):
        model = self.get()
        with self._use_lock:
            t0 = time.time()
            answers = LOADERS[self.name][1](model, state, questions)
            return {"answers": answers, "latency_ms": round((time.time() - t0) * 1000, 1)}

    def health(self):
        return {"loaded": self.model is not None, "loading": self.loading, "error": self.error, "load_s": self.load_s}


def make_handler(slots, token):
    class Handler(BaseHTTPRequestHandler):
        server_version = "zillers-models/1"

        def log_message(self, fmt, *args):  # quiet: one line per request on stderr is enough
            sys.stderr.write("%s %s\n" % (self.command, self.path))

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self):
            got = self.headers.get("Authorization", "")
            return hmac.compare_digest(got.encode(), f"Bearer {token}".encode())

        def do_GET(self):
            if not self._authorised():
                return self._send(401, {"error": "unauthorised"})
            if self.path == "/health":
                return self._send(200, {"models": {n: s.health() for n, s in slots.items()}, "pid": os.getpid()})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authorised():
                return self._send(401, {"error": "unauthorised"})
            if self.path != "/decide":
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                return self._send(413, {"error": "body must be 1..65536 bytes"})
            try:
                req = json.loads(self.rfile.read(n))
                state, questions = req["state"], req["questions"]
                if not isinstance(questions, dict) or not 1 <= len(questions) <= 16:
                    raise ValueError("questions must be an object with 1..16 entries")
            except (ValueError, KeyError, TypeError) as exc:
                return self._send(400, {"error": str(exc)[:200]})
            wanted = [m for m in (req.get("models") or list(slots)) if m in slots]
            out = {}
            for name in wanted:
                try:
                    out[name] = slots[name].ask(state, questions)
                except Exception as exc:
                    out[name] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
            self._send(200, {"models": out})

    return Handler


def main():
    token = os.environ.get("ZILLERS_SIDECAR_TOKEN", "")
    if len(token) < 16:
        sys.exit("ZILLERS_SIDECAR_TOKEN (>= 16 chars) is required")
    port = int(os.environ.get("ZILLERS_SIDECAR_PORT", "8950"))
    names = [n.strip() for n in os.environ.get("ZILLERS_SIDECAR_MODELS", "thx02,laya").split(",") if n.strip() in LOADERS]
    os.environ.setdefault("USE_TF", "0")             # Laya card: transformers can hang if TensorFlow is present
    os.environ.setdefault("HF_HUB_OFFLINE", "1")     # weights are local; never fetch at run time
    # THX-02 loads in float32 on CPU unless told otherwise: 4.5 B params x 4 bytes ~ 18 GB, more than
    # WSL's default memory. bfloat16 halves that (~9 GB), as the THX-02 card's CPU figures assume.
    os.environ.setdefault("THX02_CPU_DTYPE", "bfloat16")
    try:
        import torch
        torch.set_num_threads(max(1, min(8, (os.cpu_count() or 4) - 2)))
    except Exception:
        pass
    slots = {n: Slot(n) for n in names}
    if os.environ.get("ZILLERS_SIDECAR_PRELOAD", "1") == "1":
        # One after the other (smallest first): loading both at once can double the peak memory.
        order = sorted(slots.values(), key=lambda s: s.name != "laya")
        threading.Thread(target=lambda: [_safe(s.get) for s in order], daemon=True, name="preload").start()
    httpd = ThreadingHTTPServer((HOST, port), make_handler(slots, token))
    print(f"zillers decision-model sidecar on http://{HOST}:{port} models={names}", flush=True)
    httpd.serve_forever()


def _safe(fn):
    try:
        fn()
    except Exception:
        pass


if __name__ == "__main__":
    main()
