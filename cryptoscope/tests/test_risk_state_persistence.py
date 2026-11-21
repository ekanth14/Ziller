"""RiskBot breaker state must survive restarts and roll over at the UTC day boundary."""
import json

from cryptoscope.orchestrator.bots.risk_bot import RiskBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import PositionClosed


def _bot(path, **kw):
    return RiskBot(EventBus(), initial_nav=10000.0, max_daily_loss_pct=0.03, state_path=str(path), **kw)


def test_daily_loss_breaker_survives_restart(tmp_path):
    path = tmp_path / "risk_state.json"
    bot = _bot(path)
    bot._handle_position_closed(PositionClosed(symbol="BTCUSDT", pnl_usd=-400.0))  # > 3% of 10k
    assert bot.daily_loss_circuit_breaker
    # restart
    again = _bot(path)
    assert again.daily_loss_circuit_breaker
    assert again.daily_realized_pnl == -400.0
    assert again.current_nav == 9600.0 and again.peak_nav == 10000.0


def test_drawdown_latch_and_peak_survive_restart(tmp_path):
    path = tmp_path / "risk_state.json"
    bot = _bot(path)
    bot.observe_portfolio_nav(11000.0)
    bot.observe_portfolio_nav(9800.0)  # > 10% below the 11000 peak
    assert bot.drawdown_circuit_breaker
    again = _bot(path)
    assert again.drawdown_circuit_breaker and again.peak_nav == 11000.0


def test_daily_figures_reset_on_new_utc_day_but_drawdown_latch_stays(tmp_path):
    path = tmp_path / "risk_state.json"
    bot = _bot(path)
    bot._handle_position_closed(PositionClosed(symbol="BTCUSDT", pnl_usd=-400.0))
    bot.observe_portfolio_nav(8000.0)
    data = json.loads(path.read_text())
    data["day"] = "2000-01-01"
    path.write_text(json.dumps(data))
    again = _bot(path)
    assert again.daily_realized_pnl == 0.0 and not again.daily_loss_circuit_breaker
    assert again.drawdown_circuit_breaker  # never silently reset by a day roll


def test_running_bot_rolls_the_day(tmp_path):
    bot = _bot(tmp_path / "risk_state.json")
    bot._handle_position_closed(PositionClosed(symbol="BTCUSDT", pnl_usd=-400.0))
    bot._day = "2000-01-01"  # simulate the process outliving a UTC midnight
    bot._roll_day()
    assert bot.daily_realized_pnl == 0.0 and not bot.daily_loss_circuit_breaker


def test_unreadable_state_fails_closed(tmp_path):
    path = tmp_path / "risk_state.json"
    path.write_text("{not json")
    assert _bot(path).drawdown_circuit_breaker


def test_no_state_path_keeps_previous_in_memory_behaviour(tmp_path):
    bot = RiskBot(EventBus(), initial_nav=10000.0)
    bot._handle_position_closed(PositionClosed(symbol="BTCUSDT", pnl_usd=-400.0))
    assert bot.daily_loss_circuit_breaker
    assert not (tmp_path / "risk_state.json").exists()
