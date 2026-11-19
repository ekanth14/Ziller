"""Start/stop the multi-bot autotrading fleet (cryptoscope.orchestrator) from the dashboard.

- Only PAPER and TESTNET are allowed here. LIVE is never started from the web UI; it stays
  behind the five-gate governor and the orchestrator itself refuses it.
- Exchange keys are read by the orchestrator from .env in its own process; they never pass
  through the browser or this module.
- One fleet at a time. Output goes to work/logs/fleet-<timestamp>.log.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptoscope.trading_universe import filter_symbols

ALLOWED_MODES = {"PAPER", "TESTNET"}
SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")
# Keys the OBSERVE-only dashboard launcher blanks; the fleet must load them from .env itself.
_STRIP_KEYS = ("EXCHANGE_API_KEY", "EXCHANGE_API_SECRET", "BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET",
               "BINANCE_LIVE_API_KEY", "BINANCE_LIVE_API_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_CHAT_ID",
               "TELEGRAM_OWNER_USER_ID", "TRADING_MODE", "LIVE_TRADING")
_SECRETISH = re.compile(r"(api[_-]?key|secret|token|signature)\s*[=:]\s*\S+", re.I)


class FleetManager:
    def __init__(self, root: Path, python: str = sys.executable):
        self.root = Path(root)
        self.python = python
        self._proc: Optional[subprocess.Popen] = None
        self._meta: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def _child_env(self, mode: str) -> Dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in _STRIP_KEYS}
        env.update(TRADING_MODE=mode, LIVE_TRADING="false", PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        # CPU-only Gemma 12B generates ~1 token/s here, so one debate takes ~60-100 s; 35/90 s made them all fail closed.
        env.setdefault("DEBATE_TIMEOUT_SEC", "180")
        return env

    def start(self, mode: str, symbols: List[str], actor: str) -> Dict[str, Any]:
        mode = str(mode or "").upper()
        if mode not in ALLOWED_MODES:
            raise ValueError("Fleet can only be started in PAPER or TESTNET from the dashboard")
        symbols, dropped = filter_symbols(symbols)
        symbols = symbols[:10]
        if not symbols:
            raise ValueError(f"No tradable symbols: {', '.join(dropped)} excluded from autotrading" if dropped
                             else "Provide 1-10 valid symbols")
        if not all(SYMBOL_RE.match(s) for s in symbols):
            raise ValueError("Provide 1-10 valid symbols")
        with self._lock:
            if self._proc and self._proc.poll() is None:
                raise RuntimeError("Fleet is already running; stop it first")
            logs = self.root / "work" / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            log_path = logs / f"fleet-{time.strftime('%Y%m%d-%H%M%S')}.log"
            handle = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 - owned by the child for its lifetime
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            self._proc = subprocess.Popen(
                [self.python, "-B", "-m", "cryptoscope.orchestrator", "--mode", mode, "--symbols", *symbols],
                cwd=str(self.root), env=self._child_env(mode), stdout=handle, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=flags,
            )
            self._meta = {"mode": mode, "symbols": symbols, "started_at": time.time(), "started_by": actor,
                          "log": str(log_path.relative_to(self.root)), "pid": self._proc.pid}
        return self.status()

    def notify(self, text: str) -> Dict[str, Any]:
        """Send one Telegram message via a child process (the dashboard never holds the token)."""
        try:
            out = subprocess.run([self.python, "-B", "-m", "cryptoscope.telegram.notify", "--text", text], cwd=str(self.root),
                                 env={k: v for k, v in os.environ.items() if not k.startswith("TELEGRAM_")},
                                 capture_output=True, text=True, timeout=20)
            import json as _json
            return _json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else {"ok": False, "error": "no output"}
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__}

    def stop(self, timeout: float = 15.0, reason: str = "stopped from the dashboard") -> Dict[str, Any]:
        with self._lock:
            proc = self._proc
        if not proc or proc.poll() is not None:
            return self.status()
        try:
            if os.name == "nt":
                # CTRL_BREAK reaches the new process group and lets asyncio unwind; hard kill only as fallback.
                import signal
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
            proc.wait(timeout=timeout)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)
        with self._lock:
            self._meta["stopped_at"] = time.time()
            meta = dict(self._meta)
        threading.Thread(target=self.notify, daemon=True, args=(
            f"⏹️ <b>Autotrader fleet stopped</b>\nMode: {meta.get('mode')} · reason: {reason}",)).start()
        return self.status()

    def tail(self, lines: int = 40) -> List[str]:
        log = self._meta.get("log")
        if not log:
            return []
        path = self.root / log
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 16000))
                text = f.read().decode("utf-8", errors="replace")
        except OSError:
            return []
        return [_SECRETISH.sub(r"\1=<redacted>", ln) for ln in text.splitlines()[-lines:]]

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._proc and self._proc.poll() is None)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            proc, meta = self._proc, dict(self._meta)
        running = bool(proc and proc.poll() is None)
        out = {"running": running, "allowed_modes": sorted(ALLOWED_MODES), **meta}
        if proc and not running:
            out["exit_code"] = proc.returncode
        if running:
            out["uptime_s"] = round(time.time() - meta["started_at"])
        out["log_tail"] = self.tail()
        return out
