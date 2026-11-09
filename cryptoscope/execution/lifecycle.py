"""Cumulative, restart-safe Spot lifecycle. All exchange access is supplied by ExecutionBot."""
from contextlib import closing
import hashlib
import json
import math
import time
import uuid

from cryptoscope.storage.sqlite import connect_database
from cryptoscope.execution.accounting import SymbolRules,fill_summary

TERMINAL={'FILLED','CANCELED','EXPIRED','EXPIRED_IN_MATCH','REJECTED'}


class TestnetLifecycle:
    def _rules(self,symbol):
        return SymbolRules(self.binance_client.get_symbol_info(symbol))

    def _observation(self,reference,order,rules):
        if not isinstance(order,dict):raise ValueError('Invalid exchange observation')
        # Retain the received cumulative amounts even if fee evidence is not
        # yet available. No account response or credentials enter this ledger.
        body={k:order.get(k) for k in ('orderId','status','executedQty','cummulativeQuoteQty')}
        previous=self._read_observation(reference) or {}
        if float(body.get('executedQty') or 0)<float(previous.get('executedQty') or 0):raise ValueError('Cumulative fill moved backwards')
        body['summary']=None
        self._write_observation(reference,rules.symbol,body)
        trades=None
        if float(order.get('executedQty',0)) and not order.get('fills'):
            trades=self.binance_client.get_my_trades(rules.symbol,order.get('orderId'))
        summary=fill_summary(order,rules.base,rules.quote,trades)
        body['summary']=summary;self._write_observation(reference,rules.symbol,body)
        return summary

    def _write_observation(self,reference,symbol,body):
        with closing(connect_database(self.db_path)) as db:
            previous=db.execute('SELECT payload FROM exchange_observations WHERE reference=?',(str(reference),)).fetchone()
            if previous:body={**json.loads(previous[0]),**body}
            db.execute('INSERT INTO exchange_observations VALUES (?,?,?,?) ON CONFLICT(reference) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                (str(reference),symbol,json.dumps(body,allow_nan=False),time.time()));db.commit()

    def _read_observation(self,reference):
        with closing(connect_database(self.db_path,readonly=True)) as db:
            row=db.execute('SELECT payload FROM exchange_observations WHERE reference=?',(str(reference),)).fetchone()
        return json.loads(row[0]) if row else None

    def _set_order_status(self,reference,status):
        with closing(connect_database(self.db_path)) as db:
            db.execute('UPDATE orders SET status=? WHERE order_id=?',(status,reference));db.commit()

    def _settle_working_order(self,symbol,order):
        if order.get('status') not in TERMINAL:
            # Only the exact order created by this bot is canceled. A partial
            # cancellation response is then accounted at its cumulative fill.
            try:return self.binance_client.cancel_order(symbol,order_id=order['orderId'])
            except Exception:
                self.halt_state.halt('Own order cancellation unresolved',self.name)
        return order

    def _testnet_entry(self,intent,approved_quantity):
        symbol=intent.symbol;rules=self._rules(symbol)
        if intent.direction!='BUY' or symbol in self.active_positions:raise ValueError('Spot entry conflicts with known exposure')
        if (not all(math.isfinite(float(value)) for value in
                    (approved_quantity,intent.entry_price,intent.stop_loss,intent.take_profit))
            or not (0<intent.stop_loss<intent.entry_price<intent.take_profit)):
            raise ValueError('Invalid approved Spot entry bracket')
        qty=rules.quantity(approved_quantity,intent.entry_price)
        reference_hash=hashlib.sha256(intent.intent_id.encode()).hexdigest()[:24]
        reference='entry_'+reference_hash
        if not self._record_uncertain_order(intent.intent_id,symbol,'BUY',reference,qty):raise ValueError('Entry reference already exists')
        # Bracket survives a lost network response and process restart.
        self._write_observation(reference,symbol,dict(bracket=dict(stop=intent.stop_loss,target=intent.take_profit),requested_quantity=qty))
        order=self.binance_client.create_order(symbol=symbol,side='BUY',order_type='MARKET',quantity=qty,client_order_id=reference)
        order=self._settle_working_order(symbol,order)
        return self._adopt_entry(reference,intent.intent_id,symbol,order,rules,intent.stop_loss,intent.take_profit)

    def _adopt_entry(self,reference,intent_id,symbol,order,rules,stop,target):
        if (not str(order.get('orderId','')).isdigit() or order.get('symbol',symbol)!=symbol
            or order.get('side','BUY')!='BUY'):
            raise ValueError('Entry exchange identity conflicts with owned order')
        summary=self._observation(reference,order,rules)
        net=summary['gross']-summary['base_fee']
        if net<=0:raise ValueError('No confirmed net inventory')
        cost=summary['quote']+summary['quote_fee']
        pos=dict(symbol=symbol,side='BUY',quantity=net,entry_price=cost/net,stop_price=stop,target_price=target,
            stop_order_id=None,created_at=time.time(),mode='TESTNET',entry_reference=reference,
            entry_quantity=net,entry_cost_usd=cost,exit_references=[],base_asset=rules.base,quote_asset=rules.quote,
            commission_by_asset=summary['fees'],entry_commissions=summary['fees'],fee_valuation_complete=summary['valuation_complete'])
        self.active_positions[symbol]=pos;self._save_position_db(pos)
        terminal=order.get('status') in TERMINAL
        self._set_order_status(reference,order.get('status') if terminal else 'RECONCILE_REQUIRED')
        if order.get('status')!='FILLED' or not summary['valuation_complete']:
            self.halt_state.halt('Partial entry or unvalued commission retained',self.name)
        stop_reference='stop_'+reference.removeprefix('entry_')
        pos['stop_client_id']=stop_reference
        self._save_position_db(pos)
        try:
            protected=rules.quantity(net,stop)
            pos['protected_quantity']=protected
            self._record_uncertain_order(intent_id,symbol,'SELL',stop_reference,protected,order_type='STOP_LOSS')
            try:
                protection=self.binance_client.create_order(symbol=symbol,side='SELL',order_type='STOP_LOSS',quantity=protected,stop_price=rules.price(stop),client_order_id=stop_reference)
            except Exception:
                protection=self.binance_client.get_order(symbol=symbol,client_order_id=stop_reference)
            if not str(protection.get('orderId','')).isdigit():raise ValueError('Protection identity unavailable')
            pos['stop_order_id']=str(protection['orderId'])
            if (protection.get('status')!='NEW' or protection.get('symbol',symbol)!=symbol
                or protection.get('side','SELL')!='SELL' or protection.get('type','STOP_LOSS')!='STOP_LOSS'
                or ('origQty' in protection and abs(float(protection['origQty'])-protected)>1e-10)):
                raise ValueError('Protection not confirmed resting')
            self._set_order_status(stop_reference,'NEW')
            if abs(protected-net)>1e-10:self.halt_state.halt('Untradable base residual retained',self.name)
        except Exception:self.halt_state.halt('Exchange protection unavailable; exposure retained',self.name)
        self._save_position_db(pos)
        return pos

    def reconcile_uncertain_entries(self,cancel_working=False):
        """Read/reconcile owned entry IDs; never create a replacement entry."""
        with closing(connect_database(self.db_path,readonly=True)) as db:
            pending=db.execute("SELECT order_id,intent_id,symbol FROM orders WHERE status='RECONCILE_REQUIRED' AND order_id LIKE 'entry_%'").fetchall()
        for reference,intent_id,symbol in pending:
            try:
                prior=self._read_observation(reference) or {}
                order=self.binance_client.get_order(symbol=symbol,client_order_id=reference)
                if cancel_working and order.get('status') not in TERMINAL:
                    order=self._settle_working_order(symbol,order)
                if float(order.get('executedQty',0))==0 and order.get('status') in TERMINAL:
                    self._set_order_status(reference,order['status']);continue
                bracket=prior.get('bracket')
                if not bracket:raise ValueError('Entry bracket unavailable')
                # Reconstructing inventory is read-only with respect to the
                # exchange. Protection placement needs an explicit repair call.
                summary=self._observation(reference,order,self._rules(symbol))
                net=summary['gross']-summary['base_fee'];cost=summary['quote']+summary['quote_fee']
                if net<=0:raise ValueError('No net inventory')
                if symbol in self.active_positions:
                    pos=self.active_positions[symbol]
                    if pos.get('entry_reference')!=reference:raise ValueError('Conflicting recovered entry')
                    consumed=0.
                    for ref in pos.get('exit_references',[]):
                        prior_exit=(self._read_observation(ref) or {}).get('summary')
                        if prior_exit is None:raise ValueError('Recovered close evidence incomplete')
                        consumed+=prior_exit['gross']+prior_exit['base_fee']
                    if consumed>net+1e-9:raise ValueError('Recovered inventory conflict')
                    pos.update(quantity=max(0.,net-consumed),entry_price=cost/net,entry_cost_usd=cost,entry_quantity=net,
                        entry_commissions=summary['fees'],commission_by_asset=summary['fees'],fee_valuation_complete=summary['valuation_complete'])
                    self._save_position_db(pos)
                    if order.get('status') in TERMINAL:self._set_order_status(reference,order['status'])
                    self.halt_state.halt('Recovered cumulative entry requires protection review',self.name)
                    continue
                pos=dict(symbol=symbol,side='BUY',quantity=net,entry_price=cost/net,entry_cost_usd=cost,entry_quantity=net,
                    entry_reference=reference,exit_references=[],stop_price=bracket['stop'],target_price=bracket['target'],
                    stop_order_id=None,created_at=time.time(),mode='TESTNET',commission_by_asset=summary['fees'],fee_valuation_complete=summary['valuation_complete'])
                self.active_positions[symbol]=pos;self._save_position_db(pos)
                if order.get('status') in TERMINAL:self._set_order_status(reference,order['status'])
                self.halt_state.halt('Recovered exchange inventory requires protection repair',self.name)
            except Exception:self.halt_state.halt('Owned entry reconciliation incomplete',self.name)

    def _confirmed_testnet_close(self,symbol,pos):
        try:
            if pos.get('mode')!='TESTNET':raise ValueError('Unverified position provenance')
            rules=self._rules(symbol)
            initial=pos.setdefault('entry_quantity',pos['quantity'])
            pos.setdefault('entry_cost_usd',initial*pos['entry_price'])
            references=pos.setdefault('exit_references',[])
            stop_id=pos.get('stop_order_id')
            if stop_id and str(stop_id).isdigit() and str(stop_id) not in references:
                order=self.binance_client.get_order(symbol=symbol,order_id=int(stop_id))
                order=self._settle_working_order(symbol,order)
                self._observation(str(stop_id),order,rules)
                if order.get('status') not in TERMINAL:raise ValueError('Protective cancellation unresolved')
                own_stop_ref=pos.get('stop_client_id') or (
                    'stop_'+pos['entry_reference'].removeprefix('entry_') if pos.get('entry_reference') else None)
                if own_stop_ref:self._set_order_status(own_stop_ref,order['status'])
                references.append(str(stop_id));pos['stop_order_id']=None
            previous=pos.get('exit_client_id')
            if previous and previous not in references:references.append(previous)
            # Refresh incomplete owned closes; a lost response never means retry.
            for ref in references:
                observed=self._read_observation(ref)
                if not observed or observed.get('status') not in TERMINAL:
                    order=self.binance_client.get_order(symbol=symbol,client_order_id=ref)
                    order=self._settle_working_order(symbol,order)
                    self._observation(ref,order,rules)
            def totals():
                consumed=proceeds=0.;complete=True;pending=False
                fees=dict(pos.get('entry_commissions',{}))
                for ref in references:
                    observed=self._read_observation(ref);s=observed.get('summary') if observed else None
                    if not s:raise ValueError('Close fee evidence incomplete')
                    consumed+=s['gross']+s['base_fee'];proceeds+=s['quote']-s['quote_fee']
                    complete=complete and s['valuation_complete'];pending=pending or observed['status'] not in TERMINAL
                    for asset,amount in s['fees'].items():fees[asset]=fees.get(asset,0.)+amount
                pos['commission_by_asset']=fees
                return consumed,proceeds,complete,pending
            consumed,proceeds,valued,pending=totals()
            remaining=initial-consumed
            if remaining < -1e-9:raise ValueError('Exchange close exceeds owned inventory')
            pos['quantity']=max(0.,remaining);self._save_position_db(pos)
            if remaining>1e-10 and not pending:
                qty=rules.quantity(remaining,pos['entry_price'])
                reference='close_'+uuid.uuid4().hex[:24]
                pos['exit_client_id']=reference;references.append(reference)
                self._record_uncertain_order(reference,symbol,'SELL',reference,qty)
                self._save_position_db(pos)
                order=self.binance_client.create_order(symbol=symbol,side='SELL',order_type='MARKET',quantity=qty,client_order_id=reference)
                order=self._settle_working_order(symbol,order)
                self._observation(reference,order,rules)
                self._set_order_status(reference,order['status'] if order.get('status') in TERMINAL else 'RECONCILE_REQUIRED')
                consumed,proceeds,valued,pending=totals();remaining=initial-consumed
                if remaining < -1e-9:raise ValueError('Exchange close exceeds owned inventory')
                pos['quantity']=max(0.,remaining);self._save_position_db(pos)
            if pending or remaining>1e-10:
                raise ValueError('Residual exposure retained for reconciliation')
            pos['closed_quantity']=initial
            pos['fee_valuation_complete']=bool(valued and pos.get('fee_valuation_complete',True))
            pos['closed']=True
            self._save_position_db(pos)
            if not valued or not pos.get('fee_valuation_complete',True):
                self.halt_state.halt('Unvalued commission retained in audit ledger',self.name)
                return None
            return proceeds/initial
        except Exception:
            self._save_position_db(pos)
            self.halt_state.halt('Exchange close unresolved; exposure retained',self.name)
            return None
