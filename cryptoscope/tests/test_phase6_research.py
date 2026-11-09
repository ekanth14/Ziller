"""Tests for Phase 6: Multi-Coin Research and Long-Window Backtest Engine."""

import pytest
import pandas as pd
import numpy as np

from cryptoscope.research.multi_coin.strategy_engine import (
    MultiCoinResearchEngine,
    TradeRecord,
)
from cryptoscope.backtesting.cost_model import deflated_sharpe_ratio


def test_signals_generation():
    engine = MultiCoinResearchEngine()
    
    # 1. EMA Trend test data
    closes = [100.0] * 50 + [101.0, 103.0, 106.0, 110.0]
    df_ema = pd.DataFrame({
        "open": closes,
        "high": [c + 1.0 for c in closes],
        "low": [c - 1.0 for c in closes],
        "close": closes,
        "volume": [100.0] * len(closes),
        "quote_volume": [10000.0] * len(closes),
        "open_time": [1700000000000 + i * 3600000 for i in range(len(closes))],
    })
    # Evaluate at index 53 (uptrend accelerating)
    sig = engine.signal_ema_trend(df_ema, idx=53)
    assert sig in {"BUY", None}

    # 2. Volume Expansion Breakout test data
    # 20 quiet bars, then a huge volume breakout candle
    recent_closes = [100.0] * 20
    recent_highs = [101.0] * 20
    recent_lows = [99.0] * 20
    recent_vols = [100.0] * 20

    # Candle 21: Breakout
    recent_closes.append(105.0)
    recent_highs.append(106.0)
    recent_lows.append(100.0)
    recent_vols.append(500.0)  # 5x volume

    df_vol = pd.DataFrame({
        "open": [100.0] * 21,
        "high": recent_highs,
        "low": recent_lows,
        "close": recent_closes,
        "volume": recent_vols,
    })
    sig_vol = engine.signal_volume_expansion(df_vol, idx=20)
    assert sig_vol == "BUY"


def test_deflated_sharpe_ratio_penalizes_multiple_strategies():
    returns = [0.02, -0.01, 0.03, 0.01, -0.015, 0.025, 0.01] * 10
    dsr_single = deflated_sharpe_ratio(observed_sr=1.5, num_trials=1, returns=returns)
    dsr_multi = deflated_sharpe_ratio(observed_sr=1.5, num_trials=5, returns=returns)

    assert dsr_single["deflated_sharpe_ratio"] is not None
    assert dsr_multi["deflated_sharpe_ratio"] is not None
    # Testing 5 trials must result in lower deflated z-score than 1 trial
    assert dsr_multi["deflated_sharpe_ratio"] < dsr_single["deflated_sharpe_ratio"]


def test_performance_summary_computation():
    engine = MultiCoinResearchEngine(initial_capital=1000.0)
    
    trades = [
        TradeRecord(
            strategy="test_strat",
            symbol="BTCUSDT",
            cluster="CORE",
            entry_time_ms=1700000000000,
            exit_time_ms=1700003600000,
            entry_price=80000.0,
            exit_price=81000.0,
            effective_entry=80050.0,
            effective_exit=80950.0,
            notional_usd=200.0,
            gross_pnl_usd=2.50,
            total_fees_usd=0.30,
            total_slippage_usd=0.25,
            net_pnl_usd=1.95,
            net_return_pct=0.975,
            holding_bars=1,
            exit_reason="take_profit",
            year=2024,
        ),
        TradeRecord(
            strategy="test_strat",
            symbol="ETHUSDT",
            cluster="CORE",
            entry_time_ms=1700007200000,
            exit_time_ms=1700010800000,
            entry_price=3000.0,
            exit_price=2950.0,
            effective_entry=3005.0,
            effective_exit=2945.0,
            notional_usd=200.0,
            gross_pnl_usd=-3.33,
            total_fees_usd=0.30,
            total_slippage_usd=0.25,
            net_pnl_usd=-3.88,
            net_return_pct=-1.94,
            holding_bars=1,
            exit_reason="stop_loss",
            year=2024,
        ),
    ]

    summary = engine._compute_performance_summary(
        trades=trades,
        vetoes={"strategy": 1, "debate": 0, "risk": 2},
        final_nav=998.07,
        peak_nav=1001.95,
    )

    assert summary["trade_count"] == 2
    assert summary["win_rate_pct"] == 50.0
    assert summary["total_fees_usd"] == 0.60
    assert summary["vetoes"]["risk"] == 2
