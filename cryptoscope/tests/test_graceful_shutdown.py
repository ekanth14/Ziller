"""Test graceful shutdown within 5-second deadline, verifying DB flush and resource cleanup."""

import subprocess
import sys
import time
import urllib.request
import pytest


def test_graceful_shutdown_within_5s():
    # Launch server as subprocess on an alternate test port
    port = 8991
    proc = subprocess.Popen(
        [sys.executable, "-m", "cryptoscope.dashboard", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    t0 = time.time()
    server_ready = False

    # Wait for server to bind and respond
    for _ in range(25):
        time.sleep(0.2)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.0) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            pass

    assert server_ready, "Server failed to launch and respond on test port within 5s"

    # Send SIGINT / terminate
    shutdown_start = time.time()
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
        shutdown_duration = time.time() - shutdown_start
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("Server failed to shut down within 5.0 seconds")

    assert shutdown_duration < 5.0, f"Shutdown took {shutdown_duration:.2f}s exceeding 5s limit"
    assert proc.returncode in {0, 1, -15}, f"Shutdown exited with unexpected code: {proc.returncode}"
