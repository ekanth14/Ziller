"""Differential tests: native C++ kernels must match the pure-Python references.

Skipped automatically when the shared library is not built or cannot be loaded
(e.g. blocked by an OS application-control policy). Build with: python native/build.py
"""
import math
import random

import pytest

from core.quant import native
from core.quant.stage3_filter import compute_hurst_exponent, compute_hurst_exponent_py
from core.quant.stage8_validate import run_monte_carlo_drawdown, run_monte_carlo_drawdown_py

pytestmark = pytest.mark.skipif(not native.AVAILABLE, reason="zillers_native shared library not available")


@pytest.mark.parametrize("seed", [0, 1, 42, 2 ** 32 + 5, 2 ** 63])
@pytest.mark.parametrize("n_trades", [1, 2, 7, 120, 300])
def test_monte_carlo_matches_python_bit_for_bit(seed, n_trades):
    rng = random.Random(n_trades)
    pnls = [rng.gauss(0.002, 0.03) * 10000 for _ in range(n_trades)]
    for conf in (0.5, 0.95, 0.99, 1.0):
        py = run_monte_carlo_drawdown_py(pnls, 400, conf, 10000.0, seed)
        nat = native.monte_carlo_drawdown(pnls, 400, conf, 10000.0, seed)
        assert nat == py


def test_monte_carlo_public_api_uses_same_result():
    pnls = [random.Random(3).gauss(0, 50) for _ in range(80)]
    assert run_monte_carlo_drawdown(pnls, 300, 0.95, 10000.0, 42) == run_monte_carlo_drawdown_py(pnls, 300, 0.95, 10000.0, 42)


@pytest.mark.parametrize("n,seed", [(50, 1), (120, 2), (300, 3), (1000, 4), (5000, 5)])
def test_hurst_matches_python(n, seed):
    rng = random.Random(seed)
    price, series = 100.0, []
    for _ in range(n):
        price *= math.exp(rng.gauss(0, 0.01))
        series.append(price)
    assert native.hurst_exponent(series) == pytest.approx(compute_hurst_exponent_py(series), rel=1e-9, abs=1e-12)
    assert compute_hurst_exponent(series) == pytest.approx(compute_hurst_exponent_py(series), rel=1e-9, abs=1e-12)


def test_hurst_short_and_flat_series():
    assert native.hurst_exponent([1.0] * 10) == 0.5
    assert native.hurst_exponent([5.0] * 200) == pytest.approx(compute_hurst_exponent_py([5.0] * 200))


# ------------------------------------------------------------------ HMM
class _NoNative:
    @staticmethod
    def hmm_em(*a, **k):
        return None

    @staticmethod
    def hmm_viterbi(*a, **k):
        return None


def _regime_returns(n, seed):
    rng = random.Random(seed)
    out, state = [], 0
    for _ in range(n):
        if rng.random() < 0.03:
            state = 1 - state
        out.append(rng.gauss(0.0005, 0.004) if state == 0 else rng.gauss(-0.001, 0.02))
    return out


@pytest.mark.parametrize("n_states", [2, 3])
@pytest.mark.parametrize("n,seed", [(60, 1), (300, 2), (700, 3)])
def test_hmm_em_matches_python(monkeypatch, n_states, n, seed):
    from core.quant.levels import level10_research as lv

    returns = _regime_returns(n, seed)
    nat = lv.GaussianRegimeHMM(n_states=n_states).fit(returns)
    monkeypatch.setattr(lv, "_native", _NoNative)
    py = lv.GaussianRegimeHMM(n_states=n_states).fit(returns)
    assert nat.means == pytest.approx(py.means, rel=1e-6, abs=1e-9)
    assert nat.stds == pytest.approx(py.stds, rel=1e-6, abs=1e-9)
    assert nat.priors == pytest.approx(py.priors, rel=1e-6, abs=1e-9)
    for row_n, row_p in zip(nat.transition_matrix, py.transition_matrix):
        assert row_n == pytest.approx(row_p, rel=1e-6, abs=1e-9)


@pytest.mark.parametrize("n_states", [2, 3])
@pytest.mark.parametrize("n,seed", [(5, 1), (300, 2), (1500, 3)])
def test_hmm_viterbi_identical_paths(monkeypatch, n_states, n, seed):
    from core.quant.levels import level10_research as lv

    returns = _regime_returns(n, seed)
    hmm = lv.GaussianRegimeHMM(n_states=n_states)
    hmm.fit(returns)
    native_path = hmm.predict(returns)
    monkeypatch.setattr(lv, "_native", _NoNative)
    assert native_path == hmm.predict(returns)
