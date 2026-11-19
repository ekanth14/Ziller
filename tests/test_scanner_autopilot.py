"""Scanner ranking/filters, autopilot rotation rules, and the fleet fixes (spot-only, no repeat spam, debate model)."""
import asyncio
import math

from cryptoscope.desk.scanner import Autopilot, MarketScanner, factors


def _ticker(sym, vol=50e6, chg=2.0, price=10.0):
    return {"symbol": sym, "lastPrice": str(price), "priceChangePercent": str(chg), "quoteVolume": str(vol),
            "highPrice": str(price * 1.05), "lowPrice": str(price * 0.95), "count": 1000}


def _klines(drift, n=90, vol=0.03, seed=1):
    out, p = [], 100.0
    for i in range(n):
        o = p
        p *= math.exp(drift + vol * math.sin(i * 1.7 + seed))
        out.append({"open_time": i * 86400, "open": o, "high": max(o, p) * 1.01, "low": min(o, p) * 0.99,
                    "close": p, "volume": 1000.0})
    return out


TREND = {"UPAUSDT": 0.012, "UPBUSDT": 0.010, "UPCUSDT": 0.008, "UPDUSDT": 0.007, "UPEUSDT": 0.006, "UPFUSDT": 0.005,
         "DOWNXUSDT": -0.01, "FLATUSDT": 0.0}


def _scanner(**kw):
    tickers = [_ticker(s) for s in TREND] + [_ticker("USDCUSDT"), _ticker("TINYUSDT", vol=1e5),
                                            _ticker("PUMPUSDT", chg=60.0), _ticker("BTCUPUSDT")]
    syms = {t["symbol"] for t in tickers}
    return MarketScanner(tickers_fetcher=lambda: tickers, live_symbols=lambda: syms,
                         klines_fetcher=lambda s, i, n: _klines(TREND.get(s, 0.0), seed=len(s)),
                         testnet_symbols=lambda: {"UPAUSDT", "UPBUSDT"}, **kw)


def test_scanner_filters_and_picks_top_uptrends():
    r = _scanner().scan("PAPER")
    excluded = {x["symbol"]: x["excluded"] for x in r["all"] if x["excluded"]}
    assert excluded["USDCUSDT"] == "stable_or_leveraged" and excluded["BTCUPUSDT"] == "stable_or_leveraged"
    assert excluded["TINYUSDT"] == "illiquid" and excluded["PUMPUSDT"] == "spike_24h"
    assert len(r["top"]) <= 5
    assert "DOWNXUSDT" not in r["top"] and "FLATUSDT" not in r["top"]
    assert r["top"] and all(s.startswith("UP") for s in r["top"])
    assert r["counts"]["universe"] == len(r["all"])


def test_scanner_testnet_mode_keeps_only_testnet_pairs():
    r = _scanner().scan("TESTNET")
    assert set(r["top"]) <= {"UPAUSDT", "UPBUSDT"}


def test_factors_need_history_and_flag_pegs():
    assert factors(_klines(0.01, n=20)) is None
    peg = factors([{"open_time": i, "open": 1, "high": 1.0001, "low": 0.9999, "close": 1 + (i % 2) * 1e-5, "volume": 1}
                   for i in range(60)])
    assert peg["vol30"] < 0.10


class _Fleet:
    def __init__(self):
        self.running, self.symbols, self.calls = False, [], []

    def status(self):
        return {"running": self.running, "symbols": self.symbols}

    def start(self, mode, symbols, actor):
        self.calls.append(("start", list(symbols)))
        self.running, self.symbols = True, list(symbols)

    def stop(self, reason=""):
        self.calls.append(("stop", reason))
        self.running = False


def test_autopilot_starts_then_rotates_only_when_flat():
    scanner, fleet, holding = _scanner(), _Fleet(), {"n": 0}
    ap = Autopilot(scanner, fleet, lambda: holding["n"], period_seconds=3600)
    ap.start("PAPER", "admin")
    ap.stop()
    assert fleet.calls[0][0] == "start" and ap.last["action"] == "started"
    fleet.symbols = ["OLDUSDT"]  # pretend the market moved on
    holding["n"] = 1
    ap._cycle("admin")
    assert ap.last["action"] == "rotation deferred (open positions)"
    holding["n"] = 0
    ap._cycle("admin")
    assert ap.last["action"] == "rotated" and fleet.calls[-1][0] == "start"


def test_autopilot_does_nothing_when_no_pair_is_eligible():
    tickers = [_ticker("DOWNXUSDT")]
    scanner = MarketScanner(tickers_fetcher=lambda: tickers, live_symbols=lambda: {"DOWNXUSDT"},
                            klines_fetcher=lambda s, i, n: _klines(-0.01))
    fleet = _Fleet()
    ap = Autopilot(scanner, fleet, lambda: 0)
    ap._cycle("admin")
    assert fleet.calls == [] and ap.last["action"] == "no eligible symbols"


# ------------------------------------------------------------------ fleet fixes
def test_strategy_bot_drops_spot_shorts_and_repeated_proposals():
    from cryptoscope.orchestrator.bots.strategy_bot import StrategyBot
    from cryptoscope.orchestrator.event_bus import EventBus
    from cryptoscope.orchestrator.events import Signal, TradeIntent

    async def run():
        bus = EventBus()
        bot = StrategyBot(bus, cooldown_sec=0)
        seen = []

        async def grab(e):
            seen.append(e)

        bus.subscribe(TradeIntent, grab)
        sig = lambda d: Signal(symbol="BTCUSDT", direction=d, confidence=0.9, strategy_id="t",  # noqa: E731
                               indicators={"price": 100.0, "atr": 1.0})
        await bot._evaluate_signal(sig("SELL"))
        await bot._evaluate_signal(sig("BUY"))
        await bot._evaluate_signal(sig("BUY"))  # same candle, same price -> suppressed
        await asyncio.sleep(0.05)
        return bot, seen

    bot, seen = asyncio.run(run())
    assert [e.direction for e in seen] == ["BUY"]
    assert bot.suppressed_shorts == 1 and bot.suppressed_repeats == 1


def test_debate_model_prefers_configured_then_installed(monkeypatch):
    from cryptoscope.agents import consensus

    import io
    import json

    tags = {"models": [{"name": "laya-quant:latest", "details": {"family": "gemma4"}},
                       {"name": "gemma4-quant:12b", "details": {"family": "gemma4"}},
                       {"name": "laya:latest", "details": {"family": "modern-bert"}}]}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp(json.dumps(tags).encode()))
    monkeypatch.setattr(consensus, "_RESOLVED_MODEL", None)
    monkeypatch.setenv("OLLAMA_DEBATE_MODEL", "laya-quant:latest")      # configured + installed: honoured
    assert consensus.resolve_debate_model() == "laya-quant:latest"
    monkeypatch.setenv("OLLAMA_DEBATE_MODEL", "my-model")               # configured but not installed: replaced
    assert consensus.resolve_debate_model() == "laya-quant:latest"
    monkeypatch.delenv("OLLAMA_DEBATE_MODEL")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:12b")                    # the .env value on this machine
    assert consensus.resolve_debate_model() == "gemma4-quant:12b"

    def down(*a, **k):
        raise OSError("ollama down")
    monkeypatch.setattr("urllib.request.urlopen", down)
    monkeypatch.setattr(consensus, "_RESOLVED_MODEL", None)
    monkeypatch.setenv("OLLAMA_MODEL", "my-model")                      # cannot verify: keep it, call fails closed
    assert consensus.resolve_debate_model() == "my-model"
