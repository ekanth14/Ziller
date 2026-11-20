"""Strategy Lab promotion gate: a planted edge passes, noise and thin samples fail, the JSON round-trips."""
import json
import math
import random

from cryptoscope.desk.strategy_lab import (GATE, STRATEGIES, gate_candidates, load_promoted_strategies,
                                           record_promotions, run_lab)


def _market(n=3000, every=15, seed=11):
    """15m random walk; the bar after every `every`-th bar spikes +2% intrabar (low never dips)."""
    rng, px, out = random.Random(seed), 100.0, []
    for i in range(n):
        o = px
        if i % every == 1 and i > 1:
            hi, lo, px = o * 1.02, o, o * 1.003
        else:
            px = o * math.exp(rng.gauss(0, 0.003))
            hi, lo = max(o, px) * 1.001, min(o, px) * 0.999
        out.append({"open_time": 1_700_000_000 + i * 900, "open": o, "high": hi, "low": lo, "close": px, "volume": 1e3})
    return out


def _pulses(n, bars):
    pos = [0] * n
    for b in bars:
        pos[b] = 1                     # one-bar position: entry signal on bar b
    return pos


def test_planted_edge_passes_and_noise_fails():
    c = _market()
    n, rng = len(c), random.Random(5)
    positions = {"edge": _pulses(n, range(15, n - 20, 15))}
    for k in range(8):
        positions[f"noise{k}"] = _pulses(n, sorted(rng.sample(range(20, n - 20), 200)))
    g = gate_candidates(c, positions, "15m", fee_bps=10)
    edge = g["candidates"]["edge"]
    assert g["horizon_bars"] == 16 and g["fee_bps"] == 10
    assert edge["oos_trades"] >= GATE["min_oos_trades"] and edge["expectancy"] > 0
    assert edge["dsr_p"] < 0.05 and g["pbo"] < 0.3
    assert edge["passed"], edge["reasons"]
    assert not any(g["candidates"][f"noise{k}"]["passed"] for k in range(8))


def test_gate_never_uses_less_than_ten_bp_and_fails_thin_samples():
    c = _market(600)
    g = gate_candidates(c, {"edge": _pulses(600, range(15, 580, 15)), "flat": [0] * 600}, "15m", fee_bps=0)
    assert g["fee_bps"] == 10
    assert not g["candidates"]["edge"]["passed"]
    assert any("OOS trades" in r for r in g["candidates"]["edge"]["reasons"])
    assert g["candidates"]["flat"]["oos_trades"] == 0 and not g["candidates"]["flat"]["passed"]


def test_run_lab_attaches_gate_to_every_candidate_and_catalog():
    r = run_lab(_market(1000), "15m", 10)
    ok = [x for x in r["results"] if "error" not in x]
    assert len(ok) == len(STRATEGIES) and r["gate"]["n_candidates"] == len(STRATEGIES)
    assert all({"passed", "reasons", "oos_trades", "dsr_p", "pbo"} <= set(x["gate"]) for x in ok)
    assert r["catalog"]["status"] in {"OK", "UNAVAILABLE"}


def test_promotions_file_round_trip_and_demotion(tmp_path):
    path = tmp_path / "promoted_strategies.json"
    gate = {"status": "OK", "fee_bps": 10.0, "thresholds": {"max_pbo": 0.3}}
    metrics = {"oos_trades": 150, "expectancy": 0.002, "win_rate": 0.6, "dsr_p": 0.01, "pbo": 0.1}
    result = {"status": "OK", "interval": "15m", "bars": 1000, "from": 1, "to": 2, "gate": gate,
              "results": [{"key": "donchian", "label": "Donchian", "family": "breakout", "gate": {**metrics, "passed": True}},
                          {"key": "rsi2", "label": "RSI-2", "family": "mr", "gate": {**metrics, "passed": False}}]}
    record_promotions(result, "AAAUSDT", path)
    record_promotions({**result, "interval": "1h"}, "AAAUSDT", path)
    got = load_promoted_strategies(path)
    assert sorted((e["interval"], e["strategy"]) for e in got) == [("15m", "donchian"), ("1h", "donchian")]
    result["results"][0]["gate"]["passed"] = False          # it stops passing on 15m: demoted there only
    record_promotions(result, "AAAUSDT", path)
    assert [(e["interval"], e["strategy"]) for e in load_promoted_strategies(path)] == [("1h", "donchian")]
    assert json.loads(path.read_text())["gate"] == {"max_pbo": 0.3}
    path.write_text("{not json")
    assert load_promoted_strategies(path) == []
    assert load_promoted_strategies(tmp_path / "missing.json") == []
