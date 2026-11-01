import argparse
import json
import sys
from cryptoscope.autotrader.engine import AutoTrader
from cryptoscope.autotrader.risk import AutoBroker
from cryptoscope.autotrader.settings import load_settings
from cryptoscope.autotrader.store import BotStore,ProcessLock
from cryptoscope.providers.binance import BinanceProvider
from cryptoscope.research.settings import ROOT


def main():
    parser=argparse.ArgumentParser(description='Autonomous Laya spot paper trading; no exchange order API')
    parser.add_argument('--config',help='Autotrader JSON overrides')
    commands=parser.add_subparsers(dest='command',required=True)
    start=commands.add_parser('start',help='Run continuously in this terminal')
    start.add_argument('--max-seconds',type=int)
    once=commands.add_parser('once',help='Complete one paper decision then stop')
    once.add_argument('--force-review',action='store_true',help='Ask Laya to review even a HOLD-only context')
    once.add_argument('--max-seconds',type=int,default=120,help='Stop if no decision completes within this run budget')
    commands.add_parser('status')
    commands.add_parser('stop',help='Stop new decisions; existing paper positions remain recorded')
    commands.add_parser('pause-entries',help='Persistently pause new entries; protective exits continue')
    commands.add_parser('resume-entries',help='Release manual pause; risk halts remain in force')
    commands.add_parser('reset-risk',help='Explicitly reset loss/drawdown baselines using fresh marks')
    args=parser.parse_args()
    try:
        settings,risk,inference=load_settings(args.config)
        directory=ROOT/'work/autotrader'
        store=BotStore(directory)
        if args.command=='status':
            print(json.dumps(store.snapshot(),indent=2))
        elif args.command=='stop':
            store.request_stop()
            print(json.dumps({'status':'stop_requested','note':'Protective monitoring stops when the process exits; paper positions remain recorded.'}))
        elif args.command in {'pause-entries','resume-entries','reset-risk'}:
            broker=AutoBroker(directory/'paper.sqlite3',risk,settings)
            if args.command=='reset-risk':
                with ProcessLock(directory/'engine.lock'):
                    feed=BinanceProvider()
                    broker.observe([feed.quote(s) for s in broker.portfolio()['positions']])
                    result=broker.reset_risk()
            else:
                result=broker.set_halt(args.command=='pause-entries')
            print(json.dumps(result,indent=2))
        else:
            if getattr(args,'max_seconds',None) is not None and args.max_seconds<1:
                parser.error('--max-seconds must be positive')
            bot=AutoTrader(settings,risk,inference)
            bot.run(max_decisions=1 if args.command=='once' else None,
                    force_review=getattr(args,'force_review',False),max_seconds=getattr(args,'max_seconds',None))
            print(json.dumps(bot.store.snapshot()['runtime'],indent=2))
            if args.command=='once' and (not bot.last_decision or bot.last_decision['status']=='failed'):
                return 1
        return 0
    except Exception as error:
        print(f'{type(error).__name__}: {error}',file=sys.stderr)
        return 1


raise SystemExit(main())
