"""Resilience tests for the Binance Testnet client: rate limits, clock skew, transport errors.

All tests use a fake opener; no network access.
"""
import io
import json
import time
import urllib.error
from unittest.mock import patch

import pytest

from cryptoscope.execution.binance_testnet import (
    BinanceClockSkewError,
    BinanceNetworkError,
    BinanceRateLimitError,
    BinanceTestnetClient,
)


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, body, headers=None):
    return urllib.error.HTTPError("https://testnet.binance.vision/x", code, "err", headers or {}, io.BytesIO(json.dumps(body).encode()))


def _client():
    return BinanceTestnetClient(api_key="fixture", api_secret="fixture")


def test_critical_calls_probe_through_cooldown_but_entries_stay_blocked():
    c = _client()
    c._time_synced_monotonic = time.monotonic()  # skip time sync noise
    c.retry_after_monotonic = time.monotonic() + 100
    calls = []

    def fake_open(req, timeout=None):
        calls.append(req.full_url)
        return _Resp({"orderId": 1})

    with patch.object(c._opener, "open", side_effect=fake_open):
        # new entry (BUY market) is blocked by the cooldown
        with pytest.raises(BinanceRateLimitError):
            c.create_order("BTCUSDT", "BUY", "MARKET", 0.01)
        assert calls == []
        # protective exit/stop and cancel are allowed one probe
        assert c.create_order("BTCUSDT", "SELL", "MARKET", 0.01) == {"orderId": 1}
        assert len(calls) == 1
        # a second critical call right away is throttled (probe interval)
        with pytest.raises(BinanceRateLimitError):
            c.cancel_order("BTCUSDT", order_id=5)
        assert len(calls) == 1
        # after the probe interval another critical call is allowed
        c._last_critical_probe = time.monotonic() - c.CRITICAL_PROBE_INTERVAL - 0.1
        assert c.cancel_order("BTCUSDT", order_id=5) == {"orderId": 1}
        assert len(calls) == 2


def test_clock_skew_is_retried_once_after_resync():
    c = _client()
    seen = {"account": 0, "time": 0}

    def fake_open(req, timeout=None):
        if "/api/v3/time" in req.full_url:
            seen["time"] += 1
            return _Resp({"serverTime": int(time.time() * 1000) + 12345})
        seen["account"] += 1
        if seen["account"] == 1:
            raise _http_error(400, {"code": -1021, "msg": "Timestamp outside of recvWindow"})
        return _Resp({"balances": []})

    with patch.object(c._opener, "open", side_effect=fake_open):
        assert c.get_account() == {"balances": []}
    assert seen["account"] == 2
    assert seen["time"] == 2  # initial sync + forced resync after -1021
    assert abs(c._time_offset_ms - 12345) < 2000


def test_persistent_clock_skew_raises_after_single_retry():
    c = _client()

    def fake_open(req, timeout=None):
        if "/api/v3/time" in req.full_url:
            return _Resp({"serverTime": int(time.time() * 1000)})
        raise _http_error(400, {"code": -1021})

    with patch.object(c._opener, "open", side_effect=fake_open) as opened:
        with pytest.raises(BinanceClockSkewError):
            c.get_account()
        account_calls = [x for x in opened.call_args_list if "/account" in x.args[0].full_url]
        assert len(account_calls) == 2


def test_time_offset_is_cached_across_signed_calls():
    c = _client()
    times = []

    def fake_open(req, timeout=None):
        if "/api/v3/time" in req.full_url:
            times.append(1)
            return _Resp({"serverTime": int(time.time() * 1000)})
        return _Resp({})

    with patch.object(c._opener, "open", side_effect=fake_open):
        for _ in range(5):
            c.get_account()
    assert len(times) == 1


def test_get_retries_transport_errors_but_post_does_not():
    c = _client()
    c._time_synced_monotonic = time.monotonic()
    with patch("time.sleep"), patch.object(c._opener, "open", side_effect=urllib.error.URLError("down")) as opened:
        with pytest.raises(BinanceNetworkError):
            c.get_account()
        assert opened.call_count == 3  # 1 try + 2 retries
        opened.reset_mock()
        with pytest.raises(BinanceNetworkError):
            c.create_order("BTCUSDT", "BUY", "MARKET", 0.01)
        assert opened.call_count == 1  # never auto-retry order placement


def test_read_timeout_is_mapped_to_network_error():
    c = _client()
    c._time_synced_monotonic = time.monotonic()
    with patch("time.sleep"), patch.object(c._opener, "open", side_effect=TimeoutError("slow")):
        with pytest.raises(BinanceNetworkError):
            c.get_open_orders()


def test_time_resync_failure_does_not_fail_signed_call():
    c = _client()

    def fake_open(req, timeout=None):
        if "/api/v3/time" in req.full_url:
            raise urllib.error.URLError("time endpoint down")
        return _Resp({"ok": True})

    with patch("time.sleep"), patch.object(c._opener, "open", side_effect=fake_open):
        assert c.get_account() == {"ok": True}


def test_every_halt_raises_a_critical_alert_once_per_reason(tmp_path, monkeypatch):
    import asyncio

    from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot
    from cryptoscope.orchestrator.event_bus import EventBus
    from cryptoscope.orchestrator.events import SystemAlert

    monkeypatch.setenv("GOVERNOR_STATE_DB", str(tmp_path / "governor.db"))

    async def scenario():
        bus = EventBus()
        bot = ExecutionBot(bus, mode="PAPER", db_path=str(tmp_path / "state.db"))
        alerts = []

        async def on_alert(event):
            alerts.append(event)

        bus.subscribe(SystemAlert, on_alert)
        await bot.start()
        bot.halt_state.halt("Exchange protection mismatch", "test")
        bot.halt_state.halt("Exchange protection mismatch", "test")  # duplicate within 60s
        bot.halt_state.halt("Different reason", "test")
        await asyncio.sleep(0.2)
        await bot.stop()
        await bus.stop()
        return alerts

    alerts = asyncio.run(scenario())
    halts = [a for a in alerts if a.title == "Trading halted"]
    assert [a.severity for a in halts] == ["CRITICAL", "CRITICAL"]
    assert "Exchange protection mismatch" in halts[0].message and "Different reason" in halts[1].message
