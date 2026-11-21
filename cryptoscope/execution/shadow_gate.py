"""Shadow-check bridge to the OCaml risk gate (ocaml/risk_gate).

The OCaml program is an independent, strongly-typed re-implementation of
RiskGovernor.check_pre_trade. It NEVER replaces the Python governor and has no
authority over orders: this module only compares its verdict against the Python
verdict so divergences between the two implementations are caught early.

The binary is optional. Build it with:
    cd ocaml/risk_gate && dune build
or, on Windows hosts where Application Control blocks native compilers, inside WSL:
    wsl -d Ubuntu --exec sh ocaml/risk_gate/build_wsl.sh      (needs `sudo apt install ocaml`)
or point ZILLERS_RISK_GATE_BIN at a built executable. A Linux (ELF) binary found on Windows is
run through `wsl.exe --exec`; ZILLERS_WSL_DISTRO picks the distribution (default: WSL's default).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN = set("|,=\n\r")


def find_binary() -> Optional[Path]:
    env = os.environ.get("ZILLERS_RISK_GATE_BIN")
    names = ["main.exe", "main"] if not sys.platform.startswith("win") else ["main.exe"]
    candidates = [Path(env)] if env else []
    for n in names:
        candidates.append(_ROOT / "ocaml" / "risk_gate" / "_build" / "default" / "bin" / n)
    candidates.append(_ROOT / "ocaml" / "risk_gate" / "_build" / "wsl" / "zillers-risk-gate")
    for c in candidates:
        if c.is_file():
            return c
    found = shutil.which("zillers-risk-gate")
    return Path(found) if found else None


def _is_elf(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


def wsl_path(path: Path) -> str:
    r"""C:\Users\x y\f -> /mnt/c/Users/x y/f (WSL's default automount)."""
    p = Path(path).resolve()
    return f"/mnt/{p.drive.rstrip(':').lower()}/" + "/".join(p.parts[1:])


def gate_command(binary: Path) -> List[str]:
    """argv that runs the gate. A Linux binary on Windows runs via WSL with --exec (no shell, so no quoting)."""
    if sys.platform.startswith("win") and _is_elf(binary):
        distro = os.environ.get("ZILLERS_WSL_DISTRO")
        return ["wsl.exe", *(["-d", distro] if distro else []), "--exec", wsl_path(binary)]
    return [str(binary)]


def _num(x: float) -> str:
    return repr(float(x))


def _clean(value: str) -> str:
    if any(ch in _FORBIDDEN for ch in value):
        raise ValueError(f"unsupported character in field value: {value!r}")
    return value


def build_line(
    governor: Any,
    symbol: str,
    action: str,
    requested_value: float,
    total_portfolio_equity: float,
    current_open_orders_count: int,
    feed_age_seconds: float,
    cross_source_divergence_pct: float,
    day_pnl: float,
    day_start_equity: float,
    now: float,
    token_audit: Optional[Dict[str, Any]] = None,
) -> str:
    """Serialize governor config + state + request for the OCaml gate."""
    g = governor
    allow = ",".join(sorted(_clean(s) for s in g.symbol_allowlist))
    stamps = ",".join(_num(t) for t in g.trade_timestamps)
    last_loss = "none" if g.last_loss_time is None else _num(g.last_loss_time)
    fields = {
        "cfg.max_position_fraction": _num(g.max_position_fraction),
        "cfg.max_open_orders": str(int(g.max_open_orders)),
        "cfg.daily_loss_limit_fraction": _num(g.daily_loss_limit_fraction),
        "cfg.total_drawdown_limit_fraction": _num(g.total_drawdown_limit_fraction),
        "cfg.max_trades_per_day": str(int(g.max_trades_per_day)),
        "cfg.loss_cooldown_seconds": _num(g.loss_cooldown_seconds),
        "cfg.symbol_allowlist": allow,
        "cfg.max_feed_age_seconds": _num(g.max_feed_age_seconds),
        "cfg.max_divergence_pct": _num(g.max_divergence_pct),
        "st.emergency_halted": "1" if g.emergency_halted else "0",
        "st.peak_equity": _num(g.peak_equity),
        "st.trade_timestamps": stamps,
        "st.last_loss_time": last_loss,
        "req.symbol": _clean(symbol),
        "req.action": _clean(action),
        "req.requested_value": _num(requested_value),
        "req.total_portfolio_equity": _num(total_portfolio_equity),
        "req.open_orders": str(int(current_open_orders_count)),
        "req.feed_age_seconds": _num(feed_age_seconds),
        "req.cross_source_divergence_pct": _num(cross_source_divergence_pct),
        "req.day_pnl": _num(day_pnl),
        "req.day_start_equity": _num(day_start_equity),
        "req.now": _num(now),
    }
    if token_audit:
        fields["req.token_present"] = "1"
        fields["req.token_band"] = _clean(str(token_audit.get("band", "OK")))
        fields["req.token_score"] = _num(token_audit.get("score", 70))
    return "|".join(f"{k}={v}" for k, v in fields.items())


@dataclass
class GateVerdict:
    allowed: bool
    codes: List[str]
    halted: bool
    peak_equity: float
    error: Optional[str] = None


def parse_output(line: str) -> GateVerdict:
    parts = line.strip().split("|")
    if parts[0] == "ERROR" or parts[0] not in {"ALLOW", "REJECT"}:
        return GateVerdict(False, [], False, 0.0, error=line.strip())
    kv = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
    codes = [c for c in kv.get("reasons", "").split(",") if c]
    return GateVerdict(parts[0] == "ALLOW", codes, kv.get("halted") == "1", float(kv["peak"]))


def run_gate(lines: List[str], binary: Optional[Path] = None, timeout: float = 30.0) -> List[GateVerdict]:
    binary = binary or find_binary()
    if binary is None:
        raise FileNotFoundError("OCaml risk gate binary not found (see module docstring)")
    # Bytes, not text mode: on Windows text mode turns "\n" into "\r\n" on the way in.
    proc = subprocess.run(
        gate_command(binary), input=("\n".join(lines) + "\n").encode("utf-8"), capture_output=True,
        timeout=timeout, check=False,
    )
    stdout, stderr = proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")
    out = [parse_output(x) for x in stdout.splitlines() if x.strip()]
    if len(out) != len(lines):
        raise RuntimeError(f"gate returned {len(out)} lines for {len(lines)} requests: {stderr[:200]}")
    return out


@dataclass
class ShadowResult:
    match: bool
    python_allowed: bool
    python_codes: List[str]
    gate: GateVerdict
    differences: List[str] = field(default_factory=list)


def shadow_check(governor: Any, binary: Optional[Path] = None, now: Optional[float] = None, **request: Any) -> ShadowResult:
    """Run the Python governor and the OCaml gate on the same input and compare.

    The Python governor is called normally (including its halt side effects); the OCaml
    gate receives a snapshot of the governor state taken BEFORE that call.
    """
    now = time.time() if now is None else now
    line = build_line(governor, now=now, **request)
    allowed, reasons = governor.check_pre_trade(now=now, **request)
    py_codes = [r.split(":", 1)[0] for r in reasons]
    gate = run_gate([line], binary)[0]
    diffs: List[str] = []
    if gate.error:
        diffs.append(f"gate error: {gate.error}")
    else:
        if gate.allowed != allowed:
            diffs.append(f"verdict python={allowed} ocaml={gate.allowed}")
        if gate.codes != py_codes:
            diffs.append(f"codes python={py_codes} ocaml={gate.codes}")
        if gate.halted != bool(governor.emergency_halted):
            diffs.append(f"halt python={governor.emergency_halted} ocaml={gate.halted}")
        if gate.peak_equity != governor.peak_equity:
            diffs.append(f"peak python={governor.peak_equity} ocaml={gate.peak_equity}")
    return ShadowResult(not diffs, allowed, py_codes, gate, diffs)
