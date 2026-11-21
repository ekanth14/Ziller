"""QuantConnect LEAN-inspired features: fills, time stop, spread guard, trailing stop, statistics,
report data, rotation weighting and signal-source scoring."""
import asyncio
import math
import random
import sqlite3
import time

import pytest

from cryptoscope.execution import fill_model as fm


def test_fill_model_rules():
    assert fm.market_fill("BUY", 100, (99.9, 100.1)) == 100.1 and fm.market_fill("SELL", 100, (99.9, 100.1)) == 99.9
    assert fm.market_fill("BUY", 100, None, 0.001) == pytest.approx(100.1)
    assert fm.spread_ok((99.0, 101.0), 0.003) == (False, pytest.approx(0.02))
    assert fm.spread_ok(None, 0.003) == (True, None)                         # no book: no opinion
    assert fm.long_exit(98.0, 99.0, 102.0, None, 0, slippage=0) == ("STOP_LOSS", 98.0)   # gapped through: worse fill
    assert fm.long_exit(99.0, 99.0, 102.0, None, 0) == ("STOP_LOSS", 99.0)
    assert fm.long_exit(103.0, 99.0, 102.0, None, 0) == ("TAKE_PROFIT", 103.0)
    assert fm.long_exit(100.0, 99.0, 102.0, 50, 60, slippage=0) == ("TIME_STOP", 100.0)
    assert fm.long_exit(100.0, 99.0, 102.0, 50, 40) is None
    assert fm.trail_stop(99.0, 110.0, 0.05) == pytest.approx(104.5) and fm.trail_stop(105.0, 100.0, 0.05) == 105.0
    assert fm.trail_stop(99.0, 110.0, None) == 99.0


class _NotHalted:
    def snapshot(self):
        return {"halted": False}

    def halt(self, *a):
        raise AssertionError("must not halt")


def _exec_bot(tmp_path, realism):
    from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot
    from cryptoscope.orchestrator.event_bus import EventBus
    bot = ExecutionBot(EventBus(), mode="PAPER", db_path=str(tmp_path / "ex.db"), fill_realism=realism)
    bot.halt_state = _NotHalted()
    out = []

    async def emit(ev):
        out.append(ev)
    bot.emit = emit
    return bot, out


def _buy(bot, horizon=16):
    from cryptoscope.orchestrator.events import RiskDecision, TradeIntent
    it = TradeIntent(symbol="XRPUSDT", direction="BUY", entry_price=1.0, stop_loss=0.99, take_profit=1.02,
                     horizon_bars=horizon)
    bot.cached_intents[it.intent_id] = it
    asyncio.run(bot._execute_approved_trade(RiskDecision(intent_id=it.intent_id, symbol="XRPUSDT",
                                                         decision="APPROVED", approved_quantity=100,
                                                         position_size_usd=100)))


def test_paper_entry_fills_at_ask_and_spread_guard(tmp_path):
    bot, out = _exec_bot(tmp_path, True)
    bot.book = fm.BookSource(fetch=lambda s: (1.000, 1.002), ttl=0)
    _buy(bot)
    assert bot.active_positions["XRPUSDT"]["entry_price"] == 1.002            # the ask, not the signal price
    bot2, _ = _exec_bot(tmp_path / "b", True)
    bot2.book = fm.BookSource(fetch=lambda s: (1.0, 1.01), ttl=0)              # ~1% spread > 0.3%
    _buy(bot2)
    assert "XRPUSDT" not in bot2.active_positions and bot2.spread_skips == 1


def test_time_stop_closes_expired_positions(tmp_path):
    from cryptoscope.orchestrator.events import MarketUpdate, PositionClosed
    for realism in (False, True):
        bot, out = _exec_bot(tmp_path / str(realism), realism)
        if realism:
            bot.book = fm.BookSource(fetch=lambda s: None, ttl=0)
        _buy(bot)
        bot.active_positions["XRPUSDT"]["expires_at"] = time.time() - 1
        asyncio.run(bot._check_position_exits(MarketUpdate(symbol="XRPUSDT", price=1.005)))
        closed = [e for e in out if isinstance(e, PositionClosed)]
        assert closed and closed[0].exit_reason == "TIME_STOP" and "XRPUSDT" not in bot.active_positions


def test_gap_through_stop_fills_at_market_with_realism(tmp_path):
    from cryptoscope.orchestrator.events import MarketUpdate, PositionClosed
    bot, out = _exec_bot(tmp_path, True)
    bot.book = fm.BookSource(fetch=lambda s: None, ttl=0)
    _buy(bot)
    asyncio.run(bot._check_position_exits(MarketUpdate(symbol="XRPUSDT", price=0.95)))   # far below 0.99 stop
    c = next(e for e in out if isinstance(e, PositionClosed))
    assert c.exit_reason == "STOP_LOSS" and c.exit_price < 0.99


def test_lean_statistics_known_values():
    from core.quant import metrics_extra as mx
    rnd = random.Random(4)
    b = [rnd.gauss(0.001, 0.02) for _ in range(500)]
    r = [2 * x for x in b]                                                    # beta exactly 2
    st = mx.capm_stats(r, b, 365)
    assert st["beta"] == pytest.approx(2.0) and st["alpha"] == pytest.approx(0.0, abs=1e-9)
    t = mx.trade_stats_lean([0.02, 0.01, -0.01, -0.01, -0.01, 0.03])
    assert t["max_consecutive_wins"] == 2 and t["max_consecutive_losses"] == 3
    assert t["profit_loss_ratio"] == pytest.approx(2.0) and t["lean_expectancy"] == pytest.approx(0.5 * 2 - 0.5)
    assert mx.var_parametric([0.0] * 10) is None and mx.var_parametric(b, 0.99) > mx.var_parametric(b, 0.95)
    curve, times = [1, 1.2, 0.9, 1.3, 1.1, 1.0], [0, 1, 2, 3, 4, 5]
    dd = mx.drawdown_periods(curve, times)
    assert dd[0]["depth"] == pytest.approx(0.75 - 1) and dd[0]["recovered"] is True        # 1.2 -> 0.9, back by 1.3
    assert dd[1]["depth"] == pytest.approx(1.0 / 1.3 - 1) and dd[1]["recovered"] is False  # 1.3 -> 1.0, still under
    day = 86400
    m = mx.monthly_returns([1.0, 1.1, 1.21], [0, 31 * day, 59 * day])          # Jan, Feb, Mar 1970
    assert [x["month"] for x in m] == [1, 2, 3] and m[1]["ret"] == pytest.approx(0.1)


def test_lab_rows_include_lean_report():
    from cryptoscope.desk.strategy_lab import run_lab
    rnd, p, c = random.Random(9), 100.0, []
    for i in range(500):
        o = p
        p *= math.exp(rnd.gauss(0.0005, 0.02))
        c.append({"open_time": 1_700_000_000 + i * 86400, "open": o, "high": max(o, p) * 1.01,
                  "low": min(o, p) * 0.99, "close": p, "volume": 1000})
    r0 = run_lab(c, "1d", 10, only=["donchian"], catalog=False)["results"][0]
    r5 = run_lab(c, "1d", 10, only=["donchian"], catalog=False, slippage_bps=5)["results"][0]
    for k in ("beta", "alpha", "information_ratio", "var95", "avg_mae", "avg_mfe", "max_consecutive_losses", "report"):
        assert k in r0, k
    assert set(r0["report"]) >= {"monthly", "drawdowns", "rolling_sharpe", "trade_returns"}
    assert r0["avg_mae"] <= 0 <= r0["avg_mfe"]
    assert r5["total_return"] < r0["total_return"]                            # slippage costs money


def test_rotation_weighting_schemes():
    from cryptoscope.desk.rotation import _weights, rotation_backtest
    closes = {"A": [100 * (1.01 ** i) for i in range(40)], "B": [100 * (1.01 ** i) * (1 + 0.05 * (-1) ** i) for i in range(40)]}
    w = _weights(["A", "B"], "inverse_vol", closes, 39, {})
    assert w["A"] > w["B"] and sum(w.values()) == pytest.approx(1)              # calmer coin gets more weight
    assert _weights(["A", "B"], "score", closes, 39, {"A": 0.9, "B": 0.3})["A"] == pytest.approx(0.75)
    assert _weights(["A", "B"], "equal", closes, 39, {}) == {"A": 0.5, "B": 0.5}
    with pytest.raises(ValueError):
        rotation_backtest(closes, [1.0] * 40, list(range(40)), weighting="magic")


def test_signal_source_scoring(tmp_path):
    from cryptoscope.desk.insight_scores import score_signals
    db = sqlite3.connect(tmp_path / "trading_journal.db")
    db.execute("CREATE TABLE signals(timestamp REAL, signal_id TEXT, symbol TEXT, direction TEXT, confidence REAL,"
               " reasons TEXT, strategy_id TEXT)")
    t0 = 1_700_000_000 - 1_700_000_000 % 900
    rows = []
    for i in range(0, 200, 5):
        rows.append((t0 + i * 900 + 10, "s", "AUSDT", "BUY", 0.7, "", "good"))
        rows.append((t0 + i * 900 + 20, "s", "AUSDT", "BUY", 0.7, "", "good"))      # same bar: deduped
        rows.append((t0 + i * 900 + 10, "s", "AUSDT", "SELL", 0.7, "", "bad"))
    db.executemany("INSERT INTO signals VALUES(?,?,?,?,?,?,?)", rows)
    db.commit(); db.close()
    bars = [{"open_time": t0 + i * 900, "close": 100 * 1.001 ** i} for i in range(300)]   # steady rise
    r = score_signals(tmp_path, horizon=16, klines=lambda s: bars, now=t0 + 400 * 900)
    by = {x["source"]: x for x in r["sources"]}
    assert by["good"]["signals"] == 40 and by["good"]["direction_score"] == 1.0
    assert by["bad"]["direction_score"] == 0.0 and by["bad"]["edge"] < 0 < by["good"]["avg_fwd_return"]
