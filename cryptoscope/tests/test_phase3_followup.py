"""Phase 3 repairs: local socket deadlines and memory-growth discrimination."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch

import pytest
from cryptoscope.providers.deadline_http import post_json_deadline
from cryptoscope.tests.test_phase3_operations import make_bot,position
from cryptoscope.tests.exchange_fixtures import with_fees
from cryptoscope.execution.accounting import fill_summary,SymbolRules
from cryptoscope.execution.binance_testnet import BinanceTestnetClient,BinanceRateLimitError
from cryptoscope.execution.phase3_checks import PLAN




def test_model_transport_fails_closed_with_local_trickling_response():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200);self.send_header('Content-Length','1000');self.end_headers()
            try:
                for _ in range(80):self.wfile.write(b' ');self.wfile.flush();time.sleep(.05)
            except OSError:pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        start=time.monotonic()
        with pytest.raises((TimeoutError,OSError)):
            post_json_deadline(f'http://127.0.0.1:{server.server_port}/api/generate',{},1.5)
        assert time.monotonic()-start<1.9
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def test_model_deadline_kills_only_its_owned_stuck_worker():
    import subprocess,sys
    original=subprocess.Popen
    launched=[]
    def stuck(*args,**kwargs):
        child=original([sys.executable,'-B','-c','import time;time.sleep(10)'],**kwargs)
        launched.append(child)
        return child
    start=time.monotonic()
    with patch('cryptoscope.providers.deadline_http.subprocess.Popen',side_effect=stuck):
        with pytest.raises(TimeoutError):post_json_deadline('http://127.0.0.1:11434/api/generate',{},1.2)
    assert time.monotonic()-start<1.8
    assert len(launched)==1 and launched[0].poll() is not None


def test_consensus_rejects_opposite_direction_and_nonfinite_conviction():
    from cryptoscope.agents.consensus import DeliberationConsensusEngine
    for conviction,action in ((8,'SELL'),('NaN','BUY')):
        result=dict(done=True,done_reason='stop',response=json.dumps(dict(bull_thesis='fixture',bear_thesis='fixture',risk_verdict='APPROVE',conviction=conviction,consensus_action=action,reason='fixture')))
        with patch('cryptoscope.agents.consensus.post_json_deadline',return_value=result):
            output=DeliberationConsensusEngine().deliberate_combined('BTCUSDT','BUY',100,95,110)
        assert output['verdict']=='REJECT' and output['action']=='STAND_ASIDE'


def test_partial_close_survives_restart_without_double_counting(tmp_path):
    bot=make_bot(tmp_path);pos=position();bot.active_positions['BTCUSDT']=pos;bot._save_position_db(pos)
    bot.binance_client.get_order.return_value=dict(status='NEW',executedQty='0',orderId=11)
    partial=with_fees(dict(status='CANCELED',executedQty='.004',cummulativeQuoteQty='.44',orderId=101))
    bot.binance_client.cancel_order.side_effect=[dict(status='CANCELED',executedQty='0'),partial]
    bot.binance_client.create_order.return_value=dict(partial,status='PARTIALLY_FILLED')
    assert bot._confirmed_testnet_close('BTCUSDT',pos) is None
    assert pos['quantity']==pytest.approx(.006)
    restarted=make_bot(tmp_path);pos=restarted.active_positions['BTCUSDT']
    restarted.binance_client.create_order.return_value=with_fees(dict(status='FILLED',executedQty='.006',cummulativeQuoteQty='.66'))
    assert restarted._confirmed_testnet_close('BTCUSDT',pos)==pytest.approx(110)
    assert restarted._confirmed_testnet_close('BTCUSDT',pos)==pytest.approx(110)
    assert restarted.binance_client.create_order.call_count==1
    assert pos['closed_quantity']==.01 and pos['quantity']==pytest.approx(0)


def test_lost_entry_is_read_reconciled_without_new_order(tmp_path):
    from cryptoscope.orchestrator.events import TradeIntent
    bot=make_bot(tmp_path);intent=TradeIntent(intent_id='lost',symbol='BTCUSDT',entry_price=100,stop_loss=95,take_profit=110)
    bot.binance_client.create_order.side_effect=TimeoutError()
    with pytest.raises(TimeoutError):bot._testnet_entry(intent,.01)
    restarted=make_bot(tmp_path)
    restarted.binance_client.get_order.return_value=with_fees(dict(orderId=101,status='FILLED',executedQty='.01',cummulativeQuoteQty='1'))
    restarted.reconcile_uncertain_entries()
    restarted.reconcile_uncertain_entries()
    assert restarted.active_positions['BTCUSDT']['quantity']==.01
    assert restarted.halt_state.snapshot()['halted']
    restarted.binance_client.create_order.assert_not_called()
    restarted.binance_client.cancel_order.assert_not_called()


def test_base_and_quote_commissions_are_not_invented_as_flat_fee():
    order=dict(executedQty='.01',cummulativeQuoteQty='1',fills=[
        dict(qty='.005',price='100',commission='.00001',commissionAsset='BTC'),
        dict(qty='.005',price='100',commission='.001',commissionAsset='USDT')])
    result=fill_summary(order,'BTC','USDT')
    assert result['base_fee']==.00001 and result['quote_fee']==.001
    assert result['gross']-result['base_fee']==pytest.approx(.00999)
    assert result['valuation_complete']
    order['fills'][0]['commissionAsset']='BNB'
    assert not fill_summary(order,'BTC','USDT')['valuation_complete']


def test_untradable_residual_remains_visible_and_cannot_oversell(tmp_path):
    bot=make_bot(tmp_path);pos=position()
    bot.binance_client.get_order.return_value=with_fees(dict(status='FILLED',executedQty='.0099993',cummulativeQuoteQty='.99993'))
    assert bot._confirmed_testnet_close('BTCUSDT',pos) is None
    assert pos['quantity']==pytest.approx(.0000007)
    bot.binance_client.create_order.assert_not_called()
    assert bot.halt_state.snapshot()['halted']


def test_zero_execution_rejects_hidden_quote_or_fee_rows():
    with pytest.raises(ValueError):fill_summary(dict(executedQty='0',cummulativeQuoteQty='1',fills=[]),'BTC','USDT')
    with pytest.raises(ValueError):fill_summary(dict(executedQty='0',cummulativeQuoteQty='0',fills=[dict(qty='0')]),'BTC','USDT')


def test_quote_budget_and_wire_precision_are_preserved():
    client=BinanceTestnetClient(api_key='fixture',api_secret='fixture')
    with patch.object(client,'_request',return_value={}) as request:
        client.create_order('BTCUSDT','BUY','MARKET',0,quote_order_qty=20,client_order_id='own-ref')
        payload=request.call_args.kwargs['params']
        assert payload['quoteOrderQty']=='20' and 'quantity' not in payload
        assert payload['newOrderRespType']=='FULL'
        client.create_order('BTCUSDT','SELL','STOP_LOSS',.00012345678,stop_price=123.456789)
        payload=request.call_args.kwargs['params']
        assert payload['quantity']=='0.00012345678' and payload['stopPrice']=='123.456789'
        assert 'price' not in payload and 'timeInForce' not in payload
    assert PLAN['maximum_buy_notional_usdt']==40


def test_rate_limit_cooldown_does_not_retry_order_posts():
    import io,urllib.error
    client=BinanceTestnetClient(api_key='fixture',api_secret='fixture')
    error=urllib.error.HTTPError('https://testnet.binance.vision/api/v3/order',429,'limited',
        {'Retry-After':'2'},io.BytesIO(b'{"code":-1003}'))
    with patch.object(client._opener,'open',side_effect=error) as opened:
        with pytest.raises(BinanceRateLimitError):client._request('GET','/api/v3/ping')
        assert opened.call_count==1
        with pytest.raises(BinanceRateLimitError):client.create_order('BTCUSDT','BUY','MARKET',.01)
        assert opened.call_count==1


def test_halt_prevents_price_triggered_testnet_close(tmp_path):
    from cryptoscope.orchestrator.events import MarketUpdate
    bot=make_bot(tmp_path);pos=position();bot.active_positions['BTCUSDT']=pos
    bot.halt_state.halt('fixture','test')
    check=bot._check_position_exits(MarketUpdate(symbol='BTCUSDT',price=90))
    with pytest.raises(StopIteration):check.send(None)
    bot.binance_client.create_order.assert_not_called()
    assert 'BTCUSDT' in bot.active_positions


def test_confirmed_stop_cancellation_updates_owned_order_ledger(tmp_path):
    from contextlib import closing
    from cryptoscope.storage.sqlite import connect_database
    bot=make_bot(tmp_path);pos=position()
    pos.update(entry_reference='entry_fixture',stop_client_id='stop_fixture')
    bot._record_uncertain_order('fixture','BTCUSDT','SELL','stop_fixture',.01,'STOP_LOSS')
    bot._set_order_status('stop_fixture','NEW')
    bot.binance_client.get_order.return_value=dict(orderId=11,status='NEW',executedQty='0')
    bot.binance_client.cancel_order.return_value=dict(orderId=11,status='CANCELED',executedQty='0')
    bot.binance_client.create_order.return_value=with_fees(dict(orderId=12,status='FILLED',executedQty='.01',cummulativeQuoteQty='1'))
    assert bot._confirmed_testnet_close('BTCUSDT',pos)==pytest.approx(100)
    with closing(connect_database(bot.db_path,readonly=True)) as db:
        assert db.execute("SELECT status FROM orders WHERE order_id='stop_fixture'").fetchone()[0]=='CANCELED'
