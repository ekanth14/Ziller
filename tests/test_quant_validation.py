"""Known-answer tests for triple-barrier labels, CPCV, PBO and the deflated Sharpe wrapper."""
from math import comb

import numpy as np
import pytest

from core.quant.validation import (LOWER, UPPER, VERTICAL, cpcv_splits, deflated_sharpe, group_bounds,
                                   probability_of_backtest_overfitting, triple_barrier_labels)


def _flat(n, px=100.0):
    return [px] * n, [px] * n, [px] * n, [px] * n


def test_triple_barrier_hits_target_stop_and_time():
    o, h, l, c = _flat(12)
    sig = [0] * 12
    sig[0] = sig[4] = sig[8] = 1
    h[2] = 101.2                       # trade 1 (entry bar 1) reaches +1% target on bar 2
    l[6] = 98.9                        # trade 2 (entry bar 5) reaches -1% stop on bar 6
    trades = triple_barrier_labels(o, h, l, c, sig, [0.01] * 12, [0.01] * 12, horizon_bars=3, fee=0.001)
    assert [t["barrier"] for t in trades] == [UPPER, LOWER, VERTICAL]
    assert trades[0]["entry"] == 1 and trades[0]["exit"] == 2 and trades[0]["exit_price"] == pytest.approx(101.0)
    assert trades[0]["ret"] == pytest.approx(1.01 * 0.999 ** 2 - 1)
    assert trades[1]["ret"] == pytest.approx(0.99 * 0.999 ** 2 - 1)
    assert trades[2]["exit"] == 11 and trades[2]["ret"] == pytest.approx(0.999 ** 2 - 1)   # time barrier: fees only


def test_triple_barrier_is_conservative_when_both_barriers_touch_and_on_gaps():
    o, h, l, c = _flat(6)
    sig = [1, 0, 0, 0, 0, 0]
    h[1], l[1] = 102.0, 98.0           # same bar touches both: stop assumed first
    t = triple_barrier_labels(o, h, l, c, sig, [0.01] * 6, [0.01] * 6, horizon_bars=4, fee=0.0)[0]
    assert t["barrier"] == LOWER and t["exit_price"] == pytest.approx(99.0)
    o, h, l, c = _flat(6)
    o[2] = l[2] = h[2] = c[2] = 95.0   # gap down through the stop fills at the open, not the stop
    t = triple_barrier_labels(o, h, l, c, sig, [0.01] * 6, [0.01] * 6, horizon_bars=4, fee=0.0)[0]
    assert t["barrier"] == LOWER and t["exit_price"] == 95.0


def test_triple_barrier_one_position_at_a_time_and_drops_unfinished_labels():
    o, h, l, c = _flat(10)
    trades = triple_barrier_labels(o, h, l, c, [1] * 10, [0.01] * 10, [0.01] * 10, horizon_bars=3)
    assert [t["entry"] for t in trades] == [1, 4, 7]    # a signal on the exit bar's close may re-enter
    o, h, l, c = _flat(9)
    trades = triple_barrier_labels(o, h, l, c, [1] * 9, [0.01] * 9, [0.01] * 9, horizon_bars=3)
    assert [t["entry"] for t in trades] == [1, 4]       # entry 7 would end past the data: unlabelled
    assert all(a["exit"] < b["entry"] for a, b in zip(trades, trades[1:]))


def test_cpcv_split_count_disjoint_and_purged_with_embargo():
    n = 120
    splits = cpcv_splits(n, n_groups=6, n_test_groups=2)
    assert len(splits) == comb(6, 2)
    for train, test in splits:
        assert not set(train) & set(test)
        assert len(train) + len(test) == n             # no labels span groups -> nothing purged
    # labels lasting 5 bars: training rows whose label reaches into a test group are purged
    ends = [min(n - 1, i + 5) for i in range(n)]
    bounds = group_bounds(n, 6)
    for train, test in cpcv_splits(n, 6, 2, label_end=ends, embargo=3):
        test_set = set(test)
        for i in train:
            assert not any(j in test_set for j in range(i, ends[i] + 1)), "leaky training label"
        for a, b in bounds:
            if a in test_set:
                assert not set(range(b, min(n, b + 3))) & set(train) or b in test_set, "embargo missing"


def test_pbo_is_about_half_for_pure_noise():
    rng = np.random.default_rng(42)
    pbos = [probability_of_backtest_overfitting(rng.normal(0, 0.01, (600, 20)), n_groups=10)["pbo"]
            for _ in range(8)]
    assert 0.35 <= float(np.mean(pbos)) <= 0.65


def test_pbo_is_low_for_a_planted_edge():
    rng = np.random.default_rng(7)
    r = rng.normal(0, 0.01, (600, 20))
    r[:, 3] += 0.004                                   # one real edge among 19 noise strategies
    res = probability_of_backtest_overfitting(r, n_groups=10, embargo=2)
    assert res["splits"] == comb(10, 5)
    assert res["pbo"] < 0.1


def test_deflated_sharpe_penalises_many_trials():
    rng = np.random.default_rng(1)
    edge = rng.normal(0.004, 0.01, 300)
    one = deflated_sharpe(edge, n_trials=1)
    many = deflated_sharpe(edge, n_trials=500, var_sharpe=0.05)
    assert one["p_value"] < 0.01 and many["p_value"] > one["p_value"]
    assert deflated_sharpe(rng.normal(0, 0.01, 300), n_trials=20, var_sharpe=0.01)["p_value"] > 0.05
    assert deflated_sharpe([0.01, 0.01], n_trials=1)["p_value"] == 1.0
