"""Automated security test ensuring zero secret fragments appear in reports or log files.

Fails if any full secret, password, key, or 8+ char prefix/suffix appears in:
- work/reports/*.md, *.json, *.csv, *.txt
- Any .log files
Complies with Absolute Rule 2 and Master Prompt Item A8.
"""

import os
from pathlib import Path
import pytest


def get_configured_secrets() -> dict[str, str]:
    secrets = {}
    for fn in [".env", "credentials.env"]:
        if os.path.exists(fn):
            for line in open(fn, encoding="utf-8", errors="ignore"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    if len(v) >= 8 and any(w in k.lower() for w in ["key", "secret", "token", "password"]):
                        secrets[k] = v
    return secrets


def test_reports_and_logs_contain_zero_secret_fragments():
    """Verify that no report or log file contains secrets or secret fragments."""
    secrets = get_configured_secrets()
    if not secrets:
        pytest.skip("No secrets configured in environment files to test against.")

    reports_dir = Path("work/reports")
    files_to_check = []

    if reports_dir.exists():
        for p in reports_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in [".md", ".json", ".csv", ".txt", ".html"]:
                files_to_check.append(p)

    # Also check any .log files in work/
    work_dir = Path("work")
    if work_dir.exists():
        for p in work_dir.rglob("*.log"):
            if p.is_file():
                files_to_check.append(p)

    violations = []
    for filepath in files_to_check:
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for var_name, secret_val in secrets.items():
            # Check full secret
            if secret_val in content:
                violations.append(f"{filepath}: leaked full value of {var_name}")
            # Check 8-character prefix/suffix fragments
            elif len(secret_val) >= 16:
                prefix = secret_val[:8]
                suffix = secret_val[-8:]
                if prefix in content:
                    violations.append(f"{filepath}: leaked prefix fragment of {var_name}")
                if suffix in content:
                    violations.append(f"{filepath}: leaked suffix fragment of {var_name}")

    assert not violations, (
        f"A8 Security violation: Found {len(violations)} secret leak(s) in reports/logs:\n"
        + "\n".join(violations)
    )
