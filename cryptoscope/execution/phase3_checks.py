"""Bounded manual TESTNET diagnostics; never a strategy or unattended trading loop."""
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import time
import uuid

from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.execution.accounting import SymbolRules,wire_amount
from cryptoscope.storage.sqlite import connect_database

PLAN=dict(symbol='BTCUSDT',maximum_buy_notional_usdt=40,per_buy_notional_usdt=20,
    venue='https://testnet.binance.vision',steps=['Own post-only limit buy, query and cancel',
    'Quote-capped market buy, account actual fills and place exchange stop',
    'Force-stop this diagnostic process only after protection is confirmed',
    'Restart from disposable state, verify protection, request HALT_FLATTEN',
    'Validate three rejected orders through nonexecuting order/test'],
    excludes=['LIVE','Other account orders','Deliberate rate-limit flooding','Seven-day run'],
    acceptance='Real partial fills and HTTP 429 are NOT OBSERVED unless they occur; no blanket integration PASS or seven-day start without them')


def build_bot(root):
    return ExecutionBot(EventBus(),mode='TESTNET',db_path=str(root/'execution.db'),
        exchange_api_key=os.environ['BINANCE_TESTNET_API_KEY'],exchange_api_secret=os.environ['BINANCE_TESTNET_API_SECRET'])


def save(root,body):
    (root/'integration-result.json').write_text(json.dumps(body,indent=2,allow_nan=False),encoding='utf-8')


def phase1(root):
    bot=build_bot(root);client=bot.binance_client
    if client.get_open_orders('BTCUSDT'):raise ValueError('Existing BTC orders require operator review before diagnostics')
    rules=SymbolRules(client.get_symbol_info('BTCUSDT'));price=client.get_ticker_price('BTCUSDT')
    scope=uuid.uuid4().hex[:16];limit_ref='entry_p3limit_'+scope
    limit_price=rules.price(price*.99);quantity=rules.quantity(20/limit_price,limit_price,market=False)
    bot.halt_state.resume_local_admin(admin_reauthenticated=True,actor='approved-isolated-diagnostic')
    bot._record_uncertain_order(scope,'BTCUSDT','BUY',limit_ref,quantity,order_type='LIMIT_MAKER')
    bot._write_observation(limit_ref,'BTCUSDT',dict(bracket=dict(stop=rules.price(price*.97),target=rules.price(price*1.05))))
    submitted=client.create_order('BTCUSDT','BUY','LIMIT_MAKER',quantity,price=limit_price,client_order_id=limit_ref)
    queried=client.get_order('BTCUSDT',order_id=submitted['orderId'])
    settled=bot._settle_working_order('BTCUSDT',queried)
    if settled.get('status') not in {'CANCELED','FILLED','EXPIRED'}:raise ValueError('Own limit order did not settle')
    partial_observed=queried.get('status')=='PARTIALLY_FILLED' or settled.get('status')=='CANCELED' and float(settled.get('executedQty',0))>0
    if float(settled.get('executedQty',0))>0:
        pos=bot._adopt_entry(limit_ref,scope,'BTCUSDT',settled,rules,rules.price(price*.97),rules.price(price*1.05))
        if bot.halt_state.snapshot()['halted'] or not str(pos.get('stop_order_id','')).isdigit():
            raise ValueError('Limit fill protection or valuation requires operator review')
        if asyncio.run(bot.flatten_all_positions('Approved diagnostic limit cleanup'))!=1:raise ValueError('Limit fill leaves retained exposure; operator review required')
        if bot.halt_state.snapshot()['halted']:raise ValueError('Limit cleanup requires operator review')
    else:bot._set_order_status(limit_ref,settled['status'])
    reference='entry_p3market_'+scope
    bot._record_uncertain_order(scope,'BTCUSDT','BUY',reference,rules.quantity(20/price,price))
    bot._write_observation(reference,'BTCUSDT',dict(bracket=dict(stop=rules.price(price*.98),target=rules.price(price*1.04))))
    order=client.create_order('BTCUSDT','BUY','MARKET',quantity=0,quote_order_qty=20,client_order_id=reference)
    order=bot._settle_working_order('BTCUSDT',order)
    pos=bot._adopt_entry(reference,scope,'BTCUSDT',order,rules,rules.price(price*.98),rules.price(price*1.04))
    if bot.halt_state.snapshot()['halted']:raise ValueError('Market fill retained under halt for operator review')
    stop=client.get_order('BTCUSDT',order_id=int(pos['stop_order_id']))
    if stop.get('status')!='NEW' or stop.get('type')!='STOP_LOSS':raise ValueError('Exchange protection is not resting')
    if abs(float(stop['origQty'])-pos['quantity'])>1e-10:raise ValueError('Protection does not cover all owned units')
    result=dict(status='restart_required',scope=scope,limit_order_id=submitted['orderId'],market_order_id=order['orderId'],stop_order_id=stop['orderId'],partial_fill='OBSERVED' if partial_observed else 'NOT_OBSERVED',rate_limit='NOT_OBSERVED',plan=PLAN)
    save(root,result);(root/'restart-required').write_text('Protection confirmed; safe to terminate this diagnostic process only',encoding='utf-8')
    while True:time.sleep(1)


def phase2(root):
    result=json.loads((root/'integration-result.json').read_text(encoding='utf-8'));bot=build_bot(root)
    bot.reconcile_testnet_positions()
    if bot.halt_state.snapshot()['halted']:
        pos=bot.active_positions.get('BTCUSDT')
        if not pos or not str(pos.get('stop_order_id','')).isdigit():
            raise ValueError('Restart reconciliation requires operator review')
        own_stop=bot.binance_client.get_order('BTCUSDT',order_id=int(pos['stop_order_id']))
        if (own_stop.get('symbol')!='BTCUSDT' or own_stop.get('side')!='SELL'
            or own_stop.get('type')!='STOP_LOSS' or
            own_stop.get('status') not in {'NEW','FILLED','PARTIALLY_FILLED'} or
            abs(float(own_stop.get('origQty',0))-pos.get('protected_quantity',pos['quantity']))>1e-9):
            raise ValueError('Restart protection differs from owned order')
        if own_stop['status']=='NEW' and float(own_stop.get('executedQty',0))==0:
            result['restart_reconciliation']='PASS'
        else:result['restart_reconciliation']='STOP_TRIGGERED_REVIEW'
    else:result['restart_reconciliation']='PASS'
    bot.halt_state.halt('Approved isolated HALT_FLATTEN check','diagnostic','HALT_FLATTEN')
    if asyncio.run(bot.apply_emergency_action())!=1:raise ValueError('Flatten retained unresolved exposure')
    result['halt_flatten']='PASS';result['entry_disabled_after_flatten']=bot.halt_state.snapshot()['halted']
    result['operator_reconciliation_required']=False
    client=bot.binance_client;rules=SymbolRules(client.get_symbol_info('BTCUSDT'));price=rules.price(client.get_ticker_price('BTCUSDT'))
    valid=rules.quantity(20/price,price,market=False)
    invalid=[dict(case='lot_size',quantity=valid+float(rules.step)/2,price=price),
        dict(case='tick_size',quantity=valid,price=price+float(rules.tick)/2),
        dict(case='min_notional',quantity=float(rules.minimum),price=price)]
    checks=[]
    for item in invalid:
        try:
            client._request('POST','/api/v3/order/test',params=dict(symbol='BTCUSDT',side='BUY',type='LIMIT',timeInForce='GTC',quantity=wire_amount(item['quantity']),price=wire_amount(item['price'])),signed=True)
            checks.append(dict(case=item['case'],result='NOT_REJECTED'))
        except Exception as error:
            checks.append(dict(case=item['case'],result='REJECTED' if getattr(error,'code',None)==-1013 else 'FAIL',code=getattr(error,'code',None)))
    result['filter_checks']=checks
    with closing(connect_database(bot.db_path,readonly=True)) as db:
        result['own_order_references']=[r[0] for r in db.execute('SELECT order_id FROM orders')]
    result['bounded_lifecycle']='PASS' if result['restart_reconciliation']=='PASS' and all(c['result']=='REJECTED' for c in checks) else 'REVIEW'
    result['full_phase3_integration']='NOT_COMPLETE' if result['partial_fill']=='NOT_OBSERVED' or result['rate_limit']=='NOT_OBSERVED' else result['bounded_lifecycle']
    result['status']='completed';save(root,result)


def recheck_min_notional(root):
    result=json.loads((root/'integration-result.json').read_text(encoding='utf-8'))
    if result.get('status')!='completed' or result.get('halt_flatten')!='PASS':
        raise ValueError('Filter recheck requires completed owned flatten')
    bot=build_bot(root)
    if bot.active_positions:raise ValueError('Filter recheck cannot run with local exposure')
    client=bot.binance_client;rules=SymbolRules(client.get_symbol_info('BTCUSDT'))
    price=rules.price(client.get_ticker_price('BTCUSDT'))
    if float(rules.minimum)*price>=float(rules.min_notional):
        result['min_notional_recheck']='NOT_TESTABLE_WITH_CURRENT_FILTERS';save(root,result);return
    try:
        client._request('POST','/api/v3/order/test',params=dict(symbol='BTCUSDT',side='BUY',type='LIMIT',
            timeInForce='GTC',quantity=wire_amount(rules.minimum),price=wire_amount(price)),signed=True)
        check=dict(case='min_notional',result='NOT_REJECTED')
    except Exception as error:
        check=dict(case='min_notional',result='REJECTED' if getattr(error,'code',None)==-1013 else 'FAIL',
            code=getattr(error,'code',None))
    result['filter_checks']=[check if item['case']=='min_notional' else item for item in result['filter_checks']]
    result['min_notional_recheck']=check['result']
    result['bounded_lifecycle']='PASS' if result['restart_reconciliation']=='PASS' and all(item['result']=='REJECTED' for item in result['filter_checks']) else 'REVIEW'
    result['full_phase3_integration']='NOT_COMPLETE'
    save(root,result)


def reconcile_completed_ledger(root):
    result=json.loads((root/'integration-result.json').read_text(encoding='utf-8'))
    if result.get('status')!='completed' or result.get('halt_flatten')!='PASS':
        raise ValueError('Completed flatten evidence required')
    bot=build_bot(root)
    if bot.active_positions:raise ValueError('Known position remains open')
    reference='stop_p3market_'+result['scope']
    order=bot.binance_client.get_order('BTCUSDT',client_order_id=reference)
    if (str(order.get('orderId'))!=str(result['stop_order_id']) or order.get('status')!='CANCELED'
        or float(order.get('executedQty',0))!=0):
        raise ValueError('Owned stop has not been confirmed canceled')
    if bot.binance_client.get_open_orders('BTCUSDT'):
        raise ValueError('BTC open orders require operator review')
    bot._set_order_status(reference,'CANCELED')
    result['ledger_reconciled']=True;result.pop('error_type',None)
    save(root,result)


def inspect(root):
    bot=build_bot(root);result=json.loads((root/'integration-result.json').read_text(encoding='utf-8'))
    pos=bot.active_positions.get('BTCUSDT')
    if pos is None:
        details=dict(position_present=False,halted=bot.halt_state.snapshot()['halted'])
    else:
        stop_id=pos.get('stop_order_id');stop=None
        if str(stop_id).isdigit():stop=bot.binance_client.get_order('BTCUSDT',order_id=int(stop_id))
        details=dict(position_present=True,position_quantity=pos['quantity'],stop_id=stop_id,
            stop_status=stop.get('status') if stop else None,stop_type=stop.get('type') if stop else None,
            stop_side=stop.get('side') if stop else None,stop_symbol=stop.get('symbol') if stop else None,
            stop_executed_quantity=stop.get('executedQty') if stop else None,
            stop_original_quantity=stop.get('origQty') if stop else None,
            halted=bot.halt_state.snapshot()['halted'],halt_action=bot.halt_state.snapshot()['action'])
    with closing(connect_database(bot.db_path,readonly=True)) as db:
        details['own_order_rows']=[dict(reference=r[0],status=r[1]) for r in db.execute('SELECT order_id,status FROM orders')]
    details['exchange_owned_orders']=[]
    for item in details['own_order_rows']:
        order=bot.binance_client.get_order('BTCUSDT',client_order_id=item['reference'])
        details['exchange_owned_orders'].append(dict(reference=item['reference'],order_id=order.get('orderId'),
            status=order.get('status'),side=order.get('side'),executed_quantity=order.get('executedQty')))
    open_orders=bot.binance_client.get_open_orders('BTCUSDT')
    own_refs={item['reference'] for item in details['own_order_rows']}
    details['own_open_order_count']=sum(order.get('clientOrderId') in own_refs for order in open_orders)
    details['other_open_order_count']=len(open_orders)-details['own_open_order_count']
    (root/'inspection.json').write_text(json.dumps(details,indent=2),encoding='utf-8')


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['entry','restart','inspect','filters','ledger'],required=True);args=parser.parse_args()
    if os.environ.get('ZILLERS_APPROVED_TESTNET_CHECKS')!='bounded-phase3-v1':raise SystemExit('Explicit diagnostic authorization required')
    root=Path(os.environ['ZILLERS_AUDIT_SANDBOX'])/'tmp/exchange-check';root.mkdir(parents=True,exist_ok=True)
    os.environ['GOVERNOR_STATE_DB']=str(root/'governor.db')
    try:
        if args.stage=='entry':phase1(root)
        elif args.stage=='restart':phase2(root)
        elif args.stage=='filters':recheck_min_notional(root)
        elif args.stage=='ledger':reconcile_completed_ledger(root)
        else:inspect(root)
    except Exception as error:
        previous=json.loads((root/'integration-result.json').read_text(encoding='utf-8')) if (root/'integration-result.json').exists() else {}
        save(root,dict(previous,status='failed',error_type=type(error).__name__,operator_reconciliation_required=True));raise SystemExit(1) from None


if __name__=='__main__':main()
