"""Explicit, synthetic venue filters and complete zero-fee fill responses."""
def symbol_info(symbol='BTCUSDT'):
    return dict(symbol=symbol,status='TRADING',baseAsset=symbol.removesuffix('USDT'),quoteAsset='USDT',isSpotTradingAllowed=True,
        filters=[dict(filterType='LOT_SIZE',stepSize='0.000001',minQty='0.000001',maxQty='1000'),
                 dict(filterType='PRICE_FILTER',tickSize='0.01'),dict(filterType='MIN_NOTIONAL',minNotional='0.01')])


def with_fees(order):
    qty=float(order.get('executedQty',0));cash=float(order.get('cummulativeQuoteQty',0))
    return dict(order,orderId=order.get('orderId',101),fills=[dict(qty=str(qty),price=str(cash/qty),commission='0',commissionAsset='USDT')] if qty and cash else [])
