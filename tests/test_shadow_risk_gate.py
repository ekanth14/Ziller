"""Differential tests: OCaml shadow risk gate vs Python RiskGovernor.check_pre_trade.

The protocol tests always run. The differential tests need the OCaml binary
(cd ocaml/risk_gate && dune build, or set ZILLERS_RISK_GATE_BIN) and are skipped otherwise.
"""
import random

import pytest

from cryptoscope.execution.governor import RiskGovernor
from cryptoscope.execution import shadow_gate as sg

BINARY = sg.find_binary()
needs_binary = pytest.mark.skipif(BINARY is None, reason="OCaml risk gate binary not built")


class _NoAlerts:
    def dispatch(self, *a, **k):
        pass


def _governor(**kw):
    return RiskGovernor(alert_service=_NoAlerts(), **kw)


def _request(**over):
    base = dict(
        symbol="BTCUSDT", action="BUY", requested_value=100.0, total_portfolio_equity=10000.0,
        current_open_orders_count=1, feed_age_seconds=0.5, cross_source_divergence_pct=0.1,
        day_pnl=0.0, day_start_equity=10000.0,
    )
    base.update(over)
    return base


# ---------------------------------------------------------------- protocol (always run)
def test_build_line_contains_config_state_and_request():
    g = _governor(symbol_allowlist=["btcusdt", "ethusdt"])
    g.trade_timestamps = [1.5, 2.5]
    g.last_loss_time = 3.0
    line = sg.build_line(g, now=100.0, **_request())
    kv = dict(p.split("=", 1) for p in line.split("|"))
    assert kv["cfg.symbol_allowlist"] == "BTCUSDT,ETHUSDT"
    assert kv["st.trade_timestamps"] == "1.5,2.5"
    assert kv["st.last_loss_time"] == "3.0"
    assert kv["req.now"] == "100.0"
    assert "req.token_present" not in kv


def test_build_line_rejects_protocol_characters():
    with pytest.raises(ValueError):
        sg.build_line(_governor(), now=1.0, **_request(symbol="BTC|USDT"))


def test_build_line_token_audit():
    line = sg.build_line(_governor(), now=1.0, token_audit={"band": "DANGER", "score": 40}, **_request())
    assert "req.token_present=1" in line and "req.token_band=DANGER" in line


def test_parse_output():
    v = sg.parse_output("REJECT|reasons=STALE_FEED,MAX_ORDERS_EXCEEDED|halted=0|peak=10000")
    assert not v.allowed and v.codes == ["STALE_FEED", "MAX_ORDERS_EXCEEDED"] and not v.halted
    assert sg.parse_output("ALLOW|reasons=|halted=0|peak=1.5").allowed
    assert sg.parse_output("ERROR|boom").error == "ERROR|boom"


# ---------------------------------------------------------------- differential (need binary)
@needs_binary
def test_known_scenarios_match():
    scenarios = [
        {},
        {"feed_age_seconds": 9.0},
        {"cross_source_divergence_pct": 2.5},
        {"action": "SHORT"},
        {"requested_value": 5000.0},
        {"current_open_orders_count": 10},
        {"day_pnl": -400.0},
        {"total_portfolio_equity": 8500.0},
        {"symbol": "dogeusdt"},
    ]
    for over in scenarios:
        g = _governor(symbol_allowlist=["BTCUSDT"])
        g.peak_equity = 10000.0
        res = sg.shadow_check(g, BINARY, now=1_000_000.0, **_request(**over))
        assert res.match, (over, res.differences)


@needs_binary
def test_emergency_halt_short_circuits():
    g = _governor()
    g.emergency_halted = True
    g.halt_reason = "test"
    res = sg.shadow_check(g, BINARY, now=5.0, **_request())
    assert res.match and res.python_codes == ["EMERGENCY_HALT_ACTIVE"]


@needs_binary
def test_randomized_equivalence():
    rng = random.Random(20261116)
    pick = lambda *vals: rng.choice(vals)  # noqa: E731
    mismatches = []
    for i in range(400):
        g = _governor(
            max_position_fraction=pick(0.05, 0.1, 0.25),
            max_open_orders=pick(1, 5, 10),
            daily_loss_limit_fraction=pick(0.01, 0.03, 0.05),
            total_drawdown_limit_fraction=pick(0.05, 0.1),
            max_trades_per_day=pick(1, 3, 50),
            loss_cooldown_seconds=pick(0.0, 60.0, 900.0),
            symbol_allowlist=pick([], ["BTCUSDT"], ["BTCUSDT", "ETHUSDT"]),
            max_feed_age_seconds=pick(1.0, 5.0),
            max_divergence_pct=pick(0.5, 1.0),
        )
        now = 1_700_000_000.0 + rng.uniform(0, 1e5)
        g.emergency_halted = rng.random() < 0.08
        g.peak_equity = pick(0.0, 5000.0, 10000.0, 12000.0)
        g.trade_timestamps = [now - rng.uniform(0, 2 * 86400) for _ in range(rng.randint(0, 6))]
        g.last_loss_time = pick(None, now - 10.0, now - 900.0, now - 5000.0)
        equity = pick(0.0, 9000.0, 10000.0, 10800.0, 12000.0 * (1 - g.total_drawdown_limit_fraction))
        req = _request(
            symbol=pick("BTCUSDT", "ethusdt", "DOGEUSDT"),
            action=pick("BUY", "LONG", "CLOSE", "SELL", "SHORT", "buy"),
            requested_value=pick(0.0, 100.0, equity * g.max_position_fraction, equity * g.max_position_fraction + 0.01, 1e6),
            total_portfolio_equity=equity,
            current_open_orders_count=rng.randint(0, 12),
            feed_age_seconds=pick(0.0, g.max_feed_age_seconds, g.max_feed_age_seconds + 0.1, 30.0),
            cross_source_divergence_pct=pick(0.0, g.max_divergence_pct, g.max_divergence_pct + 0.01, 5.0),
            day_pnl=pick(0.0, 50.0, -10000.0 * g.daily_loss_limit_fraction, -10000.0 * g.daily_loss_limit_fraction - 1, -9000.0),
            day_start_equity=pick(0.0, 10000.0),
        )
        token = pick(None, {"band": "OK", "score": 80}, {"band": "DANGER", "score": 90}, {"band": "OK", "score": 64}, {"band": "OK", "score": 65})
        res = sg.shadow_check(g, BINARY, now=now, token_audit=token, **req)
        if not res.match:
            mismatches.append((i, res.differences))
    assert not mismatches, mismatches[:5]
