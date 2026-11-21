"""Deep-research additions: extra metrics (known answers), new Lab candidates (no lookahead), rotation."""
import math
import random

import pytest

from core.quant import metrics_extra as mx


def _candles(n=400, drift=0.0005, vol=0.02, seed=5, step=86400):
    rnd, p, out = random.Random(seed), 100.0, []
    for i in range(n):
        o = p
        p *= math.exp(drift + rnd.gauss(0, vol))
        out.append({"open_time": 1_700_000_000 - 1_700_000_000 % 86400 + i * step, "open": o,
                    "high": max(o, p) * (1 + abs(rnd.gauss(0, vol / 3))), "low": min(o, p) * (1 - abs(rnd.gauss(0, vol / 3))),
                    "close": p, "volume": 1000 + rnd.random() * 500})
    return out


def test_psr_and_min_trl_known_values():
    rnd = random.Random(1)
    good = [0.002 + rnd.gauss(0, 0.01) for _ in range(2000)]
    bad = [-0.002 + rnd.gauss(0, 0.01) for _ in range(2000)]
    assert mx.probabilistic_sharpe(good) > 0.99 and mx.probabilistic_sharpe(bad) < 0.01
    # normal returns: MinTRL ~ 1 + (1 + SR^2/2) * (1.645/SR)^2
    sr = 0.2
    approx = 1 + (1 + sr * sr / 2) * (1.6449 / sr) ** 2
    rets = [sr + x for x in [rnd.gauss(0, 1) for _ in range(200000)]]
    assert abs(mx.min_track_record_length(rets) - approx) / approx < 0.05
    assert mx.min_track_record_length(bad) is None and mx.probabilistic_sharpe([0.1, 0.1]) is None


def test_drawdown_and_ratio_metrics():
    curve = [100, 110, 99, 121]                      # drawdown 10% at the third point
    assert abs(mx.ulcer_index(curve) - math.sqrt(100 / 4)) < 1e-9
    assert mx.omega_ratio([0.02, -0.01, 0.03, -0.01]) == pytest.approx(2.5)
    assert mx.gain_to_pain([0.02, -0.01, 0.03, -0.01]) == pytest.approx(1.5)
    assert mx.sqn([0.01] * 3 + [0.02] * 3) == pytest.approx(math.sqrt(6) * 0.015 / 0.005477225575, rel=1e-6)
    assert mx.k_ratio([100 * 1.01 ** i for i in range(50)]) is None        # perfect line: zero error -> undefined
    assert mx.k_ratio([100 * 1.01 ** i * (1 + 0.001 * (-1) ** i) for i in range(50)]) > 0
    assert mx.sortino([0.01, -0.02, 0.03], 365) == pytest.approx(
        (0.02 / 3) / math.sqrt(0.0004 / 3) * math.sqrt(365))                # divides by total N
    assert mx.calmar([100, 50, 100], 1) == pytest.approx(0.0)


def test_frac_diff_weights_and_series():
    w = mx.frac_diff_weights(0.5, threshold=1e-3)
    assert w[:3] == pytest.approx([1.0, -0.5, -0.125]) and abs(w[-1]) >= 1e-3
    assert mx.frac_diff_weights(1.0)[:3] == [1.0, -1.0]                     # d=1 is a plain difference
    s = mx.frac_diff([float(i) for i in range(10)], 1.0)
    assert s[0] is None and s[5] == pytest.approx(1.0)


NEW = ("donchian_chandelier", "tsmom_chandelier", "ema_atr_trail", "nr7", "inside_bar", "connors_rsi",
       "zscore_revert", "turn_of_month", "utc_orb")


@pytest.mark.parametrize("key", NEW)
def test_new_candidates_have_no_lookahead(key):
    from cryptoscope.desk.strategy_lab import STRATEGIES
    step = 900 if key == "utc_orb" else 86400
    c = _candles(400, step=step)
    full = STRATEGIES[key][2](c)
    assert len(full) == len(c) and set(full) <= {0, 1}
    assert STRATEGIES[key][2](c[:300]) == full[:300]


def test_turn_of_month_and_orb_only_on_their_timeframes():
    from cryptoscope.desk.strategy_lab import s_turn_of_month, s_utc_orb
    daily, intraday = _candles(120), _candles(300, step=900)
    assert any(s_turn_of_month(daily)) and not any(s_turn_of_month(intraday))
    assert not any(s_utc_orb(daily))
    pos = s_utc_orb(intraday)
    ends = [i for i, b in enumerate(intraday) if (b["open_time"] % 86400) + 900 >= 86400]
    assert all(pos[i] == 0 for i in ends)                                   # always flat at the UTC day close


def test_chandelier_stop_only_ratchets_up():
    from cryptoscope.desk.strategy_lab import _entries_with_trailing_exit
    c = _candles(300, drift=0.004, vol=0.01)
    pos = _entries_with_trailing_exit(c, lambda i: i == 40, 30)
    assert pos[40] == 1 and sum(pos) > 5                                    # a strong trend is held, not scalped


def test_lab_reports_extra_metrics():
    from cryptoscope.desk.strategy_lab import run_lab
    r = run_lab(_candles(500), "1d", 10, only=["donchian_chandelier", "nr7"])
    assert r["status"] == "OK"
    for row in r["results"]:
        for k in ("psr", "sqn", "ulcer_index", "omega", "k_ratio"):
            assert k in row, (row["key"], k)


def test_rotation_backtest_rules():
    from cryptoscope.desk.rotation import rotation_backtest
    rnd = random.Random(3)
    T = 400
    times = [i * 86400.0 for i in range(T)]
    btc = [100 * math.exp(0.002 * i) for i in range(T)]                     # BTC above its SMA: gate open
    closes = {}
    for j in range(8):
        p, s = 10.0, []
        for i in range(T):
            p *= math.exp((0.004 if j == 0 else -0.001) + rnd.gauss(0, 0.01))
            s.append(p)
        closes[f"C{j}USDT"] = s
    r = rotation_backtest(closes, btc, times, k=2)
    assert "C0USDT" in r["last_holdings"]["holdings"]                        # the persistent winner is held
    assert r["full"]["total_return"] > 0 and len(r["curve"]) == len(r["benchmark"])
    assert set(r["checks"]) == {"oos_entries_100", "psr_95", "positive_oos_after_fees"}
    down = [100 * math.exp(-0.002 * i) for i in range(T)]                   # BTC below SMA: always cash
    r2 = rotation_backtest(closes, down, times, k=2)
    assert r2["entries"] == 0 and r2["full"]["total_return"] == 0
