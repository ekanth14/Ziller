"""Offline installation verification: python -m cryptoscope.backtesting."""
import json
import math
from importlib.metadata import distribution, version
from pathlib import Path


def verify():
    import pandas as pd
    from backtester.execution import (
        ContractSpec, ExecutionSimulator, FillEngine, FixedBpsCommission,
        FixedBpsSlippage, Order, OrderSide, OrderType,
    )
    from backtester.portfolio.accounting.ledger import PortfolioLedger
    from backtester.risk.pre_trade import PreTradeRisk

    symbol = "BTCUSDT"
    dates = pd.date_range("2026-01-01", periods=5, freq="15min", tz="UTC")
    def frame(values):
        return pd.DataFrame({symbol: values}, index=dates, dtype=float)

    spec = ContractSpec.crypto(symbol, quote_currency="USDT", base_currency="BTC",
                               quantity_step=0.00001, tick_size=0.01, min_quantity=0.00001)
    ledger = PortfolioLedger(initial_cash=10000, instruments=[symbol],
                             contract_spec_resolver=lambda _: spec, settlement_currency="USDT")
    engine = FillEngine(fill_at="open", slippage=FixedBpsSlippage(bps=5),
                        commission=FixedBpsCommission(bps=10), notional_fn=ledger.trade_notional)
    simulator = ExecutionSimulator(fill_engine=engine, ledger=ledger,
        pre_trade_risk=PreTradeRisk(allow_short=False, max_gross_leverage=1,
                                   max_margin_utilization=1, reserve_pending_orders=True))
    fills, submissions = [], []

    def on_bar(date, bars, positions, nav, average_entry):
        if date == dates[0]:
            order = Order(instrument=symbol, side=OrderSide.BUY, quantity=0.01,
                          order_type=OrderType.MARKET, created_at=date, order_id="verification-buy")
        elif date == dates[2]:
            order = Order(instrument=symbol, side=OrderSide.SELL, quantity=positions[symbol],
                          order_type=OrderType.MARKET, created_at=date, order_id="verification-sell")
        else:
            return
        batch = simulator.submit_batch([order])
        if batch.rejected_order_ids:
            raise RuntimeError("Offline verification order unexpectedly rejected")
        submissions.append(date)

    result = simulator.run(
        open_=frame([60000, 60200, 60300, 60400, 60500]),
        close=frame([60100, 60250, 60350, 60450, 60550]),
        high=frame([60200, 60300, 60400, 60500, 60600]),
        low=frame([59900, 60100, 60200, 60300, 60400]),
        volume=frame([100, 100, 100, 100, 100]),
        on_bar=on_bar, on_fill=lambda fill, notional: fills.append(fill),
    )
    if len(fills) != 2 or not all(fill.timestamp > submitted for fill, submitted in zip(fills, submissions)):
        raise RuntimeError("Expected exactly two next-bar fills")
    buy, sell = fills
    expected_buy, expected_sell = 60200 * 1.0005, 60400 * 0.9995
    expected_cash = 10000 - .01 * expected_buy * 1.001 + .01 * expected_sell * .999
    checks = [math.isclose(buy.fill_price, expected_buy),
              math.isclose(sell.fill_price, expected_sell),
              math.isclose(float(result.nav.iloc[-1]), expected_cash),
              math.isclose(float(result.positions.iloc[-1][symbol]), 0),
              all(fill.commission > 0 for fill in fills),
              math.isclose(spec.round_quantity(.0123456), .01234)]
    if not all(checks):
        raise RuntimeError("Fractional quantity, fees, slippage or NAV reconciliation failed")
    direct = distribution("quantjourney-bt").read_text("direct_url.json")
    provenance = json.loads(direct) if direct else {}
    report = {
        "status": "passed", "dataset": "synthetic_installation_check_not_a_strategy_backtest",
        "package": "quantjourney-bt", "version": version("quantjourney-bt"),
        "source_commit": provenance.get("vcs_info", {}).get("commit_id"),
        "symbol": symbol, "settlement_currency": "USDT", "fractional_quantity": .01,
        "next_bar_execution": True, "commission_bps": 10, "slippage_bps": 5,
        "fill_count": len(fills), "final_cash": float(result.cash.iloc[-1]),
        "final_nav": float(result.nav.iloc[-1]), "final_position": float(result.positions.iloc[-1][symbol]),
        "network_requests": 0,
    }
    output = Path(__file__).resolve().parents[2] / "work/backtesting/verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    try:
        import argparse
        from cryptoscope.backtesting.runner import evaluate, save_report
        from cryptoscope.agents.schemas import Snapshot
        from cryptoscope.research.demo import demo_snapshot
        from cryptoscope.research.settings import load_config
        parser = argparse.ArgumentParser(description='QuantJourney verification and archived crypto baseline backtests')
        parser.add_argument('command', choices=['verify','run','walk-forward','validate'], nargs='?', default='verify')
        source = parser.add_mutually_exclusive_group()
        source.add_argument('--snapshot', type=Path)
        source.add_argument('--demo', action='store_true')
        parser.add_argument('--strategy', choices=['ema_baseline','buy_hold_baseline'], default='ema_baseline')
        parser.add_argument('--fast', type=int, default=20)
        parser.add_argument('--slow', type=int, default=50)
        parser.add_argument('--strategy-spec', type=Path, help='Validated JSON strategy draft or spec; run command only')
        parser.add_argument('--train-bars',type=int,default=100)
        parser.add_argument('--test-bars',type=int,default=40)
        parser.add_argument('--embargo-bars',type=int,default=2)
        args = parser.parse_args()
        if args.command == 'verify':
            result = verify()
        else:
            if not args.snapshot and not args.demo:
                parser.error('run requires --snapshot or --demo')
            snapshot = Snapshot.parse(json.loads(args.snapshot.read_text(encoding='utf-8'))) if args.snapshot else demo_snapshot()
            config=load_config()
            if args.strategy_spec:
                from cryptoscope.strategy import StrategySpec
                if args.command!='run':
                    parser.error('--strategy-spec is supported by run only')
                body=json.loads(args.strategy_spec.read_text(encoding='utf-8'))
                spec=StrategySpec.parse(body.get('spec',body),config)
                if spec.symbol!=snapshot.symbol:
                    parser.error('Strategy spec and snapshot symbols differ')
                args.fast,args.slow,args.strategy=spec.fast,spec.slow,spec.strategy
            if args.command=='walk-forward':
                from cryptoscope.backtesting.validation import walk_forward
                report=walk_forward(snapshot,config,args.train_bars,args.test_bars,args.embargo_bars)
            elif args.command=='validate':
                from cryptoscope.backtesting.validation import robustness
                report=robustness(snapshot,config,args.fast,args.slow)
            else:
                report=evaluate(snapshot,config,args.fast,args.slow,args.strategy)
                if args.strategy_spec:
                    report['strategy_spec']=spec.to_dict()
                    report['strategy_artifact_id']=body.get('run_id')
            result = save_report(report)
            result = {k: result[k] for k in ('run_id','status','strategy','symbol','metrics','fingerprint')}
        print(json.dumps(result, indent=2, allow_nan=False))
    except ImportError as error:
        raise SystemExit("Run with .\\work\\environments\\backtesting\\Scripts\\python.exe; "
                         f"install requirements-backtest.txt first. Details: {error}") from error
