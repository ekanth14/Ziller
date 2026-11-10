import pytest
from core.quant.pipeline import QuantPipeline, PortfolioCoordinator, run_offline_validation

def test_pipeline_streaming_bar():
    pipeline = QuantPipeline(symbol="BTCUSDT")
    metrics = {}
    for i in range(30):
        metrics = pipeline.on_bar(
            open_p=100.0 + i,
            high_p=105.0 + i,
            low_p=98.0 + i,
            close_p=102.0 + i,
            volume=1000.0,
            bid_p=101.9,
            bid_q=50.0,
            ask_p=102.1,
            ask_q=40.0,
        )
    assert "log_return" in metrics
    assert "ewma_vol" in metrics
    assert "atr" in metrics
    assert "z_score" in metrics
    assert "microprice" in metrics
    assert "is_high_vol" in metrics
    assert "var_95" in metrics
    assert metrics["symbol"] == "BTCUSDT"

def test_portfolio_coordinator():
    coord = PortfolioCoordinator(symbols=["BTCUSDT", "ETHUSDT"])
    coord.update_price("BTCUSDT", [100.0 + i for i in range(25)])
    coord.update_price("ETHUSDT", [50.0 + (i * 0.5) for i in range(25)])
    summary = coord.compute_portfolio_summary()
    assert "correlations" in summary
    assert "risk_parity_weights" in summary
    assert "portfolio_volatility" in summary

def test_offline_validation():
    # 20 trades
    trades = [100.0, -50.0, 80.0, -40.0] * 5
    report = run_offline_validation(trades)
    assert "expected_value" in report
    assert "profit_factor" in report
    assert "monte_carlo_95_dd" in report
    assert report["profit_factor"] == 2.0
