"""Differential tests: incremental QuantPipeline must match the full-recompute reference."""
import math
import random

import pytest

from core.quant.pipeline import QuantPipeline, ReferenceQuantPipeline

NUMERIC_KEYS = [
    "close", "log_return", "annualized_vol", "ewma_vol", "atr", "z_score", "ema_20", "rsi_14",
    "t_stat", "hurst_exponent", "suggested_size", "volatility_target_scalar", "liquidation_price",
    "spread", "microprice", "estimated_impact", "var_95", "max_drawdown",
]
EXACT_KEYS = ["symbol", "is_bad_tick", "is_high_vol", "kill_switch_triggered"]


def _bars(n, seed, vol=0.01, spike_every=0):
    rng = random.Random(seed)
    price = 100.0
    for i in range(n):
        o = price
        r = rng.gauss(0.0, vol)
        if spike_every and i and i % spike_every == 0:
            r *= 12  # produce bad-tick candidates
        price *= math.exp(r)
        h = max(o, price) * (1 + abs(rng.gauss(0, 0.002)))
        low = min(o, price) * (1 - abs(rng.gauss(0, 0.002)))
        yield o, h, low, price, rng.uniform(100, 1000)


def _assert_close(ref, new, bar):
    for k in EXACT_KEYS:
        assert ref[k] == new[k], f"bar {bar}: {k} {ref[k]!r} != {new[k]!r}"
    for k in NUMERIC_KEYS:
        assert new[k] == pytest.approx(ref[k], rel=1e-7, abs=1e-9), f"bar {bar}: {k} {ref[k]} != {new[k]}"
    if ref["half_life"] is None:
        assert new["half_life"] is None, f"bar {bar}: half_life"
    else:
        assert new["half_life"] == pytest.approx(ref["half_life"], rel=1e-5), f"bar {bar}: half_life"


@pytest.mark.parametrize("seed,vol,spike", [(1, 0.01, 0), (2, 0.03, 0), (3, 0.005, 37), (4, 0.02, 53)])
def test_incremental_matches_reference(seed, vol, spike):
    ref = ReferenceQuantPipeline("BTCUSDT")
    new = QuantPipeline("BTCUSDT")
    rng = random.Random(seed + 100)
    equity = 10000.0
    for i, (o, h, low, c, v) in enumerate(_bars(450, seed, vol, spike)):
        equity *= 1 + rng.gauss(0, 0.004)
        args = (o, h, low, c, v, c * 0.9999, 1.0 + rng.random(), c * 1.0001, 1.0 + rng.random())
        a = ref.on_bar(*args, equity=equity)
        b = new.on_bar(*args, equity=equity)
        _assert_close(a, b, i)


def test_without_equity_updates():
    ref = ReferenceQuantPipeline("ETHUSDT", initial_equity=5000.0)
    new = QuantPipeline("ETHUSDT", initial_equity=5000.0)
    for i, (o, h, low, c, v) in enumerate(_bars(120, 9)):
        args = (o, h, low, c, v, c * 0.999, 2.0, c * 1.001, 1.0)
        _assert_close(ref.on_bar(*args), new.on_bar(*args), i)


def test_flat_prices_edge_case():
    ref = ReferenceQuantPipeline("X")
    new = QuantPipeline("X")
    for i in range(80):
        args = (10.0, 10.0, 10.0, 10.0, 1.0, 9.99, 1.0, 10.01, 1.0)
        _assert_close(ref.on_bar(*args), new.on_bar(*args), i)


def test_non_positive_price_raises_without_corrupting_state():
    new = QuantPipeline("X")
    new.on_bar(10, 11, 9, 10, 1, 9.9, 1, 10.1, 1)
    with pytest.raises(ValueError):
        new.on_bar(10, 11, 9, 0.0, 1, 9.9, 1, 10.1, 1)
    assert len(new.closes) == 1
    new.on_bar(10, 11, 9, 10.5, 1, 9.9, 1, 10.1, 1)
    assert len(new.closes) == 2
