"""Versioned, constrained strategy definitions; never execute model-written code."""
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class StrategySpec:
    name: str
    symbol: str
    strategy: str
    fast: int
    slow: int
    rationale: str

    @classmethod
    def parse(cls, data, config):
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise ValueError('Strategy definition must contain exactly name, symbol, strategy, fast, slow, rationale')
        if data['symbol'] not in config['symbols'] or data['strategy'] not in {'ema_baseline','buy_hold_baseline'}:
            raise ValueError('Strategy symbol or template is not allowed')
        if any(type(data[k]) is not int for k in ('fast','slow')) or not 1 < data['fast'] < data['slow'] <= 200:
            raise ValueError('Strategy periods require integers 1 < fast < slow <= 200')
        for key,limit in [('name',80),('rationale',400)]:
            if not isinstance(data[key],str) or not data[key].strip() or len(data[key]) > limit:
                raise ValueError('Invalid strategy '+key)
        return cls(**data)

    def to_dict(self):
        return asdict(self)


def draft(request, symbol, config, provider):
    if not isinstance(request,str) or not 1 <= len(request.strip()) <= 4000:
        raise ValueError('Strategy request must be 1..4000 characters')
    if symbol not in config['symbols']:
        raise ValueError('Symbol is outside configured universe')
    context={'request':request,'symbol':symbol,
        'supported_templates':{'ema_baseline':'Spot long when fast EMA exceeds slow EMA; exit on reversal.',
                               'buy_hold_baseline':'Spot comparison baseline after a slow-period warmup.'},
        'constraints':['Use a supported template only. No arbitrary code or shell commands.',
                       'Fees, sizing and risk settings come from operator configuration.',
                       'This is a research specification, not a profitability claim.',
                       'If the request cannot be represented by these templates, return strategy=unsupported and explain why.']}
    result=provider.complete('strategy_designer',context)
    if isinstance(result,dict) and result.get('strategy')=='unsupported':
        raise ValueError('Unsupported strategy request: '+str(result.get('rationale','Choose an EMA or buy/hold baseline.'))[:400])
    spec=StrategySpec.parse(result,config)
    if spec.symbol != symbol:
        raise ValueError('Strategy output changed the requested symbol')
    return spec
