"""Enforce architectural isolation: ONLY ExecutionBot may import exchange or broker execution clients.
Extended for Phase 9: Ensures all new evaluation modules maintain strict AST isolation and do not read keys.
"""

import ast
import os
from pathlib import Path
import pytest

FORBIDDEN_MODULE_SUBSTRINGS = [
    "paper_broker",
    "governor",
    "binance_testnet",
    "ccxt",
    "binance.client",
    "providers.binance",
]


def test_only_execution_bot_imports_exchange_clients():
    check_dirs = [
        Path("cryptoscope/orchestrator/bots"),
        Path("cryptoscope/telegram"),
        Path("cryptoscope/agents"),
        Path("cryptoscope/security"),
        Path("cryptoscope/backtesting"),
        Path("cryptoscope/ops"),
        Path("cryptoscope/execution/accounting.py"),
        Path("cryptoscope/execution/lifecycle.py"),
        Path("cryptoscope/providers/deadline_http.py"),
        Path("cryptoscope/research/eval"),
        Path("cryptoscope/research/laya"),
        Path("cryptoscope/research/multi_coin"),
    ]

    violations = []

    for d in check_dirs:
        assert d.exists(), f"Directory or file {d} must exist"
        for py_file in ([d] if d.is_file() else d.rglob("*.py")):
            if py_file.name in {"__init__.py", "execution_bot.py"}:
                continue  # ExecutionBot is permitted; __init__ is package manifest

            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in FORBIDDEN_MODULE_SUBSTRINGS:
                            if forbidden in alias.name:
                                violations.append(f"{py_file.name}: imports '{alias.name}' (line {node.lineno})")
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for forbidden in FORBIDDEN_MODULE_SUBSTRINGS:
                        if forbidden in mod:
                            violations.append(f"{py_file.name}: from '{mod}' import ... (line {node.lineno})")

    assert len(violations) == 0, f"Architecture violation: Non-execution bots imported broker/exchange client:\n" + "\n".join(violations)


def test_execution_bot_does_import_broker_client():
    exec_bot_file = Path("cryptoscope/orchestrator/bots/execution_bot.py")
    assert exec_bot_file.exists()

    with open(exec_bot_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Confirms ExecutionBot actually wires the execution layer
    assert "PaperBroker" in content
    assert "LiveMultiGateGovernor" in content
    assert "BinanceTestnetClient" in content


def test_evaluation_modules_do_not_access_env_secrets():
    """Verify that none of the Phase 9 evaluation modules read sensitive environment keys."""
    eval_dir = Path("cryptoscope/research/eval")
    assert eval_dir.exists()

    forbidden_strings = [
        "BINANCE_TESTNET_API_SECRET",
        "BINANCE_API_SECRET",
        "BINANCE_TESTNET_API_KEY",
        "BINANCE_API_KEY",
        "ADMIN_PASSWORD",
        "COLLAB_DESK_PASSCODE",
    ]

    violations = []
    for py_file in eval_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        code = py_file.read_text(encoding="utf-8")
        for forbidden in forbidden_strings:
            if forbidden in code:
                violations.append(f"{py_file.name} contains reference to secret '{forbidden}'")

    assert len(violations) == 0, f"Secrets violation in evaluation modules:\n" + "\n".join(violations)
