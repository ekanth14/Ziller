"""P&L quality stats: break-even win rate and per-trade Sharpe."""
from cryptoscope.desk.pnl import trade_stats


def _t(i, pnl):
    return {"timestamp": 1000 + i, "pnl_usd": pnl, "duration_seconds": 60}


def test_breakeven_win_rate_and_sharpe():
    # avg win 3, avg loss 7 -> must win 70% of trades just to break even; actual win rate is 50%
    s = trade_stats([_t(0, 3), _t(1, -7), _t(2, 3), _t(3, -7)], 10_000)
    assert abs(s["breakeven_win_rate"] - 0.7) < 1e-9 and s["win_rate"] == 0.5
    assert s["sharpe_per_trade"] is not None and s["sharpe_per_trade"] < 0


def test_stats_with_no_trades():
    s = trade_stats([], 10_000)
    assert s["breakeven_win_rate"] is None and s["sharpe_per_trade"] is None
