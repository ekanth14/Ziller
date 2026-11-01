"""Run with python -m cryptoscope.research from the repository root."""
import argparse
import json
from pathlib import Path
import sys
import uuid
from cryptoscope.agents.graph import ResearchGraph
from cryptoscope.agents.schemas import Snapshot
from cryptoscope.execution.paper_broker import PaperBroker
from cryptoscope.providers.binance import BinanceProvider
from cryptoscope.providers.laya import LayaProvider
from cryptoscope.research.demo import DemoProvider, demo_snapshot
from cryptoscope.research.settings import ROOT, load_config
from cryptoscope.storage.research_store import ResearchStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="Zien Laya research and spot paper trading")
    parser.add_argument("--config", type=Path, help="JSON settings overrides")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Verify local Laya model availability")
    commands.add_parser("status", help="Show research runs and paper portfolio")
    commands.add_parser('pause-entries', help='Persistently halt new paper entries; exits stay available')
    commands.add_parser('resume-entries', help='Explicitly release the persistent entry halt')
    demo = commands.add_parser("demo", help="Run isolated synthetic fixtures without Ollama/network")
    demo.add_argument("--paper", action="store_true", help="Execute synthetic proposal in the demo ledger")
    analyze = commands.add_parser("analyze", help="Run the configured Laya model")
    source = analyze.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path, help="Imported point-in-time JSON snapshot")
    source.add_argument("--live", action="store_true", help="Fetch public Binance spot candles")
    analyze.add_argument("--symbol", default="BTCUSDT")
    analyze.add_argument("--paper", action="store_true", help="Enable simulated fills using fresh live quotes")
    analyze.add_argument('--kronos', action='store_true', help='Add locally installed Kronos forecast evidence to Laya research')
    mark = commands.add_parser("mark", help="Evaluate paper stop/target against a fresh public quote")
    mark.add_argument("--symbol", required=True)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "doctor":
            provider = LayaProvider(config)
            models = provider.models()
            available = provider.model in models
            print(json.dumps({"model": provider.model, "available": available, "installed_models": models}, indent=2))
            return 0 if available else 1
        is_demo = args.command == "demo"
        directory = ROOT / "work" / ("research-demo" if is_demo else "research-agent")
        if is_demo:
            directory = directory / uuid.uuid4().hex
        broker = PaperBroker(directory / "paper.sqlite3", config)
        store = ResearchStore(directory)
        if args.command in {'pause-entries','resume-entries'}:
            print(json.dumps(broker.set_halt(args.command == 'pause-entries'), indent=2))
            return 0
        if args.command == "status":
            print(json.dumps({"portfolio": broker.portfolio(), "controls": broker.controls(), "runs": store.recent()}, indent=2))
            return 0
        if args.command == "mark":
            if args.symbol not in config["symbols"]:
                raise ValueError("symbol is outside configured universe")
            print(json.dumps(broker.mark(BinanceProvider().quote(args.symbol)), indent=2))
            return 0
        feed = None
        if is_demo:
            snapshot = demo_snapshot()
            provider = DemoProvider(snapshot)
            quote_supplier = provider.quote
        else:
            if args.symbol not in config["symbols"]:
                raise ValueError("symbol is outside configured universe")
            if args.snapshot:
                if args.paper:
                    raise ValueError("paper execution of imported snapshots is disabled; use --live")
                snapshot = Snapshot.parse(json.loads(args.snapshot.read_text(encoding="utf-8")))
                quote_supplier = None
            else:
                feed = BinanceProvider()
                snapshot = feed.snapshot(args.symbol, config["interval"])
                quote_supplier = feed.quote
            provider = LayaProvider(config)
        from cryptoscope.forecasting import forecast
        graph = ResearchGraph(provider, store, broker, config,
                              ROOT / "reports" / ("demo" if is_demo else "research"),
                              on_stage=lambda name: print(f"Completed: {name}", file=sys.stderr, flush=True),
                              forecast_supplier=forecast if getattr(args, 'kronos', False) else None)
        body = graph.run(snapshot, quote_supplier, args.paper)
        archive = ROOT / "data" / "snapshots"
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f"{body['run_id']}.json").write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
        if feed:
            archive = ROOT / "data" / "raw"
            archive.mkdir(parents=True, exist_ok=True)
            (archive / f"{body['run_id']}.json").write_text(json.dumps(feed.raw), encoding="utf-8")
        print(json.dumps({key: body[key] for key in ("run_id", "status", "model", "mode", "report_directory")}, indent=2))
        print(json.dumps({"decision": body.get("decision"), "execution": body.get("execution"), "error": body.get("error")}, indent=2))
        return 0 if body["status"] == "completed" else 1
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
