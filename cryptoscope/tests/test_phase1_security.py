"""Phase 1: real local state and HTTP tests; exchange/message transports are stubs."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock, Mock

import pytest

from cryptoscope.security.config import signup_mode, validate_startup
from cryptoscope.security.halt_state import GovernorState
from cryptoscope.security.public_forms import FormGuard, validate_proposal, operator_cookie, valid_operator_cookie


def test_governor_state_missing_and_corrupt_are_closed(tmp_path):
    state = GovernorState(tmp_path / 'missing.db')
    assert state.snapshot()['halted'] is True
    assert not state.path.exists()
    state.path.write_bytes(b'not a database')
    assert state.snapshot()['halted'] is True


def test_kill_survives_a_new_process_and_cannot_clear_without_admin(tmp_path):
    state = GovernorState(tmp_path / 'shared.db')
    state.halt('regression test')
    code = 'from cryptoscope.security.halt_state import GovernorState; import sys; print(GovernorState(sys.argv[1]).snapshot()["halted"])'
    result = subprocess.run([sys.executable, '-B', '-c', code, str(state.path)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'True'
    with pytest.raises(PermissionError):
        state.resume_local_admin(admin_reauthenticated=False, actor='not-authenticated')
    assert state.snapshot()['halted'] is True


def test_gateway_and_entire_fleet_reconstruction_keep_kill(tmp_path):
    from cryptoscope.orchestrator.engine import OrchestratorEngine
    from cryptoscope.telegram.gateway import TelegramGateway
    from cryptoscope.tests.test_telegram_gateway import make_mock_update
    async def run():
        gateway = TelegramGateway(token='fixture-token', owner_chat_id=999888, owner_user_id=12345)
        await gateway.cmd_kill(make_mock_update(999888), Mock())
        rebuilt = TelegramGateway(token='fixture-token', owner_chat_id=999888, owner_user_id=12345)
        assert rebuilt.kill_switch_active is True
        strategy = Mock()
        rebuilt.strategy_bot = strategy
        context = Mock(args=['confirm'])
        await rebuilt.cmd_resume(make_mock_update(999888), context)
        strategy.resume.assert_not_called()
        with pytest.raises(PermissionError):
            rebuilt.kill_switch_active = False
        engine = OrchestratorEngine(mode='PAPER', work_dir=str(tmp_path / 'fleet'))
        assert engine.telegram.kill_switch_active is True
        assert all(bot.halt_state.snapshot()['halted'] for bot in engine.supervisor.bots.values())
        code = '''
from cryptoscope.telegram.gateway import TelegramGateway
from cryptoscope.orchestrator.engine import OrchestratorEngine
import json,sys
gateway=TelegramGateway(owner_chat_id=999888,owner_user_id=12345)
engine=OrchestratorEngine(mode='PAPER',work_dir=sys.argv[1])
print(json.dumps({'gateway_halted':gateway.kill_switch_active,
                 'fleet_halted':all(b.halt_state.snapshot()['halted'] for b in engine.supervisor.bots.values())}))
'''
        child = subprocess.run([sys.executable, '-B', '-c', code, str(tmp_path / 'fresh-process')],
                               check=True, capture_output=True, text=True)
        assert json.loads(child.stdout) == {'gateway_halted': True, 'fleet_halted': True}
    asyncio.run(run())


def test_kill_between_order_event_and_submission_prevents_order(tmp_path):
    from cryptoscope.orchestrator.event_bus import EventBus
    from cryptoscope.orchestrator.events import TradeIntent, RiskDecision, OrderRequest
    from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot
    async def run():
        bus = EventBus()
        bot = ExecutionBot(bus, mode='TESTNET', db_path=str(tmp_path / 'execution.db'))
        bot.binance_client.create_order = Mock(side_effect=AssertionError('No exchange request allowed'))
        intent = TradeIntent(symbol='BTCUSDT', direction='BUY', entry_price=100, stop_loss=95, take_profit=110)
        bot.cached_intents[intent.intent_id] = intent
        async def halt(_event):
            GovernorState().halt('kill during event propagation')
        bus.subscribe(OrderRequest, halt)
        await bot._execute_approved_trade(RiskDecision(intent_id=intent.intent_id, symbol='BTCUSDT', decision='APPROVED', approved_quantity=1))
        bot.binance_client.create_order.assert_not_called()
        assert bot.active_positions == {}
    asyncio.run(run())


def test_every_bot_reloads_halt_and_restart_restores_subscription():
    from cryptoscope.orchestrator.bots.analyst_bot import AnalystBot
    from cryptoscope.orchestrator.event_bus import EventBus
    from cryptoscope.orchestrator.events import MarketUpdate
    async def run():
        bus = EventBus()
        bot = AnalystBot(bus)
        await bot.start()
        await bot.stop()
        await bot.start()
        assert len(bus._subscribers.get('MarketUpdate', [])) == 1
        assert bot.halt_state.snapshot()['halted'] is False
        GovernorState().halt('other process or gateway')
        assert bot.halt_state.snapshot()['halted'] is True
        await bot.stop()
    asyncio.run(run())


def test_admin_recovery_does_not_leave_a_second_emergency_latch():
    from cryptoscope.orchestrator.bots.strategy_bot import StrategyBot
    from cryptoscope.orchestrator.event_bus import EventBus
    bot = StrategyBot(EventBus())
    GovernorState().halt('test emergency')
    bot.pause('Emergency kill')
    assert bot.paused is True
    GovernorState().resume_local_admin(admin_reauthenticated=True, actor='fixture-admin')
    assert bot.paused is False
    bot.pause('Ordinary operator pause')
    GovernorState().halt('test emergency')
    GovernorState().resume_local_admin(admin_reauthenticated=True, actor='fixture-admin')
    assert bot.paused is True


@pytest.mark.parametrize('environment, mode', [
    ({'TRADING_MODE': 'TESTNET'}, 'PAPER'),
    ({'TRADING_MODE': 'LIVE'}, None),
    ({'SIGNUP_MODE': 'open'}, None),
    ({'TRADING_MODE': 'TESTNET', 'BINANCE_TESTNET_API_KEY': 'fixture-only'}, None),
    ({'EXCHANGE_API_KEY': 'fixture-only'}, None),
    ({'BINANCE_TESTNET_BASE_URL': 'https://api.binance.com'}, None),
    ({'TELEGRAM_BOT_TOKEN': 'fixture-only', 'TELEGRAM_OWNER_CHAT_ID': '123'}, None),
])
def test_startup_rejects_ambiguous_or_incomplete_configuration(environment, mode):
    with pytest.raises(ValueError):
        validate_startup(mode, environment)


def test_safe_defaults_and_explicit_open_signup():
    assert validate_startup(environment={}) == 'PAPER'
    assert signup_mode({}) == 'invite'
    assert signup_mode({'SIGNUP_MODE': 'open', 'ALLOW_OPEN_SIGNUP': 'true'}) == 'open'
    assert validate_startup(environment={'TRADING_MODE': 'TESTNET', 'BINANCE_TESTNET_API_KEY': 'fixture-only', 'BINANCE_TESTNET_API_SECRET': 'fixture-only'}) == 'TESTNET'


@pytest.mark.parametrize('module,extra', [('cryptoscope.orchestrator', ['--mode', 'PAPER']), ('cryptoscope.dashboard', [])])
def test_real_cli_refuses_unsafe_settings_before_service_start(tmp_path, module, extra):
    env = dict(os.environ)
    env.update(SIGNUP_MODE='open', TRADING_MODE='TESTNET')
    env.pop('ALLOW_OPEN_SIGNUP', None)
    result = subprocess.run([sys.executable, '-B', '-m', module, *extra], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'Open signup requires an explicit' in result.stderr
    assert not (tmp_path / 'work').exists()


def proposal():
    return {'name': 'Fixture Researcher', 'email': 'fixture@example.invalid', 'github': 'fixture-user',
            'linkedin': 'fixture-user', 'message': 'Research fixture for security validation.'}


@pytest.mark.parametrize('change', [
    {'name': ['bad']}, {'message': 'x' * 4001}, {'github': 'javascript:alert(1)'},
    {'linkedin': 'https://wrong.invalid/profile'}, {'website': 'http://unsafe.invalid'},
    {'fax': 'automation'}, {'email': 'not-an-address'}, {'message': 'tiny'},
])
def test_public_form_rejects_abuse(change):
    with pytest.raises(ValueError):
        validate_proposal({**proposal(), **change})


def test_form_quota_duplicate_expiry_and_operator_authentication():
    guard = FormGuard()
    data = validate_proposal(proposal())
    assert guard.accept(data, 'fixture-client', now=0)
    assert not guard.accept(data, 'fixture-client', now=1)
    for n in range(4):
        assert guard.accept({**data, 'message': str(n)}, 'fixture-client', now=2)
    assert not guard.accept({**data, 'message': 'next'}, 'fixture-client', now=3)
    assert guard.accept(data, 'fixture-client', now=901)
    code = 'fictional-operator-fixture'
    cookie = operator_cookie(code, now=1000)
    assert code not in cookie
    assert valid_operator_cookie(cookie, code, now=1001)
    assert not valid_operator_cookie(cookie, 'rotated-fixture', now=1001)
    assert not valid_operator_cookie(code, code, now=1001)
    assert not valid_operator_cookie(cookie, code, now=606000)


def test_example_environment_has_no_values_and_no_legacy_exchange_names():
    root = Path(__file__).resolve().parents[2]
    settings = dict(line.split('=', 1) for line in (root / '.env.example').read_text().splitlines()
                    if line.strip() and not line.startswith('#') and '=' in line)
    assert all(not value for value in settings.values())
    assert {'BINANCE_TESTNET_API_KEY', 'BINANCE_LIVE_API_KEY', 'ALLOW_OPEN_SIGNUP'} <= settings.keys()
    assert 'EXCHANGE_API_KEY' not in settings


def test_blank_optional_url_uses_the_approved_default(monkeypatch):
    from cryptoscope.execution.binance_testnet import BinanceTestnetClient
    monkeypatch.setenv('BINANCE_TESTNET_BASE_URL', '')
    assert BinanceTestnetClient().base_url == 'https://testnet.binance.vision'


def test_client_error_and_representation_do_not_echo_sensitive_server_text(monkeypatch, caplog):
    import io
    from urllib.error import HTTPError
    from cryptoscope.execution.binance_testnet import BinanceTestnetClient, BinanceAuthError
    fixture = 'fictional-credential-fixture'
    client = BinanceTestnetClient(api_key=fixture, api_secret=fixture)
    assert fixture not in repr(client)
    assert client.masked_api_key == '<CONFIGURED>'
    payload = json.dumps({'code': -2015, 'msg': fixture}).encode()
    def reject(*_args, **_kwargs):
        raise HTTPError('https://testnet.binance.vision', 401, 'Unauthorized', {}, io.BytesIO(payload))
    monkeypatch.setattr('urllib.request.urlopen', reject)
    with pytest.raises(BinanceAuthError) as failure:
        client._request('GET', '/api/v3/ping')
    assert failure.value.code == -2015
    assert fixture not in str(failure.value)
    assert fixture not in caplog.text


def test_telegram_delivery_error_does_not_echo_transport_error(caplog):
    from cryptoscope.telegram.gateway import TelegramGateway
    async def run():
        gateway = TelegramGateway(token='fixture-token', owner_chat_id=999888, owner_user_id=12345)
        gateway.app = Mock()
        gateway.app.bot.send_message = AsyncMock(side_effect=RuntimeError('fictional-transport-fixture'))
        with pytest.raises(ConnectionError) as failure:
            await gateway.send_alert('fixture message; no network transport')
        assert 'fictional-transport-fixture' not in str(failure.value)
        assert 'fictional-transport-fixture' not in caplog.text
    asyncio.run(run())
