import argparse
import hashlib
import json
import sys
import time
import uuid
from cryptoscope.providers.laya import LayaProvider
from cryptoscope.research.settings import ROOT, load_config
from cryptoscope.strategy import draft


def main():
    parser=argparse.ArgumentParser(description='Draft a constrained baseline strategy with the configured Laya model')
    parser.add_argument('--config')
    commands=parser.add_subparsers(dest='command',required=True)
    make=commands.add_parser('draft')
    make.add_argument('--request',required=True)
    make.add_argument('--symbol',default='BTCUSDT')
    args=parser.parse_args()
    try:
        config=load_config(args.config)
        provider=LayaProvider(config)
        spec=draft(args.request,args.symbol,config,provider)
        run_id=uuid.uuid4().hex
        result={'kind':'strategy_spec','run_id':run_id,'created_at':time.time(),'model':provider.model,
                'request':args.request,'spec':spec.to_dict(),'model_calls':provider.calls,
                'fingerprint':hashlib.sha256(json.dumps(spec.to_dict(),sort_keys=True).encode()).hexdigest(),
                'status':'draft_not_backtested'}
        output=ROOT/'reports/strategies'/run_id
        output.mkdir(parents=True)
        (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps({'status':result['status'],'spec':spec.to_dict(),'report':str(output/'report.json')},indent=2))
        return 0
    except Exception as error:
        print(f'{type(error).__name__}: {error}',file=sys.stderr)
        return 1


raise SystemExit(main())
