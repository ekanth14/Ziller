import pytest
from core.quant.microstructure.order_flow import (
    compute_cumulative_volume_delta,
    compute_cvd_from_trades,
    compute_cvd_from_candles,
    detect_delta_divergence,
    detect_absorption,
    OrderFlowScreener,
    DivergenceType,
    AbsorptionType,
)

def test_cumulative_volume_delta_basic():
    buy_vol = [10.0, 20.0, 15.0, 5.0]
    sell_vol = [8.0, 12.0, 25.0, 5.0]
    # deltas: [+2.0, +8.0, -10.0, 0.0]
    # cvd: [2.0, 10.0, 0.0, 0.0]
    cvd = compute_cumulative_volume_delta(buy_vol, sell_vol)
    assert cvd == pytest.approx([2.0, 10.0, 0.0, 0.0])

def test_cumulative_volume_delta_initial_offset():
    buy_vol = [10.0, 5.0]
    sell_vol = [5.0, 10.0]
    cvd = compute_cumulative_volume_delta(buy_vol, sell_vol, initial_delta=100.0)
    assert cvd == pytest.approx([105.0, 100.0])

def test_cvd_empty_or_mismatched():
    assert compute_cumulative_volume_delta([], []) == []
    with pytest.raises(ValueError, match="Length mismatch"):
        compute_cumulative_volume_delta([10.0], [5.0, 2.0])

def test_cvd_from_trades():
    trades = [
        {"price": 100.0, "size": 1.5, "side": "buy"},
        {"price": 100.5, "size": 2.0, "side": "sell"},
        {"price": 101.0, "size": 0.5, "is_buyer_maker": False}, # Taker buy
        {"price": 101.0, "size": 1.0, "is_buyer_maker": True},  # Taker sell
    ]
    # deltas: +1.5, -2.0, +0.5, -1.0
    # cvd: 1.5, -0.5, 0.0, -1.0
    cvd = compute_cvd_from_trades(trades)
    assert cvd == pytest.approx([1.5, -0.5, 0.0, -1.0])

def test_cvd_from_candles():
    candles = [
        {"taker_buy_volume": 60.0, "volume": 100.0}, # buy=60, sell=40 -> delta=+20
        {"taker_buy_volume": 30.0, "volume": 100.0}, # buy=30, sell=70 -> delta=-40
        {"taker_buy_volume": 50.0, "volume": 100.0}, # buy=50, sell=50 -> delta=0
    ]
    cvd = compute_cvd_from_candles(candles)
    assert cvd == pytest.approx([20.0, -20.0, -20.0])

def test_detect_delta_divergence_bearish_regular():
    # Price makes higher high, CVD makes lower high -> Bearish Regular Divergence
    # index: 0, 1, 2, 3, 4
    prices = [100.0, 102.0, 101.0, 104.0, 105.0]
    cvd =    [10.0,  50.0,  20.0,  30.0,  25.0]
    # At index 3: price=104 > max(100, 102, 101)=102, but CVD=30 < 50
    # At index 4: price=105 > max(100, 102, 101, 104)=104, and CVD=25 < 30
    divergences = detect_delta_divergence(prices, cvd, lookback=4)
    bearish = [d for d in divergences if d["type"] == DivergenceType.BEARISH_REGULAR.value]
    assert len(bearish) >= 1
    indices = [d["index"] for d in bearish]
    assert 4 in indices
    assert bearish[-1]["price_higher"] is True
    assert bearish[-1]["cvd_lower"] is True

def test_detect_delta_divergence_bullish_regular():
    # Price makes lower low, CVD makes higher low -> Bullish Regular Divergence
    prices = [100.0, 95.0, 97.0, 92.0, 90.0]
    cvd =    [-10.0, -50.0, -30.0, -20.0, -15.0]
    divergences = detect_delta_divergence(prices, cvd, lookback=4)
    bullish = [d for d in divergences if d["type"] == DivergenceType.BULLISH_REGULAR.value]
    assert len(bullish) >= 1
    indices = [d["index"] for d in bullish]
    assert 4 in indices
    assert bullish[-1]["price_lower"] is True
    assert bullish[-1]["cvd_higher"] is True

def test_detect_absorption():
    # Absorption: high volume bar with tight range (high - low)
    highs =   [105.0, 106.0, 105.5, 105.2, 105.1]
    lows =    [100.0, 101.0, 102.0, 104.8, 104.9] # range bar 3 is 0.4, bar 4 is 0.2 (very narrow)
    volumes = [100.0, 120.0, 110.0, 500.0, 600.0] # volume bar 3 and 4 are massive
    deltas =  [5.0,   10.0,  -5.0,  250.0, -300.0]

    absorptions = detect_absorption(
        highs=highs,
        lows=lows,
        volumes=volumes,
        deltas=deltas,
        volume_threshold_percentile=70.0,
        spread_threshold_percentile=40.0,
    )
    assert len(absorptions) >= 2
    # Bar 3 has huge positive delta with narrow spread -> ASK absorption (passive sellers absorbed buyers)
    assert absorptions[0]["index"] == 3
    assert absorptions[0]["type"] == AbsorptionType.ASK_ABSORPTION.value
    # Bar 4 has huge negative delta with narrow spread -> BID absorption (passive buyers absorbed sellers)
    assert absorptions[1]["index"] == 4
    assert absorptions[1]["type"] == AbsorptionType.BID_ABSORPTION.value

def test_order_flow_screener_pipeline():
    screener = OrderFlowScreener()
    candles = [
        {"open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 1000.0, "taker_buy_volume": 600.0},
        {"open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0, "volume": 1200.0, "taker_buy_volume": 700.0},
        {"open": 105.0, "high": 105.5, "low": 104.8, "close": 105.2, "volume": 5000.0, "taker_buy_volume": 4000.0},
        {"open": 105.2, "high": 107.0, "low": 105.0, "close": 106.5, "volume": 1100.0, "taker_buy_volume": 450.0},
        {"open": 106.5, "high": 108.0, "low": 106.0, "close": 107.5, "volume": 900.0, "taker_buy_volume": 400.0},
    ]
    report = screener.analyze(candles)
    assert "cvd" in report
    assert len(report["cvd"]) == 5
    assert "divergences" in report
    assert "absorptions" in report
    assert report["latest_cvd"] is not None
    assert isinstance(report["absorptions"], list)
