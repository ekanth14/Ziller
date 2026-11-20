"""The indicator catalog uses no future bars: truncating later candles never changes earlier values."""
import math
import random

import pytest

pytest.importorskip("pandas_ta_classic")

from cryptoscope.desk import indicator_catalog as cat  # noqa: E402


def _candles(n=900, seed=3):
    rng, px, out = random.Random(seed), 100.0, []
    for i in range(n):
        o = px
        px = max(1.0, px * math.exp(rng.gauss(0.0002, 0.006)))
        hi, lo = max(o, px) * (1 + abs(rng.gauss(0, 0.002))), min(o, px) * (1 - abs(rng.gauss(0, 0.002)))
        out.append({"open_time": 1_700_000_000 + i * 900, "open": o, "high": hi, "low": lo, "close": px,
                    "volume": 1000 * (1 + abs(rng.gauss(0, 0.5)))})
    return out


def test_full_catalog_has_no_lookahead():
    c = _candles()
    feats = cat.compute_catalog(c)
    assert feats.shape == (len(c), feats.shape[1]) and feats.shape[1] > 300
    assert not [col for col in feats.columns if col.startswith("ICS_")]
    assert cat.audit_lookahead(c, cuts=[250, 600, len(c) - 1]) == {}


def test_audit_catches_known_lookahead_indicators():
    c = _candles(400)
    bad = cat.audit_lookahead(c, cuts=[300], names=["dpo", "tos_stdevall", "rsi"])
    assert any(k.startswith("DPO") for k in bad) and any(k.startswith("TOS_STDEVALL") for k in bad)
    assert not any(k.startswith("RSI") for k in bad)


def test_summary_lists_counts_exclusions_and_latest_values():
    c = _candles(300)
    s = cat.catalog_summary(cat.compute_catalog(c))
    assert s["status"] == "OK" and s["features"] > 300 and s["indicators"] > 150
    assert "dpo" in s["excluded"] and "ICS_*" in s["excluded"]
    assert "RSI_14" in s["latest"]
