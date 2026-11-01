"""Export historical candle features and forward returns for Laya model fine-tuning.

Dumps historical features and forward return labels into a clean JSONL dataset.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptoscope.market_data.candle_store import CandleStore
from cryptoscope.autotrader.decision import Tier1Engine


def export_training_dataset(symbol: str = "BTCUSDT", interval: str = "15m", output_path: str = "data/training/laya_dataset.jsonl"):
    root = Path(__file__).resolve().parents[1]
    db_path = root / "work/runtime/crypto_candles.db"
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    store = CandleStore(db_path)
    candles = store.load_candles(symbol, interval, limit=2000)
    if len(candles) < 30:
        # Fall back to snapshot fixtures
        snap_file = root / f"data/snapshots/historical_{symbol.lower()}_{interval}_999bars.json"
        if snap_file.exists():
            with open(snap_file, "r", encoding="utf-8") as f:
                snap_data = json.load(f)
                candles = snap_data.get("candles", [])
                print(f"[Info] Sourced {len(candles)} candles from snapshot {snap_file.name}")
        if len(candles) < 30:
            print(f"[Warning] Only {len(candles)} candles found for {symbol} ({interval}). Need at least 30.")
            return

    tier1 = Tier1Engine()
    records = []
    # Rolling feature window of 25 bars, label is next bar forward return
    for i in range(25, len(candles) - 1):
        window = candles[i - 25:i + 1]
        next_candle = candles[i + 1]
        eval_res = tier1.evaluate(window, symbol=symbol)

        curr_close = float(window[-1]["close"])
        next_close = float(next_candle["close"])
        forward_return_pct = round(((next_close - curr_close) / curr_close) * 100.0, 4)

        # Label: 1 if >0.2% return, -1 if <-0.2% return, 0 if flat
        if forward_return_pct >= 0.2:
            label = "BULLISH_EXPANSION"
        elif forward_return_pct <= -0.2:
            label = "BEARISH_CONTRACTION"
        else:
            label = "NEUTRAL"

        records.append({
            "timestamp": window[-1].get("close_time", 0),
            "symbol": symbol,
            "interval": interval,
            "discrete_encoding": eval_res["discrete_encoding"],
            "tier1_score": eval_res["score"],
            "tier1_action": eval_res["action"],
            "tier1_setup": eval_res["setup_type"],
            "forward_return_pct": forward_return_pct,
            "label": label,
        })

    with open(out_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(f"[OK] Exported {len(records)} fine-tuning examples to {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Laya Fine-tuning Dataset")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair symbol")
    parser.add_argument("--interval", default="15m", help="Candle timeframe")
    parser.add_argument("--out", default="data/training/laya_dataset.jsonl", help="Output JSONL path")
    args = parser.parse_args()
    export_training_dataset(args.symbol, args.interval, args.out)
