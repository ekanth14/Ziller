"""Disposable operations checks. Broker tests use explicit stubs, never an exchange."""
import asyncio
from contextlib import closing
import json
from pathlib import Path
from unittest.mock import MagicMock,patch

import pytest

from cryptoscope.ops.databases import backup_and_verify,inventory
from cryptoscope.ops.telemetry import process_metrics
from cryptoscope.storage.sqlite import connect_database
from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import MarketUpdate,TradeIntent,RiskDecision
from cryptoscope.security.halt_state import GovernorState


def test_backup_restore_preserves_source_and_old_backups(tmp_path):
    source=tmp_path/'work/runtime/example.db';source.parent.mkdir(parents=True)
    with closing(connect_database(source)) as db:
        db.execute('CREATE TABLE data(value TEXT)');db.execute("INSERT INTO data VALUES ('fixture')");db.commit()
    destination=tmp_path/'work/backups/new'
    result=backup_and_verify(tmp_path,destination)
    assert result['passed'] and any(m['path'].endswith('example.db') for m in result['databases'])
    with pytest.raises(FileExistsError):backup_and_verify(tmp_path,destination)
    with closing(connect_database(source,readonly=True)) as db:
        assert db.execute('SELECT value FROM data').fetchone()[0]=='fixture'
        assert db.execute('PRAGMA busy_timeout').fetchone()[0]==5000
        assert db.execute('PRAGMA journal_mode').fetchone()[0]=='wal'


def test_metrics_are_actual_process_observations():
    result=process_metrics()
    assert result['pid']>0 and result['threads']>0
    assert result['rss_mb'] is None or result['rss_mb']>0
    assert result['sockets'] is None or result['sockets']>=0


def test_backup_without_databases_cannot_report_success(tmp_path):
    import subprocess,sys
    empty=tmp_path/'empty';empty.mkdir()
    result=backup_and_verify(empty,tmp_path/'retained-empty-snapshot')
    assert result['databases']==[] and result['passed'] is False
    command=[sys.executable,'-B','-m','scripts.run_database_backups','--root',str(empty)]
    assert subprocess.run(command,capture_output=True,timeout=15).returncode==1


def test_windows_metrics_reuse_ctypes_definitions():
    import os
    if os.name!='nt':pytest.skip('Windows native telemetry')
    from cryptoscope.ops.telemetry import _windows_types
    first=_windows_types()
    for _ in range(20):process_metrics()
    assert _windows_types() is first
    assert _windows_types.cache_info().currsize==1


def test_legacy_execution_migration_retains_rows_and_marks_unknown_provenance(tmp_path):
    path=tmp_path/'legacy.db'
    with closing(connect_database(path)) as db:
        db.execute('CREATE TABLE positions(symbol TEXT PRIMARY KEY,side TEXT,quantity REAL,entry_price REAL,stop_price REAL,target_price REAL,stop_order_id TEXT,created_at REAL,updated_at REAL)')
        db.execute("INSERT INTO positions VALUES ('BTCUSDT','BUY',.01,100,95,110,'11',1,1)")
        db.commit()
    bot=ExecutionBot(EventBus(),mode='TESTNET',db_path=str(path))
    assert bot.active_positions['BTCUSDT']['mode']=='UNKNOWN'
    assert bot.halt_state.snapshot()['halted']
    with closing(connect_database(path,readonly=True)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM positions').fetchone()[0]==1


def test_future_execution_schema_is_rejected(tmp_path):
    path=tmp_path/'future.db'
    with closing(connect_database(path)) as db:db.execute('PRAGMA user_version=2')
    with pytest.raises(RuntimeError,match='newer'):
        ExecutionBot(EventBus(),mode='TESTNET',db_path=str(path))


def position():
    return dict(symbol='BTCUSDT',side='BUY',quantity=.01,entry_price=100,
                stop_price=95,target_price=110,stop_order_id='11',mode='TESTNET')


def make_bot(tmp_path):
    bot=ExecutionBot(EventBus(),mode='TESTNET',db_path=str(tmp_path/'execution.db'))
    bot.binance_client=MagicMock()
    return bot


def test_failed_testnet_flatten_preserves_exposure_and_restart_reference(tmp_path):
    async def run():
        bot=make_bot(tmp_path);pos=position();bot.active_positions['BTCUSDT']=pos;bot._save_position_db(pos)
        bot.binance_client.get_order.return_value=dict(status='NEW',executedQty='0')
        bot.binance_client.cancel_order.return_value=dict(status='CANCELED',executedQty='0')
        bot.binance_client.create_order.side_effect=TimeoutError('fixture')
        assert await bot.flatten_all_positions()==0
        assert 'BTCUSDT' in bot.active_positions and bot.halt_state.snapshot()['halted']
        restarted=make_bot(tmp_path)
        assert restarted.active_positions['BTCUSDT']['exit_client_id']==pos['exit_client_id']
    asyncio.run(run())


def test_target_exit_uses_confirmed_exchange_fill(tmp_path):
    async def run():
        bot=make_bot(tmp_path);pos=position();bot.active_positions['BTCUSDT']=pos;bot._save_position_db(pos)
        bot.binance_client.get_order.return_value=dict(status='NEW',executedQty='0')
        bot.binance_client.cancel_order.return_value=dict(status='CANCELED',executedQty='0')
        bot.binance_client.create_order.return_value=dict(status='FILLED',executedQty='.01',cummulativeQuoteQty='1.1')
        await bot._check_position_exits(MarketUpdate(symbol='BTCUSDT',price=110))
        assert 'BTCUSDT' not in bot.active_positions
        assert bot.binance_client.create_order.call_args.kwargs['side']=='SELL'
    asyncio.run(run())


def test_already_filled_stop_never_sends_second_sell(tmp_path):
    bot=make_bot(tmp_path)
    bot.binance_client.get_order.return_value=dict(status='FILLED',executedQty='.01',cummulativeQuoteQty='.95')
    assert bot._confirmed_testnet_close('BTCUSDT',position())==95
    bot.binance_client.create_order.assert_not_called()


def test_stop_rejection_halts_and_tracks_actual_entry_without_fake_stop(tmp_path):
    async def run():
        bot=make_bot(tmp_path)
        bot.binance_client.create_order.side_effect=[dict(status='FILLED',executedQty='.01',cummulativeQuoteQty='1',orderId=10),RuntimeError('fixture stop rejection')]
        intent=TradeIntent(intent_id='fixture',symbol='BTCUSDT',entry_price=100,stop_loss=95,take_profit=110)
        bot.cached_intents[intent.intent_id]=intent
        await bot._execute_approved_trade(RiskDecision(intent_id='fixture',symbol='BTCUSDT',decision='APPROVED',approved_quantity=.01))
        assert bot.active_positions['BTCUSDT']['stop_order_id'] is None
        assert bot.halt_state.snapshot()['halted']
    asyncio.run(run())


def test_partial_entry_is_retained_as_uncertain_and_halts(tmp_path):
    async def run():
        bot=make_bot(tmp_path)
        bot.binance_client.create_order.return_value=dict(status='PARTIALLY_FILLED',executedQty='.005',cummulativeQuoteQty='.5',orderId=10)
        intent=TradeIntent(intent_id='partial',symbol='BTCUSDT',entry_price=100,stop_loss=95,take_profit=110)
        bot.cached_intents[intent.intent_id]=intent
        await bot._execute_approved_trade(RiskDecision(intent_id='partial',symbol='BTCUSDT',decision='APPROVED',approved_quantity=.01))
        assert bot.halt_state.snapshot()['halted']
        with closing(connect_database(bot.db_path,readonly=True)) as db:
            assert db.execute("SELECT count(*) FROM orders WHERE status='RECONCILE_REQUIRED'").fetchone()[0]>0
    asyncio.run(run())


def test_persisted_client_reference_matches_sent_entry_and_blocks_duplicate(tmp_path):
    async def run():
        bot=make_bot(tmp_path)
        bot.binance_client.create_order.side_effect=TimeoutError('fixture lost response')
        intent=TradeIntent(intent_id='long-intent-identity-'*5,symbol='BTCUSDT',entry_price=100,stop_loss=95,take_profit=110)
        bot.cached_intents[intent.intent_id]=intent
        decision=RiskDecision(intent_id=intent.intent_id,symbol='BTCUSDT',decision='APPROVED',approved_quantity=.01)
        await bot._execute_approved_trade(decision)
        sent=bot.binance_client.create_order.call_args.kwargs['client_order_id']
        with closing(connect_database(bot.db_path,readonly=True)) as db:
            assert db.execute('SELECT order_id FROM orders').fetchone()[0]==sent
        # Even a new instance must preserve the unresolved reference and halt.
        restarted=make_bot(tmp_path)
        restarted.cached_intents[intent.intent_id]=intent
        await restarted._execute_approved_trade(decision)
        restarted.binance_client.create_order.assert_not_called()
    asyncio.run(run())


def test_nonfinite_close_response_retains_position(tmp_path):
    bot=make_bot(tmp_path)
    bot.binance_client.get_order.return_value=dict(status='FILLED',executedQty='NaN',cummulativeQuoteQty='1')
    assert bot._confirmed_testnet_close('BTCUSDT',position()) is None
    assert bot.halt_state.snapshot()['halted']


def test_durable_master_flatten_reaches_execution_and_keeps_halt(tmp_path):
    async def run():
        bot=make_bot(tmp_path);pos=position();bot.active_positions['BTCUSDT']=pos;bot._save_position_db(pos)
        bot.binance_client.get_order.return_value=dict(status='NEW',executedQty='0')
        bot.binance_client.cancel_order.return_value=dict(status='CANCELED',executedQty='0')
        bot.binance_client.create_order.return_value=dict(status='FILLED',executedQty='.01',cummulativeQuoteQty='1')
        bot.halt_state.halt('fixture master request','test-admin','HALT_FLATTEN')
        assert await bot.apply_emergency_action()==1
        assert not bot.active_positions and bot.halt_state.snapshot()['halted']
        assert await bot.apply_emergency_action()==0
        assert bot.binance_client.create_order.call_count==1
    asyncio.run(run())


def test_plain_halt_keeps_exchange_protection_and_exposure(tmp_path):
    async def run():
        bot=make_bot(tmp_path);bot.active_positions['BTCUSDT']=position()
        bot.halt_state.halt('fixture plain halt','test-admin','HALT')
        assert await bot.apply_emergency_action()==0
        assert 'BTCUSDT' in bot.active_positions
        bot.binance_client.create_order.assert_not_called()
        bot.binance_client.cancel_order.assert_not_called()
    asyncio.run(run())


def test_reconciliation_mismatch_and_legacy_position_halt_without_orders(tmp_path):
    bot=make_bot(tmp_path);bot.active_positions['BTCUSDT']=position()
    bot.binance_client.get_order.return_value=dict(symbol='BTCUSDT',side='SELL',type='STOP_LOSS',status='CANCELED',origQty='.01',executedQty='0')
    bot.reconcile_testnet_positions()
    assert bot.halt_state.snapshot()['halted']
    bot.binance_client.create_order.assert_not_called()


def test_market_stop_does_not_send_limit_fields():
    from cryptoscope.execution.binance_testnet import BinanceTestnetClient
    client=BinanceTestnetClient(api_key='fixture',api_secret='fixture')
    with patch.object(client,'_request',return_value={}) as request:
        client.create_order(symbol='BTCUSDT',side='SELL',order_type='STOP_LOSS',quantity=.01,stop_price=95)
    params=request.call_args.kwargs['params']
    assert 'price' not in params and 'timeInForce' not in params
