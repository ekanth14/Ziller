"""Features adapted from similar projects: protections (freqtrade), AI journal (TradingAgents),
rule significance (Jesse), grid/DCA paper bots (OctoBot). All offline."""
import math
import random

import pytest

from cryptoscope.desk.ai_journal import AIJournal
from cryptoscope.desk.engine import significance
from cryptoscope.desk.paperbots import PaperBotManager, dca_start, dca_step, grid_start, grid_step, validate
from cryptoscope.execution.protections import GLOBAL, ProtectionConfig, ProtectionManager


# ------------------------------------------------------------------ protections
class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_cooldown_locks_only_that_pair_and_expires():
    clk = Clock()
    pm = ProtectionManager(ProtectionConfig(cooldown_minutes=30), clock=clk)
    pm.record_close("BTCUSDT", 0.01, 10, "TAKE_PROFIT")
    assert pm.is_locked("BTCUSDT")[0] and not pm.is_locked("ETHUSDT")[0]
    clk.t += 31 * 60
    assert not pm.is_locked("BTCUSDT")[0]


def test_stoploss_guard_locks_all_pairs():
    clk = Clock()
    pm = ProtectionManager(ProtectionConfig(cooldown_minutes=0, stoploss_limit=3), clock=clk)
    for sym in ("A1USDT", "B2USDT", "C3USDT"):
        pm.record_close(sym, -0.01, -10, "STOP_LOSS")
        clk.t += 60
    locked, reasons = pm.is_locked("ZZZUSDT")
    assert locked and any("STOPLOSSGUARD" in r for r in reasons)


def test_low_profit_pair_lock_and_drawdown_guard():
    clk = Clock()
    pm = ProtectionManager(ProtectionConfig(cooldown_minutes=0, stoploss_limit=99, lowprofit_trades=3,
                                            lowprofit_required=-0.02, max_drawdown=0.05), clock=clk)
    for _ in range(3):
        pm.record_close("SOLUSDT", -0.01, -5, "TIMEOUT")
        clk.t += 600
    st = pm.status()
    guards = {(l["pair"], l["guard"]) for l in st["locks"]}
    assert ("SOLUSDT", "LowProfitPairs") in guards
    pm.record_close("ETHUSDT", -0.04, -40, "TIMEOUT")
    assert any(l["pair"] == GLOBAL and l["guard"] == "MaxDrawdown" for l in pm.status()["locks"])


def test_locks_survive_restart_and_bad_state_fails_closed(tmp_path):
    path = tmp_path / "protections.json"
    clk = Clock()
    ProtectionManager(ProtectionConfig(cooldown_minutes=60), state_path=str(path), clock=clk).record_close("BTCUSDT", 0.0, 0, "X")
    assert ProtectionManager(state_path=str(path), clock=clk).is_locked("BTCUSDT")[0]
    path.write_text("{broken")
    assert ProtectionManager(state_path=str(path), clock=clk).is_locked("ANYUSDT")[0]


def test_riskbot_vetoes_locked_pairs():
    from cryptoscope.orchestrator.bots.risk_bot import RiskBot
    from cryptoscope.orchestrator.event_bus import EventBus
    from cryptoscope.orchestrator.events import TradeIntent

    pm = ProtectionManager(ProtectionConfig(cooldown_minutes=30))
    bot = RiskBot(EventBus(), protections=pm)
    intent = TradeIntent(symbol="BTCUSDT", direction="BUY", entry_price=100, stop_loss=95, take_profit=110)
    assert bot.check_pre_trade_risk(intent)[0]
    pm.record_close("BTCUSDT", 0.01, 1, "TAKE_PROFIT")
    ok, reasons = bot.check_pre_trade_risk(intent)
    assert not ok and any("PROTECTION_COOLDOWNPERIOD" in r for r in reasons)


# ------------------------------------------------------------------ AI journal
def _bars(closes):
    return [{"open_time": i * 60.0, "open": c, "high": c, "low": c, "close": c, "volume": 1} for i, c in enumerate(closes)]


def test_journal_records_once_per_bar_and_scores_after_horizon(tmp_path):
    j = AIJournal(str(tmp_path / "j.db"), horizon=2)
    bars = _bars([100, 101, 103, 99, 98])
    decisions = [{"system": "LLM a", "action": "BUY"}, {"system": "LLM b", "action": "SELL"}, {"system": "PM", "action": "HOLD"}]
    assert j.record("BTCUSDT", "1m", 0.0, 100, 0.005, decisions) == 3
    assert j.record("BTCUSDT", "1m", 0.0, 100, 0.005, decisions) == 0  # idempotent
    assert j.score("BTCUSDT", "1m", bars, 1) == 0                        # horizon not closed yet
    assert j.score("BTCUSDT", "1m", bars, 4) == 3
    board = {s["system"]: s for s in j.scoreboard("BTCUSDT", "1m")["systems"]}
    assert board["LLM a"]["hit"] == 1.0 and abs(board["LLM a"]["edge"] - 0.03) < 1e-9   # +3% after 2 bars
    assert board["LLM b"]["hit"] == 0.0 and board["PM"]["hit"] == 0.0


# ------------------------------------------------------------------ significance
def test_significance_detects_real_timing_and_rejects_noise():
    rng = random.Random(3)
    fwd = [rng.gauss(0, 0.02) for _ in range(300)]
    perfect = [1 if r > 0 else -1 for r in fwd]
    noise = [rng.choice([-1, 0, 1]) for _ in fwd]
    assert significance(perfect, fwd) < 0.01
    assert significance(noise, fwd) > 0.05
    assert significance([1] * 5, [0.01] * 5) is None  # too little evidence


# ------------------------------------------------------------------ paper bots
def _wave(n, amp=8.0, base=100.0, period=15.0, wiggle=0.6):
    out = []
    for i in range(1, n):
        p = base + amp * math.sin(i / period)
        out.append({"open_time": i * 60.0, "open": p, "high": p + wiggle, "low": p - wiggle, "close": p})
    return out


def test_grid_profits_in_a_range_and_conserves_inventory():
    cfg = validate("GRID", {"lower": 90, "upper": 110, "levels": 10, "investment": 1000}, 100)
    st, fills = grid_start(cfg, 100, 0)
    for c in _wave(400):
        grid_step(cfg, st, c)
    assert st["round_trips"] > 10 and st["realized"] > 0
    assert st["base"] >= -1e-12 and st["cash"] >= -1e-6


def test_grid_and_dca_validation():
    with pytest.raises(ValueError):
        validate("GRID", {"lower": 110, "upper": 120, "levels": 10, "investment": 100}, 100)  # price outside range
    with pytest.raises(ValueError):
        validate("DCA", {"investment": 100, "base_order": 50, "safety_orders": 5}, 100)      # budget too small
    with pytest.raises(ValueError):
        validate("SCALP", {}, 100)


def test_dca_takes_profit_and_starts_new_cycles():
    cfg = validate("DCA", {"investment": 1000, "base_order": 40, "safety_orders": 5, "step": 0.02, "take_profit": 0.015}, 100)
    st, _ = dca_start(cfg, 100, 0)
    for c in _wave(600, amp=6.0, period=40.0, wiggle=0.3):
        dca_step(cfg, st, c)
    assert st["cycles"] >= 3 and st["realized"] > 0


def test_order_never_fills_on_the_candle_it_was_placed():
    cfg = validate("GRID", {"lower": 90, "upper": 110, "levels": 10, "investment": 1000}, 100)
    st, _ = grid_start(cfg, 100, 60.0)
    fills = grid_step(cfg, st, {"open_time": 60.0, "open": 100, "high": 120, "low": 80, "close": 100})
    assert fills == []


def test_manager_runs_bots_on_new_candles_only_and_pauses_on_halt(tmp_path):
    import time as _t
    now = _t.time() // 60 * 60
    candles = [{"open_time": now - 600 + i * 60, "open": 100, "high": 101, "low": 95, "close": 100} for i in range(9)]
    halted = {"v": False}
    m = PaperBotManager(str(tmp_path / "bots.db"), candles=lambda s, n: candles, price=lambda s: 100.0,
                        gate=lambda: not halted["v"], period=3600)
    bot = m.create("GRID", "BTCUSDT", {"lower": 90, "upper": 110, "levels": 10, "investment": 1000}, "admin")
    # bot starts "now": the older candles above must not be replayed
    assert m.tick() == 0
    candles.append({"open_time": now + 60, "open": 100, "high": 101, "low": 95, "close": 100})
    halted["v"] = True
    assert m.tick() == 0
    m.stop_loop()
    assert m.get(bot["id"])["status"] == "RUNNING"
    m.set_status(bot["id"], "STOPPED")
    assert m.list()[0]["status"] == "STOPPED"
