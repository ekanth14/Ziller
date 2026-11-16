"""Optional native (C++) kernels loaded through ctypes.

The pure-Python implementations in core.quant remain the source of truth. If the
shared library is missing, cannot be loaded (e.g. blocked by an OS policy), or the
environment variable ZILLERS_NO_NATIVE=1 is set, every function here returns None
and callers fall back to Python.

Build the library with:  python native/build.py
"""
from __future__ import annotations

import ctypes
import math
import os
import sys
from pathlib import Path
from typing import Sequence

_ROOT = Path(__file__).resolve().parents[2]


def _candidate_paths() -> list[Path]:
    name = (
        "zillers_native.dll" if sys.platform.startswith("win")
        else "libzillers_native.dylib" if sys.platform == "darwin"
        else "libzillers_native.so"
    )
    paths = []
    env = os.environ.get("ZILLERS_NATIVE_LIB")
    if env:
        paths.append(Path(env))
    paths.append(Path(__file__).resolve().parent / "_native" / name)
    paths.append(_ROOT / "native" / "build" / name)
    return paths


def _load():
    if os.environ.get("ZILLERS_NO_NATIVE", "").lower() in {"1", "true", "yes"}:
        return None
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            lib = ctypes.CDLL(str(path))
            lib.zn_abi_version.restype = ctypes.c_int
            if lib.zn_abi_version() != 2:
                continue
            dp = ctypes.POINTER(ctypes.c_double)
            lib.zn_monte_carlo_drawdown.restype = ctypes.c_double
            lib.zn_monte_carlo_drawdown.argtypes = [
                dp, ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double, ctypes.c_uint64,
            ]
            lib.zn_hurst_exponent.restype = ctypes.c_double
            lib.zn_hurst_exponent.argtypes = [dp, ctypes.c_int]
            ip = ctypes.POINTER(ctypes.c_int)
            lib.zn_hmm_em.restype = ctypes.c_int
            lib.zn_hmm_em.argtypes = [dp, ctypes.c_int, ctypes.c_int, dp, dp, dp, dp, ctypes.c_int, ctypes.c_double]
            lib.zn_hmm_viterbi.restype = ctypes.c_int
            lib.zn_hmm_viterbi.argtypes = [dp, ctypes.c_int, ctypes.c_int, dp, dp, dp, dp, ip]
            return lib
        except (OSError, AttributeError):
            continue
    return None


_LIB = _load()
AVAILABLE = _LIB is not None


def _as_array(values: Sequence[float]):
    n = len(values)
    return (ctypes.c_double * n)(*values), n


def monte_carlo_drawdown(
    pnls: Sequence[float], iterations: int, confidence: float, initial_equity: float, seed: int
) -> float | None:
    """Native Monte Carlo drawdown percentile; None if unavailable or inputs unsupported."""
    if _LIB is None or iterations <= 0 or not (0 <= seed < 2 ** 64):
        return None
    arr, n = _as_array(pnls)
    result = _LIB.zn_monte_carlo_drawdown(arr, n, int(iterations), float(confidence), float(initial_equity), int(seed))
    return None if math.isnan(result) else result


def hurst_exponent(series: Sequence[float]) -> float | None:
    """Native Hurst exponent (R/S); None if unavailable."""
    if _LIB is None:
        return None
    arr, n = _as_array(series)
    result = _LIB.zn_hurst_exponent(arr, n)
    return None if math.isnan(result) else result


def hmm_em(x, means, stds, a, pi, max_iter: int, tol: float):
    """Native HMM EM loop. Returns (means, stds, a, pi) as lists, or None if unavailable.

    `a` is a k x k nested sequence; inputs are not modified.
    """
    if _LIB is None:
        return None
    k = len(means)
    xs, t = _as_array([float(v) for v in x])
    m, _ = _as_array([float(v) for v in means])
    sd, _ = _as_array([float(v) for v in stds])
    am, _ = _as_array([float(a[i][j]) for i in range(k) for j in range(k)])
    p, _ = _as_array([float(v) for v in pi])
    if _LIB.zn_hmm_em(xs, t, k, m, sd, am, p, int(max_iter), float(tol)) != 0:
        return None
    a_out = [[am[i * k + j] for j in range(k)] for i in range(k)]
    return list(m), list(sd), a_out, list(p)


def hmm_viterbi(x, means, stds, a, pi):
    """Native Viterbi decoding. Returns list[int] path, or None if unavailable."""
    if _LIB is None:
        return None
    k = len(means)
    xs, t = _as_array([float(v) for v in x])
    m, _ = _as_array([float(v) for v in means])
    sd, _ = _as_array([float(v) for v in stds])
    am, _ = _as_array([float(a[i][j]) for i in range(k) for j in range(k)])
    p, _ = _as_array([float(v) for v in pi])
    path = (ctypes.c_int * t)()
    if _LIB.zn_hmm_viterbi(xs, t, k, m, sd, am, p, path) != 0:
        return None
    return list(path)
