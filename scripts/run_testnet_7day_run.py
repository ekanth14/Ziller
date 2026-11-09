"""Launch and monitor the 7-day Binance Spot Testnet soak run (Phase 3.4).

Starts the multi-bot orchestrator in background logging to work/logs/testnet_7day_run.log.
Provides status inspection and graceful stop controls.
"""

import argparse
import ctypes
import datetime
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptoscope.orchestrator.__main__ import load_credentials_env
from cryptoscope.security.config import validate_startup

LOG_DIR = ROOT / "work" / "logs"
RUNTIME_DIR = ROOT / "work" / "runtime"
MANIFEST_PATH = RUNTIME_DIR / "testnet_7day_run.json"
LOG_PATH = LOG_DIR / "testnet_7day_run.log"


def is_pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        STILL_ACTIVE = 259
        return exit_code.value == STILL_ACTIVE
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def get_status() -> dict:
    if not MANIFEST_PATH.is_file():
        return {"status": "STOPPED", "running": False, "message": "No active 7-day run manifest found."}
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "ERROR", "running": False, "message": "Corrupt manifest file."}

    pid = manifest.get("pid")
    is_running = is_pid_alive(pid) if pid else False

    manifest["running"] = is_running
    manifest["status"] = "RUNNING" if is_running else "TERMINATED"
    return manifest


def start_run(symbols: list[str]) -> None:
    current = get_status()
    if current.get("running"):
        print(f"[7-DAY RUN] Already active with PID {current.get('pid')}. Use --status to inspect or --stop to end.", flush=True)
        return

    load_credentials_env()
    mode = validate_startup("TESTNET")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ts_str = now_utc.strftime("%m-%d %H:%M:%S UTC")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n=== FLEET 7-DAY TESTNET RUN LAUNCHED AT {ts_str} ===\n")

    symbols_str = " ".join(symbols)
    # On Windows, launch via cmd.exe redirect with CREATE_NO_WINDOW so the handle stays open
    cmd_str = f'"{sys.executable}" -u -m cryptoscope.orchestrator --mode TESTNET --symbols {symbols_str} >> "{LOG_PATH}" 2>&1'

    creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    process = subprocess.Popen(
        cmd_str,
        cwd=str(ROOT),
        shell=True,
        creationflags=creationflags,
    )

    # Let the process spawn and record PID
    time.sleep(1.5)

    # On Windows shell=True, process.pid is cmd.exe. Let's find python child or record process.pid
    manifest = {
        "pid": process.pid,
        "mode": mode,
        "symbols": symbols,
        "started_at": now_utc.isoformat(),
        "target_duration_days": 7,
        "target_duration_seconds": 7 * 86400,
        "planned_end_at": (now_utc + datetime.timedelta(days=7)).isoformat(),
        "log_path": str(LOG_PATH),
        "monitoring_cmd": "python scripts/run_testnet_7day_run.py --status",
        "stop_cmd": "python scripts/run_testnet_7day_run.py --stop",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[7-DAY RUN] Successfully launched background Testnet orchestrator.", flush=True)
    print(f"  PID: {process.pid}", flush=True)
    print(f"  Mode: {mode}", flush=True)
    print(f"  Symbols: {', '.join(symbols)}", flush=True)
    print(f"  Log File: {LOG_PATH}", flush=True)
    print(f"  Target Duration: 7 days (until {manifest['planned_end_at']})", flush=True)
    print(f"  Monitor Command: python scripts/run_testnet_7day_run.py --status", flush=True)


def stop_run() -> None:
    current = get_status()
    if not current.get("running"):
        print("[7-DAY RUN] No active run detected.", flush=True)
        return
    pid = current.get("pid")
    print(f"[7-DAY RUN] Sending termination signal to PID {pid}...", flush=True)
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        print(f"[7-DAY RUN] Orchestrator PID {pid} stopped.", flush=True)
    except Exception as e:
        print(f"[7-DAY RUN] Error stopping process: {e}", flush=True)

    current["status"] = "STOPPED_BY_OPERATOR"
    current["stopped_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    MANIFEST_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="ZILLERS 7-Day Spot Testnet Soak Run")
    parser.add_argument("--start", action="store_true", help="Launch background 7-day run")
    parser.add_argument("--status", action="store_true", help="Inspect status of 7-day run")
    parser.add_argument("--stop", action="store_true", help="Stop background 7-day run")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT"], help="Symbols to trade")
    args = parser.parse_args()

    if args.stop:
        stop_run()
    elif args.status:
        st = get_status()
        print(json.dumps(st, indent=2))
    elif args.start:
        start_run(args.symbols)
    else:
        st = get_status()
        print(json.dumps(st, indent=2))


if __name__ == "__main__":
    main()
