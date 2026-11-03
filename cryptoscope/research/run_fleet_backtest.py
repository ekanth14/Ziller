"""Institutional 3-Month Fleet Backtest with realistic fees, slippage, and walk-forward split.

Features:
- 3 months of candles across BTCUSDT, ETHUSDT, SOLUSDT (1-hour timeframe).
- 70% In-Sample (Train) / 30% Out-of-Sample (Test) walk-forward validation.
- Institutional fee schedule: 0.075% maker/taker fee (BNB fee discount).
- Execution slippage: 5 bps (0.05%) for BTC/ETH, 10 bps for SOL.
- Fixed fractional position sizing: 0.5% equity risk per trade.
- Strategies evaluated:
  1. EMA Trend Continuation (EMA20/50 cross with dynamic ATR protective stops)
  2. Volatility Compression Breakout (Parkinson/Garman-Klass squeeze with CVD confirmation)
  3. Statistical Arbitrage Pairs (ETH/BTC Ornstein-Uhlenbeck mean-reverting spread)
Saves results to work/reports/fleet_backtest_report.json.
"""

import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error

from cryptoscope.autotrader.strategies.volatility_breakout import VolatilityCompressionBreakoutStrategy
from cryptoscope.autotrader.strategies.stat_arb_pairs import StatArbPairsStrategy
from cryptoscope.quant.sizing import fixed_fractional_sizing

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cryptoscope.backtest")

DB_PATH = Path("work/runtime/crypto_candles.db")
FEE_RATE = 0.00075  # 0.075% per side
SLIPPAGE_MAJOR_BPS = 5.0  # 5 bps for BTC/ETH
SLIPPAGE_ALT_BPS = 10.0   # 10 bps for SOL
INITIAL_CAPITAL = 10000.0
FIXED_RISK_FRACTION = 0.005  # 0.5% equity per trade ($50)


def fetch_historical_candles_from_binance(symbol: str, target_count: int = 2160, interval: str = "1h") -> List[Dict[str, Any]]:
    """Fetch candles from Binance REST API paginating backwards."""
    candles: List[Dict[str, Any]] = []
    end_time: Optional[int] = None
    logger.info("Fetching %d historical %s candles for %s from Binance...", target_count, interval, symbol)

    while len(candles) < target_count:
        fetch_limit = min(1000, target_count - len(candles))
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={fetch_limit}"
        if end_time:
            url += f"&endTime={end_time}"

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not data:
                break

            batch = []
            for row in data:
                batch.append({
                    "open_time": float(row[0]) / 1000.0,
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                    "close_time": float(row[6]) / 1000.0,
                    "taker_buy_volume": float(row[9]),
                })

            # Prepend older batch
            candles = batch + candles
            # Update end_time to just before the earliest candle in this batch
            earliest_open_ms = int(data[0][0]) - 1
            end_time = earliest_open_ms

            if len(data) < fetch_limit:
                break
            time.sleep(0.1)  # rate limit courtesy
        except Exception as exc:
            logger.warning("Error fetching candles from Binance: %s", exc)
            break

    logger.info("Fetched %d candles for %s.", len(candles), symbol)
    return candles


def get_or_load_candles(symbol: str, target_count: int = 2160) -> List[Dict[str, Any]]:
    """Load candles from SQLite or fetch from Binance and cache them."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS crypto_candles (
            symbol TEXT,
            open_time REAL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            close_time REAL,
            taker_buy_volume REAL,
            interval TEXT,
            PRIMARY KEY (symbol, open_time, interval)
        )
    """)
    conn.commit()

    # Query existing 1h candles
    cur.execute(
        "SELECT open_time, open, high, low, close, volume, close_time, taker_buy_volume FROM crypto_candles WHERE symbol=? AND interval='1h' ORDER BY open_time ASC",
        (symbol,)
    )
    rows = cur.fetchall()

    if len(rows) >= target_count:
        conn.close()
        return [
            {
                "open_time": r[0], "open": r[1], "high": r[2], "low": r[3],
                "close": r[4], "volume": r[5], "close_time": r[6], "taker_buy_volume": r[7]
            }
            for r in rows
        ]

    # Fetch from Binance API
    fetched = fetch_historical_candles_from_binance(symbol, target_count=target_count, interval="1h")
    if fetched:
        cur.executemany(
            """
            INSERT OR REPLACE INTO crypto_candles 
            (symbol, interval, open_time, close_time, open, high, low, close, volume, taker_buy_volume, source)
            VALUES (?, '1h', ?, ?, ?, ?, ?, ?, ?, ?, 'binance')
            """,
            [
                (symbol, c["open_time"], c["close_time"], c["open"], c["high"], c["low"], c["close"], c["volume"], c["taker_buy_volume"])
                for c in fetched
            ]
        )
        conn.commit()
    conn.close()
    return fetched


def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> List[float]:
    atrs = [0.0] * len(candles)
    if len(candles) < period + 1:
        return atrs

    tr_list = []
    for i in range(len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        if i == 0:
            tr = h - l
        else:
            prev_c = candles[i - 1]["close"]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)

    atr = sum(tr_list[:period]) / period
    atrs[period - 1] = atr
    for i in range(period, len(candles)):
        atr = (atr * (period - 1) + tr_list[i]) / period
        atrs[i] = atr
    return atrs


def run_strategy_backtest(
    strategy_name: str,
    symbol: str,
    candles: List[Dict[str, Any]],
    is_train: bool,
    initial_cash: float = 10000.0,
) -> Dict[str, Any]:
    """Execute strategy logic bar-by-bar with slippage and fees."""
    if len(candles) < 60:
        return {"trades": 0, "net_pnl": 0.0, "win_rate": 0.0}

    slippage_bps = SLIPPAGE_MAJOR_BPS if symbol in {"BTCUSDT", "ETHUSDT"} else SLIPPAGE_ALT_BPS
    slippage_rate = slippage_bps / 10000.0

    closes = [c["close"] for c in candles]
    atrs = calculate_atr(candles, period=14)

    # Strategy helper instances
    vol_strat = VolatilityCompressionBreakoutStrategy() if strategy_name == "volatility_breakout" else None

    # EMA calculations for ema_trend
    ema20 = [0.0] * len(candles)
    ema50 = [0.0] * len(candles)
    k20, k50 = 2.0 / 21.0, 2.0 / 51.0
    val20, val50 = closes[0], closes[0]
    for idx, cl in enumerate(closes):
        val20 += k20 * (cl - val20)
        val50 += k50 * (cl - val50)
        ema20[idx] = val20
        ema50[idx] = val50

    cash = initial_cash
    equity = initial_cash
    position = 0.0  # coins
    entry_price = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    side = "NONE"

    trades: List[Dict[str, Any]] = []
    equity_curve: List[float] = [initial_cash]
    peak_equity = initial_cash
    max_drawdown_pct = 0.0

    for i in range(50, len(candles)):
        c = candles[i]
        curr_price = c["close"]
        curr_atr = atrs[i] or (curr_price * 0.015)

        # Check exit conditions if in position
        if position > 0:
            exit_triggered = False
            exit_price = 0.0
            exit_reason = ""

            if side == "BUY":
                if c["low"] <= stop_loss:
                    exit_triggered = True
                    exit_price = stop_loss
                    exit_reason = "STOP_LOSS"
                elif c["high"] >= take_profit:
                    exit_triggered = True
                    exit_price = take_profit
                    exit_reason = "TAKE_PROFIT"
                elif strategy_name == "ema_trend" and ema20[i] < ema50[i]:
                    exit_triggered = True
                    exit_price = curr_price
                    exit_reason = "TREND_FLIP"

            if exit_triggered:
                # Apply slippage on exit
                eff_exit = exit_price * (1.0 - slippage_rate)
                sale_val = position * eff_exit
                fee = sale_val * FEE_RATE
                cash += (sale_val - fee)
                pnl = (sale_val - fee) - cost_basis
                pnl_pct = (pnl / cost_basis) * 100.0

                trades.append({
                    "entry_time": entry_time,
                    "exit_time": c["close_time"],
                    "side": side,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": exit_reason,
                })
                position = 0.0
                side = "NONE"

        # Check entry signals if flat
        if position == 0:
            signal_entry = False
            target_stop = 0.0
            target_tp = 0.0

            if strategy_name == "ema_trend":
                # Bullish EMA cross + momentum
                if ema20[i] > ema50[i] and ema20[i - 1] <= ema50[i - 1]:
                    signal_entry = True
                    target_stop = curr_price - (1.5 * curr_atr)
                    target_tp = curr_price + (3.0 * curr_atr)

            elif strategy_name == "volatility_breakout":
                res = vol_strat.evaluate(candles[max(0, i - 65) : i + 1])
                if res and res.get("side") == "BUY":
                    signal_entry = True
                    target_stop = res.get("stop_loss", curr_price - 1.5 * curr_atr)
                    target_tp = res.get("take_profit", curr_price + 3.0 * curr_atr)

            if signal_entry:
                # Sizing via Fixed Fractional Risk
                sizing = fixed_fractional_sizing(
                    account_balance=cash,
                    entry_price=curr_price,
                    stop_loss=target_stop,
                    risk_fraction=FIXED_RISK_FRACTION,
                )
                if sizing["status"] == "APPROVED" and sizing["position_qty"] > 0:
                    desired_qty = sizing["position_qty"]
                    # Apply slippage on entry
                    eff_entry = curr_price * (1.0 + slippage_rate)
                    cost_basis = desired_qty * eff_entry
                    fee = cost_basis * FEE_RATE
                    if cash >= (cost_basis + fee):
                        cash -= (cost_basis + fee)
                        position = desired_qty
                        entry_price = curr_price
                        entry_time = c["close_time"]
                        stop_loss = target_stop
                        take_profit = target_tp
                        side = "BUY"

        # Mark-to-market equity
        current_eq = cash + (position * curr_price if position > 0 else 0.0)
        equity_curve.append(current_eq)
        peak_equity = max(peak_equity, current_eq)
        dd = (peak_equity - current_eq) / peak_equity if peak_equity > 0 else 0.0
        max_drawdown_pct = max(max_drawdown_pct, dd * 100.0)

    # Close any open trade at final bar
    if position > 0:
        eff_exit = closes[-1] * (1.0 - slippage_rate)
        sale_val = position * eff_exit
        fee = sale_val * FEE_RATE
        cash += (sale_val - fee)
        pnl = (sale_val - fee) - cost_basis
        trades.append({
            "entry_time": entry_time,
            "exit_time": candles[-1]["close_time"],
            "side": side,
            "entry_price": round(entry_price, 2),
            "exit_price": round(closes[-1], 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / cost_basis) * 100.0, 2),
            "reason": "END_OF_BACKTEST",
        })

    total_trades = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    gross_profits = sum(t["pnl"] for t in wins)
    gross_losses = abs(sum(t["pnl"] for t in losses))
    profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else (99.0 if gross_profits > 0 else 0.0)
    net_pnl = cash - initial_cash
    return_pct = (net_pnl / initial_cash) * 100.0
    expectancy = (net_pnl / total_trades) if total_trades > 0 else 0.0

    return {
        "strategy": strategy_name,
        "symbol": symbol,
        "split": "TRAIN (70%)" if is_train else "TEST (30%)",
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 2),
        "net_pnl_usd": round(net_pnl, 2),
        "return_pct": round(return_pct, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_usd": round(expectancy, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "initial_capital": initial_cash,
        "final_capital": round(cash, 2),
    }


def run_stat_arb_backtest(
    candles_eth: List[Dict[str, Any]],
    candles_btc: List[Dict[str, Any]],
    is_train: bool,
    initial_cash: float = 10000.0,
) -> Dict[str, Any]:
    """Execute statistical arbitrage backtest on ETH/BTC pair."""
    n = min(len(candles_eth), len(candles_btc))
    strat = StatArbPairsStrategy(entry_zscore=1.8, exit_zscore=0.25, stop_zscore=3.5, window=30)
    cash = initial_cash
    position_eth = 0.0
    position_btc = 0.0
    trades: List[Dict[str, Any]] = []
    peak_equity = initial_cash
    max_drawdown_pct = 0.0

    entry_eth = 0.0
    entry_btc = 0.0
    entry_time = 0.0

    for i in range(45, n):
        sub_eth = candles_eth[:i + 1]
        sub_btc = candles_btc[:i + 1]
        p_eth = candles_eth[i]["close"]
        p_btc = candles_btc[i]["close"]

        # If in position, check mean reversion exit
        if position_eth != 0:
            res = strat.evaluate_pair(sub_eth, sub_btc, "ETHUSDT", "BTCUSDT")
            z = res.get("zscore", 0.0) if res else 0.0
            # Exit when z-score mean reverts close to 0 or hits stop
            if abs(z) <= 0.25 or abs(z) >= 3.5:
                # Liquidate
                eff_exit_eth = p_eth * (1.0 - 0.0005)
                eff_exit_btc = p_btc * (1.0 + 0.0005)  # cover short
                pnl_eth = (eff_exit_eth - entry_eth) * position_eth
                pnl_btc = (entry_btc - eff_exit_btc) * abs(position_btc)
                fees = (position_eth * eff_exit_eth + abs(position_btc) * eff_exit_btc) * FEE_RATE
                net_trade_pnl = pnl_eth + pnl_btc - fees
                cash += net_trade_pnl
                trades.append({
                    "entry_time": entry_time,
                    "exit_time": candles_eth[i]["close_time"],
                    "pnl": round(net_trade_pnl, 2),
                    "reason": "MEAN_REVERSION" if abs(z) <= 0.25 else "STOP_ZSCORE",
                })
                position_eth = 0.0
                position_btc = 0.0

        elif position_eth == 0:
            res = strat.evaluate_pair(sub_eth, sub_btc, "ETHUSDT", "BTCUSDT")
            if res and res.get("side") == "LONG_SPREAD":
                beta = res.get("hedge_ratio_beta", 0.035)
                # Buy ETH, Short BTC
                risk_usd = cash * FIXED_RISK_FRACTION
                notional = risk_usd / 0.02  # 2% stop distance
                notional = min(notional, cash * 0.4)
                qty_eth = (notional * 0.5) / p_eth
                qty_btc = -(qty_eth * beta)

                entry_eth = p_eth * (1.0 + 0.0005)
                entry_btc = p_btc * (1.0 - 0.0005)
                entry_time = candles_eth[i]["close_time"]
                fees_entry = notional * FEE_RATE
                cash -= fees_entry
                position_eth = qty_eth
                position_btc = qty_btc

        curr_eq = cash + (position_eth * (p_eth - entry_eth) if position_eth else 0.0) + (abs(position_btc) * (entry_btc - p_btc) if position_btc else 0.0)
        peak_equity = max(peak_equity, curr_eq)
        dd = (peak_equity - curr_eq) / peak_equity if peak_equity > 0 else 0.0
        max_drawdown_pct = max(max_drawdown_pct, dd * 100.0)

    # Close any open position at final bar
    if position_eth != 0:
        p_eth = candles_eth[-1]["close"]
        p_btc = candles_btc[-1]["close"]
        eff_exit_eth = p_eth * (1.0 - 0.0005)
        eff_exit_btc = p_btc * (1.0 + 0.0005)
        pnl_eth = (eff_exit_eth - entry_eth) * position_eth
        pnl_btc = (entry_btc - eff_exit_btc) * abs(position_btc)
        fees = (position_eth * eff_exit_eth + abs(position_btc) * eff_exit_btc) * FEE_RATE
        net_trade_pnl = pnl_eth + pnl_btc - fees
        cash += net_trade_pnl
        trades.append({
            "entry_time": entry_time,
            "exit_time": candles_eth[-1]["close_time"],
            "pnl": round(net_trade_pnl, 2),
            "reason": "END_OF_BACKTEST",
        })

    total_trades = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    gross_profits = sum(t["pnl"] for t in wins)
    gross_losses = abs(sum(t["pnl"] for t in losses))
    profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else (99.0 if gross_profits > 0 else 0.0)
    net_pnl = cash - initial_cash
    return_pct = (net_pnl / initial_cash) * 100.0
    expectancy = (net_pnl / total_trades) if total_trades > 0 else 0.0

    return {
        "strategy": "stat_arb_pairs",
        "symbol": "ETH/BTC",
        "split": "TRAIN (70%)" if is_train else "TEST (30%)",
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 2),
        "net_pnl_usd": round(net_pnl, 2),
        "return_pct": round(return_pct, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_usd": round(expectancy, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "initial_capital": initial_cash,
        "final_capital": round(cash, 2),
    }


def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    candle_store: Dict[str, List[Dict[str, Any]]] = {}

    print("================================================================================")
    print("3-MONTH FLEET BACKTEST (BTC, ETH, SOL) - Realistic Fees & Slippage")
    print("Fee: 0.075% | Slippage: 5 bps (BTC/ETH), 10 bps (SOL) | Sizing: Fixed Fractional 0.5%")
    print("Split: 70% In-Sample (Train) / 30% Out-of-Sample (Test)")
    print("================================================================================\n")

    for sym in symbols:
        candles = get_or_load_candles(sym, target_count=2160)
        candle_store[sym] = candles
        print(f"Loaded {len(candles)} 1h bars for {sym}")

    results = []

    for sym in symbols:
        candles = candle_store[sym]
        split_idx = int(len(candles) * 0.70)
        train_candles = candles[:split_idx]
        test_candles = candles[split_idx:]

        for strat in ["ema_trend", "volatility_breakout"]:
            res_train = run_strategy_backtest(strat, sym, train_candles, is_train=True)
            res_test = run_strategy_backtest(strat, sym, test_candles, is_train=False)
            results.extend([res_train, res_test])

    # Stat Arb Pairs on ETH/BTC
    eth_c = candle_store["ETHUSDT"]
    btc_c = candle_store["BTCUSDT"]
    split_idx = int(min(len(eth_c), len(btc_c)) * 0.70)
    sa_train = run_stat_arb_backtest(eth_c[:split_idx], btc_c[:split_idx], is_train=True)
    sa_test = run_stat_arb_backtest(eth_c[split_idx:], btc_c[split_idx:], is_train=False)
    results.extend([sa_train, sa_test])

    report_path = Path("work/reports/fleet_backtest_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 95)
    print(f"{'Strategy':<22} | {'Symbol':<10} | {'Split':<12} | {'Trades':<6} | {'WinRate%':<8} | {'NetPnL($)':<10} | {'Return%':<8} | {'ProfitFactor':<12} | {'MaxDD%':<6}")
    print("-" * 95)
    for r in results:
        print(
            f"{r['strategy']:<22} | {r['symbol']:<10} | {r['split']:<12} | {r['total_trades']:<6} | "
            f"{r['win_rate_pct']:<8.1f} | {r['net_pnl_usd']:<10.2f} | {r['return_pct']:<8.2f} | "
            f"{r['profit_factor']:<12.2f} | {r['max_drawdown_pct']:<6.2f}"
        )
    print("=" * 95)
    print(f"Full backtest report saved to: {report_path}\n")


if __name__ == "__main__":
    main()
