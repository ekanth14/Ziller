"""Native Ollama JSON schemas restrict each role to its actual handoff fields."""
import math


class SchemaValidationError(ValueError):
    pass


def validate_schema(value, schema, path='response'):
    """Validate the small JSON Schema subset emitted by role_schema locally.

    Ollama's grammar is a generation aid; local validation remains mandatory.
    Unknown schema constructs are not accepted by this validator.
    """
    if schema=='json':
        if not isinstance(value,dict):
            raise SchemaValidationError(f'{path} must be an object')
        return
    allowed={'type','anyOf','properties','required','additionalProperties','items','minItems','maxItems',
             'minLength','maxLength','enum','minimum','maximum','exclusiveMinimum'}
    if not isinstance(schema,dict) or set(schema)-allowed:
        raise ValueError('Unsupported local response schema')
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            try:
                validate_schema(value,option,path)
                return
            except SchemaValidationError:
                continue
        raise SchemaValidationError(f'{path} matches no permitted type')
    kind=schema.get('type')
    matches={'object':isinstance(value,dict),'array':isinstance(value,list),
        'string':isinstance(value,str),'boolean':type(value) is bool,'null':value is None,
        'number':type(value) in (int,float),'integer':type(value) is int}
    if kind not in matches or not matches[kind]:
        raise SchemaValidationError(f'{path} must be {kind}')
    if 'enum' in schema and value not in schema['enum']:
        raise SchemaValidationError(f'{path} is not an allowed value')
    if kind=='object':
        properties=schema.get('properties',{})
        if set(schema.get('required',[]))-set(value):
            raise SchemaValidationError(f'{path} is missing required fields')
        if schema.get('additionalProperties') is False and set(value)-set(properties):
            raise SchemaValidationError(f'{path} has unexpected fields')
        for key,item in value.items():
            if key in properties:
                validate_schema(item,properties[key],f'{path}.{key}')
    elif kind=='array':
        if len(value)<schema.get('minItems',0) or len(value)>schema.get('maxItems',float('inf')):
            raise SchemaValidationError(f'{path} has invalid item count')
        for index,item in enumerate(value):
            validate_schema(item,schema['items'],f'{path}[{index}]')
    elif kind=='string':
        if len(value)<schema.get('minLength',0) or len(value)>schema.get('maxLength',float('inf')):
            raise SchemaValidationError(f'{path} has invalid text length')
    elif kind in {'number','integer'}:
        if not math.isfinite(value) or value<schema.get('minimum',-float('inf')) or value>schema.get('maximum',float('inf')):
            raise SchemaValidationError(f'{path} is outside the permitted numeric range')
        if 'exclusiveMinimum' in schema and value<=schema['exclusiveMinimum']:
            raise SchemaValidationError(f'{path} is below the exclusive minimum')


def text(limit=240):
    return {"type": "string", "minLength": 1, "maxLength": limit}


def items(schema, minimum=0, maximum=3):
    return {"type": "array", "items": schema, "minItems": minimum, "maxItems": maximum}


def record(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def role_schema(role, context):
    if role == 'fast_decider':
        return record({'action':{'type':'string','enum':context['allowed_actions']},
                       'strategy':{'type':'string','enum':context['allowed_strategies']}})
    if role == 'strategy_designer':
        return record({'name':text(80), 'symbol':{'type':'string','enum':[context['symbol']]},
            'strategy':{'type':'string','enum':['ema_baseline','buy_hold_baseline','unsupported']},
            'fast':{'type':'integer','minimum':2,'maximum':199},
            'slow':{'type':'integer','minimum':3,'maximum':200}, 'rationale':text(400)})
    analysts = context.get("analysts", [])
    ids = [a["id"] for a in analysts if a.get("status") == "available"] or ["technical"]
    evidence = items({"type": "string", "enum": ids}, minimum=1)
    if role in {"bull_researcher", "bear_researcher"}:
        return record({"thesis": text(), "evidence": evidence,
                       "counterarguments": items(text(160))})
    if role in {"aggressive_risk", "neutral_risk", "conservative_risk"}:
        return record({"assessment": text(), "concerns": items(text(160))})
    if role == "portfolio_manager":
        return record({"approved": {"type": "boolean"}, "reason": text()})
    if role == "trader":
        symbol = context["instrument"]["symbol"]
        level = {"anyOf": [{"type": "number", "exclusiveMinimum": 0}, {"type": "null"}]}
        return record({
            "action": {"type": "string", "enum": ["LONG", "SHORT", "REDUCE", "CLOSE", "HOLD", "NO_TRADE"]},
            "symbol": {"type": "string", "enum": [symbol]},
            "entry": level, "stop": level, "target": level,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "thesis": text(), "evidence": evidence,
            "expires_at": {"type": "number", "minimum": context["instrument"]["as_of"],
                           "maximum": context["instrument"]["as_of"] + 86400},
            "reduce_fraction": {"type": "number", "minimum": 0.000001, "maximum": 1},
        })
    return "json"
