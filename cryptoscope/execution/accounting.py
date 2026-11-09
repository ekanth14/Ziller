"""Deterministic Spot quantity, cumulative fill and commission accounting."""
from decimal import Decimal,InvalidOperation,ROUND_DOWN


def decimal(value):
    try:result=Decimal(str(value))
    except (InvalidOperation,ValueError):raise ValueError('Invalid exchange amount') from None
    if not result.is_finite() or result<0:raise ValueError('Invalid exchange amount')
    return result


def wire_amount(value):
    result=format(decimal(value),'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


class SymbolRules:
    def __init__(self,info):
        if not isinstance(info,dict) or info.get('status')!='TRADING' or info.get('isSpotTradingAllowed') is False:
            raise ValueError('Spot symbol is not active')
        self.symbol=info['symbol'];self.base=info['baseAsset'];self.quote=info['quoteAsset']
        filters={f['filterType']:f for f in info['filters']}
        lot=filters['LOT_SIZE'];market=filters.get('MARKET_LOT_SIZE',{})
        self.step=decimal(lot['stepSize']);self.minimum=decimal(lot['minQty']);self.maximum=decimal(lot['maxQty'])
        self.market_step=decimal(market.get('stepSize',0)) or self.step
        self.market_min=decimal(market.get('minQty',0)) or self.minimum
        self.market_max=decimal(market.get('maxQty',0)) or self.maximum
        self.tick=decimal(filters['PRICE_FILTER']['tickSize'])
        notional=filters.get('NOTIONAL',filters.get('MIN_NOTIONAL',{}))
        self.min_notional=decimal(notional.get('minNotional',0))
        self.max_notional=decimal(notional.get('maxNotional',0))
        if self.step<=0 or self.market_step<=0 or self.tick<=0:raise ValueError('Incomplete exchange filters')

    def quantity(self,quantity,price,market=True):
        step=self.market_step if market else self.step
        qty=(decimal(quantity)/step).to_integral_value(rounding=ROUND_DOWN)*step
        low=self.market_min if market else self.minimum;high=self.market_max if market else self.maximum
        value=qty*decimal(price)
        if qty<=0 or qty<low or qty>high or value<self.min_notional or (self.max_notional and value>self.max_notional):
            raise ValueError('Order violates exchange quantity/notional filters')
        return float(qty)

    def price(self,price):
        result=(decimal(price)/self.tick).to_integral_value(rounding=ROUND_DOWN)*self.tick
        if result<=0:raise ValueError('Invalid exchange price')
        return float(result)


def fill_summary(order,base,quote,trades=None):
    """Require complete commission evidence for every cumulative executed unit."""
    gross=decimal(order.get('executedQty',0));cash=decimal(order.get('cummulativeQuoteQty',0))
    rows=trades if trades is not None else order.get('fills')
    if gross==0:
        if cash!=0 or rows:
            raise ValueError('Zero execution conflicts with exchange fill evidence')
        return dict(gross=0.,quote=0.,base_fee=0.,quote_fee=0.,fees={},valuation_complete=True)
    if cash<=0 or not isinstance(rows,list) or not rows:raise ValueError('Executed fills require complete fee evidence')
    quantity=Decimal(0);quoted=Decimal(0);fees={}
    seen=set()
    for row in rows:
        identity=row.get('id',row.get('tradeId'))
        if identity is not None:
            if identity in seen:raise ValueError('Duplicate exchange fill identity')
            seen.add(identity)
        size=decimal(row['qty']);price=decimal(row['price']);fee=decimal(row['commission']);asset=row['commissionAsset']
        if not isinstance(asset,str) or not asset:raise ValueError('Missing commission asset')
        quantity+=size;quoted+=size*price;fees[asset]=fees.get(asset,Decimal(0))+fee
    if abs(quantity-gross)>Decimal('0.00000001') or abs(quoted-cash)>max(Decimal('0.00000001'),cash*Decimal('0.00000001')):
        raise ValueError('Incomplete or inconsistent cumulative fills')
    return dict(gross=float(gross),quote=float(cash),base_fee=float(fees.get(base,0)),
        quote_fee=float(fees.get(quote,0)),fees={a:float(v) for a,v in fees.items()},
        valuation_complete=not any(v>0 and a not in {base,quote} for a,v in fees.items()))
