"""BTC trend gate + funding filter (veto-only, fail open), jump-model regimes, meta-labeling pipeline."""
import math
import random

import numpy as np

from cryptoscope.quant.market_filters import BtcTrendGate, FundingFilter, default_filters


def test_btc_gate_vetoes_only_in_downtrend_and_fails_open():
    up = BtcTrendGate(closes=lambda: [100 + i for i in range(60)])
    down = BtcTrendGate(closes=lambda: [200 - i for i in range(60)])
    broken = BtcTrendGate(closes=lambda: (_ for _ in ()).throw(OSError("offline")))
    assert up.veto() is None and down.veto().startswith("BTC_DOWNTREND")
    assert broken.veto() is None and broken.state()["ok"] is False


def test_funding_filter_threshold_cache_and_missing_perp():
    calls = []

    def fetch(sym):
        calls.append(sym)
        return {"HOTUSDT": 0.001, "OKUSDT": 0.0001}.get(sym)
    f = FundingFilter(fetch=fetch, max_rate=0.0005)
    assert f.veto("HOTUSDT").startswith("FUNDING_CROWDED") and f.veto("OKUSDT") is None
    assert f.veto("NOPERPUSDT") is None                                     # no perpetual: no opinion
    f.veto("HOTUSDT")
    assert calls.count("HOTUSDT") == 1                                      # cached


def test_btc_gate_is_opt_in(monkeypatch):
    monkeypatch.delenv("ZILLERS_BTC_GATE", raising=False)
    monkeypatch.delenv("ZILLERS_FUNDING_FILTER", raising=False)
    assert set(default_filters()) == {"funding"}
    monkeypatch.setenv("ZILLERS_BTC_GATE", "1")
    monkeypatch.setenv("ZILLERS_FUNDING_FILTER", "0")
    assert set(default_filters()) == {"btc"}


def test_risk_bot_applies_filters_to_new_longs_only():
    from cryptoscope.orchestrator.bots.risk_bot import RiskBot
    from cryptoscope.orchestrator.event_bus import EventBus
    from cryptoscope.orchestrator.events import TradeIntent

    class Veto:
        def veto(self, *a):
            return "BTC_DOWNTREND: test"

    class Boom:
        def veto(self, *a):
            raise RuntimeError("feed down")
    bot = RiskBot(EventBus(), market_filters={"btc": Veto(), "funding": Boom()})
    it = TradeIntent(symbol="XRPUSDT", direction="BUY", entry_price=1.0, stop_loss=0.99, take_profit=1.01)
    ok, why = bot.check_pre_trade_risk(it)
    assert not ok and why == ["BTC_DOWNTREND: test"]                         # a crashing filter adds nothing
    assert RiskBot(EventBus()).check_pre_trade_risk(it)[0]                   # no filters by default (offline)


def _regime_prices(seed=2):
    rnd, p, out = random.Random(seed), 100.0, []
    for i in range(600):
        bull = (i // 150) % 2 == 0                                           # 150-bar bull / bear blocks
        p *= math.exp((0.004 if bull else -0.004) + rnd.gauss(0, 0.008 if bull else 0.02))
        out.append(p)
    return out


def test_jump_model_finds_persistent_regimes_without_lookahead():
    from core.quant.jump_model import online_bull_states
    close = _regime_prices()
    st = online_bull_states(close, lam=20, refit=50, warmup=150)
    assert st[:150] == [None] * 150
    truth = [1 if (i // 150) % 2 == 0 else 0 for i in range(600)]
    acc = sum(1 for i in range(200, 600) if st[i] == truth[i]) / 400
    switches = sum(1 for a, b in zip(st[150:], st[151:]) if a != b)
    assert acc > 0.75 and switches < 20
    assert online_bull_states(close[:400], lam=20, refit=50, warmup=150) == st[:400]


def test_meta_label_learns_a_planted_rule():
    from core.quant.meta_ml import evaluate_meta_label
    rnd = random.Random(7)
    c, p = [], 100.0
    pos = []
    for i in range(3000):
        good = rnd.random() < 0.5
        o = p
        # every 10th bar is a signal; when the bar's volume is high (planted feature) the next bars rally
        sig = i % 10 == 0 and i > 70
        vol = 5000.0 if (sig and good) else 1000.0 + rnd.random() * 100
        drift = 0.004 if (i % 10 in (1, 2, 3) and c and c[-(i % 10)]["volume"] > 4000) else -0.0005
        p *= math.exp(drift + rnd.gauss(0, 0.002))
        c.append({"open": o, "high": max(o, p) * 1.0005, "low": min(o, p) * 0.9995, "close": p, "volume": vol})
        pos.append(1 if sig else 0)
    pos = [1 if (pos[i] and not pos[i - 1]) else 0 for i in range(len(pos))]
    r = evaluate_meta_label(c, pos, stop_pct=0.005, target_pct=0.005, horizon_bars=5, fee=0.0)
    assert r["status"] == "OK" and r["auc"] > 0.7
    assert r["oos_taken"]["expectancy"] > r["oos_all"]["expectancy"]
    few = evaluate_meta_label(c[:300], pos[:300], 0.005, 0.005, 5)
    assert few["status"] == "INSUFFICIENT_DATA"


def test_jump_regime_lab_candidate_registered():
    from cryptoscope.desk.strategy_lab import STRATEGIES
    assert "jump_regime" in STRATEGIES and len(STRATEGIES) == 38
    close = _regime_prices()
    c = [{"open": x, "high": x, "low": x, "close": x, "volume": 1, "open_time": i * 86400} for i, x in enumerate(close)]
    pos = STRATEGIES["jump_regime"][2](c)
    assert set(pos) <= {0, 1} and STRATEGIES["jump_regime"][2](c[:400]) == pos[:400]
    assert np.mean(pos[200:300]) != np.mean(pos[350:450])                  # follows the regime change
