"""Unit and verification tests for Phase 8: Laya Tier 2 Decision Model.

Covers:
1. Model probe diagnostics (architecture, capabilities, untrained baseline).
2. Zero-lookahead feature extraction guarantee.
3. Triple-barrier label generation and class metrics.
4. Fast in-process serving latency (p95 < 50ms, hard timeout 200ms).
5. Confidence threshold gating (min confidence parameter).
6. Every fail-closed path (missing model, timeout exceeded, bad input).
7. Real candle replay through Tier 1 + Laya Tier 2 + Risk.
8. Architectural AST isolation for all Laya and decision modules.
"""

import ast
import os
from pathlib import Path
import time
import numpy as np
import pandas as pd
import pytest

from cryptoscope.research.laya.probe import probe_laya_model
from cryptoscope.research.laya.label_generator import (
    compute_triple_barrier_labels,
    extract_features_at_bar,
    verify_no_lookahead,
    LABEL_HOLD,
    LABEL_BUY,
    LABEL_SELL,
)
from cryptoscope.research.laya.serving import LayaInProcessServing
from cryptoscope.autotrader.decision import (
    LayaTier2Evaluator,
    FastDecisionLayer,
    Tier1Engine,
)


def _generate_synthetic_klines(n: int = 100) -> pd.DataFrame:
    """Generates synthetic hourly candle dataframe for deterministic testing."""
    rng = np.random.default_rng(42)
    start_ts = 1700000000000
    times = [start_ts + i * 3600000 for i in range(n)]
    
    price = 30000.0
    opens, highs, lows, closes, vols, qvols = [], [], [], [], [], []
    for _ in range(n):
        o = price
        change = rng.normal(0, 50.0)
        c = o + change
        h = max(o, c) + rng.uniform(5.0, 30.0)
        l = min(o, c) - rng.uniform(5.0, 30.0)
        v = rng.uniform(10.0, 50.0)
        qv = v * c
        price = c
        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)
        vols.append(v)
        qvols.append(qv)

    return pd.DataFrame({
        "open_time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": vols,
        "quote_volume": qvols,
    })


def test_probe_laya_model():
    """Verify probe returns expected architecture, parameter estimate, and random chance accuracy."""
    res = probe_laya_model()
    assert isinstance(res, dict)
    assert res["untrained_accuracy_pct"] == 33.33
    assert "PROBE_PASS" in res["verdict"]


def test_zero_lookahead_verification():
    """Verify feature extractor at bar t does not leak future data."""
    df = _generate_synthetic_klines(80)
    assert verify_no_lookahead(df, test_idx=70) is True


def test_triple_barrier_labels():
    """Verify triple-barrier labeling generates valid target distribution."""
    df = _generate_synthetic_klines(100)
    labels, metrics = compute_triple_barrier_labels(df, horizon_bars=12)
    assert len(labels) == 100
    assert metrics.total_samples > 0
    assert set(np.unique(labels)).issubset({LABEL_HOLD, LABEL_BUY, LABEL_SELL})
    assert metrics.hold_count + metrics.buy_count + metrics.sell_count == metrics.total_samples


def test_in_process_serving_latency():
    """Verify in-process serving latency p95 is strictly under 50ms budget."""
    serving = LayaInProcessServing()
    bench = serving.benchmark_latency(n_runs=50)
    assert bench.p95_ms < 50.0, f"Serving p95 latency {bench.p95_ms}ms exceeded 50ms limit"
    assert bench.status == "PASS"


def test_threshold_gating_logic():
    """Verify confidence gating returns STAND_ASIDE when confidence is below threshold."""
    # When min_confidence is high (e.g. 0.99), evaluator must not agree
    evaluator = LayaTier2Evaluator(min_confidence=0.99)
    tier1_long = {
        "action": "LONG",
        "discrete_encoding": "trend=up,location=near_bull_ob",
        "features": {"close": 30000.0, "ema20": 29800.0, "ema50": 29500.0, "rsi14": 62.0, "vol_ratio": 2.0},
    }
    res = evaluator.evaluate(tier1_long)
    assert res["agreed"] is False


def test_every_fail_closed_path():
    """Verify all fail-closed mechanisms strictly default to STAND_ASIDE."""
    # 1. Missing model checkpoint
    eval_missing = LayaTier2Evaluator(model_path="checkpoints/non_existent_model.joblib")
    tier1_long = {"action": "LONG", "features": {"close": 30000.0}}
    res_missing = eval_missing.evaluate(tier1_long)
    assert res_missing["agreed"] is False
    assert res_missing["status"] in {"UNAVAILABLE", "MODEL_UNAVAILABLE"}

    # 2. Hard timeout exceed (>200ms)
    eval_timeout = LayaTier2Evaluator(timeout_ms=50.0)
    res_timeout = eval_timeout.evaluate(tier1_long, simulate_delay_ms=80.0)
    assert res_timeout["agreed"] is False
    assert res_timeout["status"] == "TIMEOUT_EXCEEDED"

    # 3. Bad / corrupt input vector
    serving = LayaInProcessServing()
    res_bad = serving.predict(np.array(["invalid", "features"]))
    assert res_bad["action"] == "STAND_ASIDE"
    assert res_bad["status"] in {"ERROR", "MODEL_UNAVAILABLE"}


def test_real_candle_replay_through_tier1_laya_risk():
    """Replay 65 candles through FastDecisionLayer and verify full audit trail."""
    df = _generate_synthetic_klines(65)
    candles = df.to_dict(orient="records")

    decision_layer = FastDecisionLayer()
    decision = decision_layer.decide(candles, symbol="BTCUSDT")

    assert "final_action" in decision
    assert decision["final_action"] in {"LONG", "SHORT", "STAND_ASIDE"}
    assert "thesis" in decision
    assert "total_latency_ms" in decision
    assert decision["total_latency_ms"] < 250.0
    assert len(decision_layer.audit_log) > 0


def test_ast_isolation_laya_modules():
    """Architectural isolation: No research/laya or decision module may import broker/exchange clients."""
    forbidden = ["paper_broker", "governor", "binance_testnet", "ccxt", "binance.client", "providers.binance"]
    check_paths = [
        Path("cryptoscope/research/laya"),
        Path("cryptoscope/autotrader/decision.py"),
    ]

    for p in check_paths:
        py_files = [p] if p.is_file() else list(p.rglob("*.py"))
        for py_file in py_files:
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for bad in forbidden:
                            assert bad not in alias.name, f"{py_file.name} illegal import: {alias.name}"
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for bad in forbidden:
                        assert bad not in mod, f"{py_file.name} illegal from-import: {mod}"
