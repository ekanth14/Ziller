"""Enforce architectural isolation: ONLY ExecutionBot may import exchange or broker execution clients."""

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
    ]

    violations = []

    for d in check_dirs:
        assert d.exists(), f"Directory {d} must exist"
        for py_file in d.rglob("*.py"):
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
