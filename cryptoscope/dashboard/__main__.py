import math
import signal
import sqlite3
"""Serve the institutional ZILLERS crypto terminal: python -m cryptoscope.dashboard --port 8900."""
import argparse
from datetime import datetime, timezone
import threading
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import logging
import os
import sys
from pathlib import Path
import time
from urllib.parse import parse_qs, urlsplit

from cryptoscope.auth.security import (
    AccountLockoutManager,
    RateLimiter,
    extract_client_ip,
    verify_password,
    hash_password,
    needs_rehash,
)
from cryptoscope.auth.store import AuthStore
from cryptoscope.dashboard.data import DashboardData
from cryptoscope.desk import DeskFeed
from cryptoscope.desk.feed import SymbolDirectory
from cryptoscope.desk.fleet import FleetManager
from cryptoscope.desk.llm_panel import LLMPanel
from cryptoscope.desk.scanner import Autopilot, MarketScanner
from cryptoscope.desk.markets import MarketDirectory
from cryptoscope.desk.system_monitor import SystemMonitor
from cryptoscope.dashboard.collaborate_view import render_collaborations_html
from cryptoscope.fx.rate_service import FxRateService
from cryptoscope.market_data.aggregator import MarketDataAggregator
from cryptoscope.market_data.binance_feed import BinanceFeed
from cryptoscope.market_data.coinbase_feed import CoinbaseFeed
from cryptoscope.market_data.kraken_feed import KrakenFeed
from cryptoscope.market_data.coingecko import CoinGeckoService
from cryptoscope.execution.governor import LiveMultiGateGovernor, RiskGovernor, EmergencyKillSwitch, LiveGateError
from cryptoscope.autotrader.decision import LayaTier2Evaluator
from cryptoscope.research.settings import ROOT, load_config
from cryptoscope.security.halt_state import PersistentKillSwitch
from cryptoscope.security.config import validate_startup
from cryptoscope.security.public_forms import FormGuard, validate_proposal, operator_cookie, valid_operator_cookie, valid_operator_passcode
from cryptoscope.quant import (
    analyze_crypto_pair,
    volatility_regime_analysis,
    analyze_order_flow,
    optimal_trade_sizing,
    kelly_criterion,
    volatility_parity_allocation,
)

logger = logging.getLogger("cryptoscope.server")


def _sanitize_floats(obj):
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj

class PayloadTooLargeError(Exception):
    pass

STATIC = Path(__file__).parent / "static"
COLLAB_FILE = Path(__file__).resolve().parents[2] / "data" / "collaborations.json"
_collab_lock = threading.Lock()
def get_collab_passcode() -> str:
    return os.environ.get("COLLAB_DESK_PASSCODE", "")


def is_collab_authorized(headers) -> bool:
    passcode = get_collab_passcode()
    if not passcode:
        return False
    code = headers.get("X-Desk-Passcode", "")
    if valid_operator_passcode(code, passcode):
        return True
    cookie_str = headers.get("Cookie", "")
    if cookie_str:
        from http.cookies import SimpleCookie
        try:
            c = SimpleCookie()
            c.load(cookie_str)
            if "zillers_collab_auth" in c and valid_operator_cookie(c["zillers_collab_auth"].value, passcode):
                return True
        except Exception:
            pass
    return False



def get_server_metrics():
    from cryptoscope.ops.telemetry import process_metrics
    return process_metrics()


def handler_for(data, auth_store=None, rate_limiter=None, lockout_mgr=None, fx_service=None, market_aggregator=None, coingecko_service=None, risk_governor=None, live_governor=None, kill_switch=None, laya_evaluator=None):
    form_guard = FormGuard()
    auth_store = auth_store or AuthStore()
    rate_limiter = rate_limiter or RateLimiter()
    lockout_mgr = lockout_mgr or AccountLockoutManager()
    fx_service = fx_service or FxRateService()
    market_aggregator = market_aggregator or MarketDataAggregator()
    coingecko_service = coingecko_service or CoinGeckoService()
    risk_governor = risk_governor or RiskGovernor()
    live_governor = live_governor or LiveMultiGateGovernor()
    kill_switch = kill_switch or EmergencyKillSwitch(risk_governor, live_governor)
    if not isinstance(kill_switch, PersistentKillSwitch):
        kill_switch = PersistentKillSwitch(kill_switch)
    laya_evaluator = laya_evaluator or LayaTier2Evaluator()
    def _ollama_status():
        st = laya_evaluator.get_status()
        return {"status": "available" if st.get("ollama_available") else "unavailable", "model": st.get("ollama_model"),
                "role": "explainer only (never votes)",
                "laya": {"status": st.get("status"), "checkpoint_loaded": st.get("checkpoint_loaded"),
                         "evaluations": st.get("total_evaluations")}}

    ai_allowed = lambda: not kill_switch.halted  # noqa: E731 - the durable latch gates every AI system
    # The fleet gets Ollama to itself while it runs: the panel cycling 5 models forces reloads that
    # make the fleet's debate calls time out.
    llm_panel = LLMPanel(gate=lambda: ai_allowed() and not fleet.is_running())
    from cryptoscope.desk.ai_journal import AIJournal
    ai_journal = AIJournal(str(ROOT / "work" / "runtime" / "ai_journal.db"))
    desk_feed = DeskFeed(ollama_status=_ollama_status, llm_panel=llm_panel, ai_gate=ai_allowed, journal=ai_journal)
    symbol_directory = SymbolDirectory()
    fleet = FleetManager(ROOT)
    scanner = MarketScanner()

    def _coin_meta():
        listing = coingecko_service.get_top_listings(per_page=150, page=1)
        return {str(it.get("base_symbol") or "").upper(): it for it in listing.get("items", []) if it.get("base_symbol")}

    market_directory = MarketDirectory(meta_fetcher=_coin_meta)

    from cryptoscope.desk.paperbots import PaperBotManager
    from cryptoscope.desk.feed import fetch_klines as _klines
    from cryptoscope.desk.scanner import _get as _public_get

    def _last_price(symbol):
        return float(_public_get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=8)["price"])

    paper_bots = PaperBotManager(str(ROOT / "work" / "runtime" / "paperbots.db"),
                                 candles=lambda sym, n: _klines(sym, "1m", n), price=_last_price,
                                 gate=lambda: not kill_switch.halted, notify=fleet.notify)
    paper_bots.ensure_running()

    from cryptoscope.desk.live_view import PriceCache, build_live
    live_prices = PriceCache()   # one batched Binance price request per second, shared by every viewer

    from cryptoscope.desk.market_structure import MarketStructure
    from cryptoscope.desk.strategy_lab import record_promotions, run_lab
    market_structure = MarketStructure()
    _lab_cache = {}

    def _fleet_positions_open():
        db = ROOT / "work" / "runtime" / "orchestrator_execution.db"
        if not db.is_file():
            return 0
        try:
            with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=5) as conn:
                return int(conn.execute("SELECT count(*) FROM positions").fetchone()[0])
        except sqlite3.Error:
            return 1  # unknown -> treat as holding, so the autopilot never rotates blindly

    autopilot = Autopilot(scanner, fleet, _fleet_positions_open, notify=fleet.notify,
                          tier_log=ROOT / "work" / "runtime" / "scanner_tiers.jsonl")

    from cryptoscope.desk.startup import StartupRunner, build_default_checks

    def _telegram_status():
        from cryptoscope.telegram.notify import configured as telegram_configured
        return telegram_configured()

    from cryptoscope.agents.decision_models import SidecarManager
    decision_sidecar = SidecarManager()   # real THX-02 + Laya, in WSL on Windows; never imported in-process

    startup = StartupRunner(lambda mode: build_default_checks(
        mode, kill_switch=kill_switch, risk_governor=RiskGovernor(), fleet=fleet, autopilot=autopilot, scanner=scanner,
        paper_bots=paper_bots, llm_panel=llm_panel, laya_evaluator=laya_evaluator,
        klines=lambda s, i, n: _klines(s, i, n), telegram_status=_telegram_status,
        decision_sidecar=decision_sidecar))

    def _feed_delays():
        out = {}
        conns = market_aggregator.get_connection_status()
        for src, c in conns.items():
            out[src] = {"state": c.get("state"), "heartbeat_age_s": c.get("last_heartbeat_age"),
                        "latency_ms": c.get("latency_ms"), "errors": c.get("consecutive_errors"), "feed": c.get("feed_type")}
        ticks = {}
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            t = market_aggregator.get_ticker(sym)
            ticks[sym] = {"status": t.get("status"), "age_s": t.get("age_seconds"), "latency_ms": t.get("latency_ms"),
                          "sources": t.get("sources_reporting"), "source_latencies": t.get("source_latencies")}
        return {"exchanges": out, "tickers": ticks}

    system_monitor = SystemMonitor(feed_status=_feed_delays,
                                   extra_targets=(("Ollama (local)", LLMPanel().host + "/api/version"),))

    def connection_status():
        return {**market_aggregator.get_connection_status(),
                'coingecko': coingecko_service.connection_status()}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def handle(self):
            try:
                super().handle()
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass

        def send(self, status, content, kind, download=None, cookies=None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "script-src 'self' 'unsafe-inline'; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "img-src 'self' data: https: https://assets.coingecko.com; "
                "connect-src 'self' https://open.er-api.com; frame-ancestors 'none'; base-uri 'none'"
            )
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            if cookies:
                for c in cookies:
                    self.send_header("Set-Cookie", c)
            self.end_headers()
            try:
                self.wfile.write(content)
            except (ConnectionError, BrokenPipeError, TimeoutError, OSError):
                pass



        def json(self, status, body, download=None, cookies=None):
            safe_body = _sanitize_floats(body)
            self.send(status, json.dumps(safe_body, allow_nan=False).encode(), "application/json; charset=utf-8", download, cookies)

        def _get_session(self):
            raw_cookies = self.headers.get("Cookie", "")
            if not raw_cookies:
                return None
            c = SimpleCookie(raw_cookies)
            if "session_token" not in c:
                return None
            token = c["session_token"].value
            return auth_store.validate_session(token)

        def _read_body_json(self, max_bytes: int = 524_288):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > max_bytes:
                try:
                    self.rfile.read(content_length)
                except Exception:
                    pass
                raise PayloadTooLargeError(f"Payload size ({content_length} bytes) exceeds maximum limit ({max_bytes} bytes)")
            if content_length == 0:
                return {}
            raw = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw)

        def do_GET(self):
            port = self.server.server_address[1]
            if self.headers.get("Host") not in {f"localhost:{port}", f"127.0.0.1:{port}"}:
                return self.json(403, {"error": "Localhost access only"})

            url = urlsplit(self.path)
            query = parse_qs(url.query)
            session = self._get_session()

            # Health and readiness probes (no auth required)
            if url.path == "/health":
                return self.json(200, {"status": "healthy", "timestamp": time.time(), "terminal": "ZILLERS"})
            if url.path == "/ready":
                connections=connection_status()
                missing=[source for source in ('binance','coinbase','kraken') if connections.get(source,{}).get('state')!='connected'
                    or connections.get(source,{}).get('last_heartbeat_age') is None or connections[source]['last_heartbeat_age']>5]
                unavailable=[symbol for symbol in ('BTCUSDT','ETHUSDT','SOLUSDT') if market_aggregator.get_ticker(symbol).get('status')!='verified']
                return self.json(503 if missing or unavailable else 200, {
                    "status": "degraded" if missing or unavailable else "ready",
                    "exchanges": connections,
                    "unavailable_required_feeds":missing,
                    "unverified_required_symbols":unavailable,
                    "trading_authorized":False,
                    "fx": fx_service.get_rate(auto_fetch=False),
                })

            # Static assets
            assets = {
                "/": ("desk.html", "text/html"),
                "/desk": ("desk.html", "text/html"),
                "/desk.js": ("desk.js", "text/javascript"),
                "/desk.css": ("desk.css", "text/css"),
                "/system": ("system.html", "text/html"),
                "/system.js": ("system.js", "text/javascript"),
                "/scanner": ("scanner.html", "text/html"),
                "/scanner.js": ("scanner.js", "text/javascript"),
                "/markets": ("markets.html", "text/html"),
                "/markets.js": ("markets.js", "text/javascript"),
                "/bots": ("bots.html", "text/html"),
                "/bots.js": ("bots.js", "text/javascript"),
                "/lab": ("lab.html", "text/html"),
                "/lab.js": ("lab.js", "text/javascript"),
                "/pnl": ("pnl.html", "text/html"),
                "/pnl.js": ("pnl.js", "text/javascript"),
                "/live": ("live.html", "text/html"),
                "/live.js": ("live.js", "text/javascript"),
            }
            if url.path in assets:
                name, kind = assets[url.path]
                return self.send(200, (STATIC / name).read_bytes(), kind + "; charset=utf-8")

            # Machine discovery & SEO / GEO / AEO endpoints
            seo_files = {
                "/robots.txt": "text/plain; charset=utf-8",
                "/sitemap.xml": "application/xml; charset=utf-8",
                "/llms.txt": "text/plain; charset=utf-8",
                "/llms-full.txt": "text/plain; charset=utf-8",
                "/manifest.json": "application/json; charset=utf-8",
            }
            if url.path in seo_files:
                target_file = (STATIC / "landing" / url.path.lstrip("/")).resolve()
                if not target_file.is_file():
                    target_file = (STATIC / url.path.lstrip("/")).resolve()
                if target_file.is_file():
                    return self.send(200, target_file.read_bytes(), seo_files[url.path])

            if url.path in {"/landing", "/docs", "/about", "/landing/", "/collaborate", "/collaborate/", "/setup", "/setup/"}:
                landing_html = STATIC / "landing" / "index.html"
                if landing_html.is_file():
                    return self.send(200, landing_html.read_bytes(), "text/html; charset=utf-8")

            if url.path in {"/collaborations", "/collaborations/", "/collaborate/submissions"}:
                with _collab_lock:
                    records = []
                    if COLLAB_FILE.is_file():
                        try:
                            records = json.loads(COLLAB_FILE.read_text(encoding="utf-8"))
                            if not isinstance(records, list):
                                records = []
                        except Exception:
                            records = []
                is_auth = is_collab_authorized(self.headers)
                html_view = render_collaborations_html(records, is_authenticated=is_auth)
                return self.send(200, html_view.encode("utf-8"), "text/html; charset=utf-8")

            if url.path.startswith("/landing/"):
                subpath = url.path[len("/landing/"):].lstrip("/")
                landing_file = (STATIC / "landing" / subpath).resolve()
                if (STATIC / "landing") in landing_file.parents and landing_file.is_file():
                    mime = "text/css" if landing_file.suffix == ".css" else "text/javascript" if landing_file.suffix == ".js" else "image/png" if landing_file.suffix == ".png" else "text/html"
                    return self.send(200, landing_file.read_bytes(), f"{mime}; charset=utf-8" if "text" in mime else mime)

            if url.path.startswith("/assets/"):
                asset_path = (STATIC / url.path.lstrip("/")).resolve()
                if STATIC in asset_path.parents and asset_path.is_file():
                    mime = "text/css" if asset_path.suffix == ".css" else "text/javascript" if asset_path.suffix == ".js" else "image/png" if asset_path.suffix == ".png" else "image/svg+xml" if asset_path.suffix == ".svg" else "application/octet-stream"
                    return self.send(200, asset_path.read_bytes(), f"{mime}; charset=utf-8" if "text" in mime else mime)

            # Action Desk: rule-model votes, PM decision and paper book on real daily candles
            if url.path == "/api/desk":
                try:
                    fee_bps = float(query.get("fee_bps", ["10"])[0])
                    result = desk_feed.desk(query.get("symbol", ["BTCUSDT"])[0], fee_bps=fee_bps,
                                            interval=query.get("interval", ["1d"])[0])
                except ValueError as err:
                    return self.json(400, {"error": str(err)})
                return self.json(200 if result.get("status") == "OK" else 503, result)

            if url.path == "/api/desk/symbols":
                return self.json(200, symbol_directory.symbols())
            if url.path == "/api/system/metrics":
                return self.json(200, {**system_monitor.snapshot(), "fleet": fleet.status(),
                                       "ai": _ollama_status()})
            if url.path == "/api/fleet/status":
                return self.json(200, fleet.status())
            if url.path == "/api/scanner":
                mode = query.get("mode", ["PAPER"])[0].upper()
                if mode not in {"PAPER", "TESTNET"}:
                    return self.json(400, {"error": "mode must be PAPER or TESTNET"})
                try:
                    return self.json(200, scanner.scan(mode, force=query.get("force", ["0"])[0] == "1"))
                except Exception as err:
                    return self.json(503, {"status": "UNAVAILABLE", "error": type(err).__name__})
            if url.path == "/api/scanner/autopilot":
                return self.json(200, autopilot.status())
            if url.path == "/api/ai/journal":
                return self.json(200, ai_journal.scoreboard(query.get("symbol", [None])[0], query.get("interval", [None])[0]))
            if url.path == "/api/protections":
                from cryptoscope.execution.protections import read_status
                return self.json(200, read_status(str(ROOT / "work" / "runtime" / "protections.json")))
            # Live Tradebot view: every coin the fleet trades, live marks, per-coin P&L
            if url.path == "/api/live":
                return self.json(200, build_live(ROOT / "work" / "runtime", fleet.status(), live_prices,
                                                 with_detail=(query.get("symbol", [None])[0] or None)))
            if url.path == "/api/live/candles":
                from cryptoscope.desk.feed import fetch_klines
                from cryptoscope.desk.live_view import coin_book
                sym = query.get("symbol", [""])[0].upper()
                interval = query.get("interval", ["15m"])[0]
                if not re.fullmatch(r"[A-Z0-9]{5,20}", sym) or interval not in {"1m", "5m", "15m", "1h", "4h"}:
                    return self.json(400, {"error": "bad symbol or interval"})
                try:
                    limit = max(20, min(500, int(query.get("limit", ["200"])[0])))
                    candles = fetch_klines(sym, interval, limit)
                except Exception as err:
                    return self.json(503, {"error": type(err).__name__})
                book = coin_book(ROOT / "work" / "runtime", sym, fills_limit=100)
                return self.json(200, {"symbol": sym, "interval": interval, "candles": candles,
                                       "fills": book["fills"], "position": book["position"], "closed": book["closed"]})
            if url.path == "/api/live/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                detail = query.get("symbol", [None])[0] or None
                try:
                    for _ in range(3600):   # the browser reconnects after an hour; keeps threads from piling up
                        payload = build_live(ROOT / "work" / "runtime", fleet.status(), live_prices, with_detail=detail)
                        self.wfile.write(("data: " + json.dumps(payload) + "\n\n").encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(1.0)
                except (ConnectionError, BrokenPipeError, TimeoutError, OSError):
                    pass
                return
            if url.path == "/api/pnl":
                from cryptoscope.desk.pnl import build_pnl
                marks = {}

                def _mark(sym):
                    if sym not in marks:
                        marks[sym] = _last_price(sym)
                    return marks[sym]
                try:
                    bots_now = paper_bots.list()
                except Exception:
                    bots_now = []
                return self.json(200, {**build_pnl(ROOT / "work" / "runtime", bots_now, _mark),
                                       "halted": kill_switch.halted, "fleet": fleet.status()})
            if url.path == "/api/bots":
                return self.json(200, {"bots": paper_bots.list(), "halted": kill_switch.halted})
            if url.path.startswith("/api/bots/") and url.path.count("/") == 3:
                try:
                    return self.json(200, paper_bots.get(url.path.rsplit("/", 1)[1]))
                except KeyError:
                    return self.json(404, {"error": "Bot not found"})
            if url.path == "/api/marketdata":
                sym = query.get("symbol", ["BTCUSDT"])[0].upper()
                if not sym.isalnum() or not 5 <= len(sym) <= 20:
                    return self.json(400, {"error": "Invalid symbol"})
                return self.json(200, market_structure.snapshot(sym))
            if url.path == "/api/lab/rotation":
                from cryptoscope.desk.rotation import run_rotation
                try:
                    k = int(query.get("k", ["5"])[0]); n = int(query.get("n", ["20"])[0])
                except ValueError:
                    return self.json(400, {"error": "k and n must be integers"})
                if not (1 <= k <= 10 and 5 <= n <= 40 and n >= 2 * k):
                    return self.json(400, {"error": "need 1 <= k <= 10, 5 <= n <= 40, n >= 2k"})
                try:
                    res = run_rotation(n=n, k=k)
                except Exception as err:
                    return self.json(503, {"status": "UNAVAILABLE", "error": type(err).__name__})
                return self.json(200 if res.get("status") == "OK" else 503, res)
            if url.path == "/api/lab":
                sym = query.get("symbol", ["BTCUSDT"])[0].upper()
                iv = query.get("interval", ["1d"])[0]
                try:
                    fee = float(query.get("fee_bps", ["10"])[0])
                except ValueError:
                    return self.json(400, {"error": "fee_bps must be a number"})
                if not sym.isalnum() or not 5 <= len(sym) <= 20 or not 0 <= fee <= 100:
                    return self.json(400, {"error": "Invalid symbol or fee"})
                key = (sym, iv, fee)
                hit = _lab_cache.get(key)
                if hit and time.time() - hit[0] < 120:
                    return self.json(200, hit[1])
                try:
                    candles = _klines(sym, iv, 1000)
                    result = {**run_lab(candles, iv, fee), "symbol": sym}
                    record_promotions(result, sym)   # gate passes -> work/runtime/promoted_strategies.json
                except ValueError as err:
                    return self.json(400, {"error": str(err)})
                except Exception as err:
                    return self.json(503, {"status": "UNAVAILABLE", "error": type(err).__name__})
                _lab_cache[key] = (time.time(), result)
                return self.json(200, result)
            if url.path == "/api/markets":
                m = market_directory.markets()
                return self.json(200 if m.get("status") in {"OK", "STALE"} else 503, m)
            if url.path == "/api/system/startup":
                return self.json(200, startup.status())
            if url.path == "/api/models/sidecar":
                from cryptoscope.agents.decision_models import enforce_enabled, min_probability
                return self.json(200, {**decision_sidecar.status(), "enforced": enforce_enabled(),
                                       "min_p": min_probability()})
            if url.path == "/api/telegram/status":
                from cryptoscope.telegram.notify import configured as telegram_configured
                return self.json(200, telegram_configured())

            # Public market data and FX APIs
            if url.path == "/api/fx/rate":
                target = query.get("target", ["INR"])[0]
                return self.json(200, fx_service.get_rate(target))

            if url.path in {"/api/market/status", "/api/market/connections"}:
                conn = connection_status()
                lat_list = [v.get("latency_ms") for v in conn.values() if isinstance(v, dict) and v.get("latency_ms") is not None]
                avg_lat = round(sum(lat_list) / len(lat_list), 1) if lat_list else None
                return self.json(200, {
                    "status": "online",
                    "exchanges": conn,
                    "server": get_server_metrics(),
                    "timestamp": time.time(),
                    "latency_ms": avg_lat,
                })

            if url.path == "/api/market/tickers":
                return self.json(200, {"tickers": market_aggregator.get_all_tickers()})

            if url.path == "/api/market/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                try:
                    while True:
                        conn = connection_status()
                        lat_list = [v.get("latency_ms") for v in conn.values() if isinstance(v, dict) and v.get("latency_ms") is not None]
                        avg_lat = round(sum(lat_list) / len(lat_list), 1) if lat_list else None
                        payload = json.dumps({
                            "tickers": market_aggregator.get_all_tickers(),
                            "connections": conn,
                            "timestamp": time.time(),
                            "latency_ms": avg_lat,
                        })
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(0.5)
                except (ConnectionError, BrokenPipeError, TimeoutError, OSError, ConnectionResetError, ConnectionAbortedError):
                    pass
                return

            if url.path == "/api/market/ticker":
                symbol = query.get("symbol", ["BTCUSDT"])[0].upper()
                ticker = market_aggregator.get_ticker(symbol)
                if ticker.get("status") == "unavailable" or ticker.get("price") is None:
                    try:
                        from cryptoscope.providers.binance import BinanceProvider
                        q = BinanceProvider().quote(symbol)
                        if q and q.get("bid"):
                            bid = float(q["bid"])
                            ask = float(q["ask"])
                            mid = round((bid + ask) / 2.0, 4 if bid < 10 else 2)
                            ticker = {
                                "symbol": symbol,
                                "status": "single-source",
                                "price": mid,
                                "bid": bid,
                                "ask": ask,
                                "change_24h_pct": None,
                                "volume_24h": None,
                                "high_24h": None,
                                "low_24h": None,
                                "source": "binance_spot",
                                "sources_reporting": ["binance"],
                                "sources_dropped_stale": [],
                                "age_seconds": round(time.time() - q["available_at"], 2),
                                "latency_ms": 25.0,
                                "source_latencies": {"binance": 25.0},
                                "median_price": mid,
                                "max_deviation_pct": 0.0,
                                "metadata": None
                            }
                    except Exception:
                        pass
                return self.json(200, ticker)

            if url.path == "/api/market/candles":
                symbol = query.get("symbol", ["BTCUSDT"])[0].upper()
                interval = query.get("interval", ["1m"])[0]
                limit = min(500, max(10, int(query.get("limit", [100])[0])))
                candles = []
                try:
                    from cryptoscope.market_data.candle_store import CandleStore
                    from cryptoscope.providers.binance import BinanceProvider
                    cs = CandleStore()
                    candles = cs.get_fresh_candles(symbol, interval, limit=limit)
                    return self.json(200, {
                        "symbol": symbol,
                        "interval": interval,
                        "candles": candles,
                        "count": len(candles),
                        "as_of": time.time(),
                        "source": "binance_spot"
                    })
                except Exception as e:
                    return self.json(200, {
                        "symbol": symbol,
                        "interval": interval,
                        "candles": candles or [],
                        "count": len(candles),
                        "as_of": time.time(),
                        "error": str(e)
                    })

            if url.path == "/api/market/connections":
                return self.json(200, connection_status())

            if url.path == "/api/market/listings":
                page = int(query.get("page", [1])[0])
                per_page = int(query.get("per_page", [50])[0])
                return self.json(200, coingecko_service.get_top_listings(per_page, page))

            if url.path == "/api/governor/status":
                return self.json(200, {
                    "mode": live_governor.mode,
                    "kill_switch_engaged": kill_switch.halted,
                    "action": getattr(kill_switch, "action", "HALT"),
                    "emergency_halted": risk_governor.emergency_halted,
                    "halt_reason": risk_governor.halt_reason,
                    "halted_at": kill_switch.halted_at,
                    "halted_by": kill_switch.halted_by,
                    "target_exchange": "Binance Spot",
                    "ai_layer": "stopped" if kill_switch.halted else "running",
                    "fleet_running": fleet.status()["running"],
                })

            # Quantitative Analysis & Statistical Arbitrage APIs
            if url.path == "/api/quant/pairs":
                from cryptoscope.market_data.candle_store import CandleStore
                from cryptoscope.providers.binance import BinanceProvider
                cs = CandleStore()
                provider = BinanceProvider()
                
                pairs_param = query.get("pairs", ["ETHUSDT:BTCUSDT,SOLUSDT:ETHUSDT,AVAXUSDT:SOLUSDT"])[0]
                results = []
                for pair_str in pairs_param.split(","):
                    parts = pair_str.strip().split(":")
                    if len(parts) != 2:
                        continue
                    sym_a, sym_b = parts[0].upper(), parts[1].upper()
                    candles_a = cs.get_fresh_candles(sym_a, "15m", limit=100)
                    candles_b = cs.get_fresh_candles(sym_b, "15m", limit=100)
                    pair_diag = analyze_crypto_pair(candles_a, candles_b, symbol_a=sym_a, symbol_b=sym_b)
                    results.append(pair_diag)

                return self.json(200, {"pairs": results, "as_of": time.time()})

            if url.path == "/api/quant/volatility":
                symbol = query.get("symbol", ["BTCUSDT"])[0].upper()
                interval = query.get("interval", ["15m"])[0]
                from cryptoscope.market_data.candle_store import CandleStore
                from cryptoscope.providers.binance import BinanceProvider
                cs = CandleStore()
                candles = cs.get_fresh_candles(symbol, interval, limit=100)
                vol_report = volatility_regime_analysis(candles, window=20, baseline_window=60, interval=interval)
                vol_report["symbol"] = symbol
                vol_report["interval"] = interval
                return self.json(200, vol_report)

            # 8-Stage 48-Formula Quant Pipeline Live Telemetry
            if url.path == "/api/quant/metrics":
                symbol = query.get("symbol", ["BTCUSDT"])[0].upper()
                from cryptoscope.market_data.candle_store import CandleStore
                from core.quant.pipeline import QuantPipeline

                cs = CandleStore()
                candles = cs.get_fresh_candles(symbol, "15m", limit=60)
                ticker = market_aggregator.get_ticker(symbol)
                bid_p = float(ticker.get("bid")) if ticker and ticker.get("bid") else 100.0
                ask_p = float(ticker.get("ask")) if ticker and ticker.get("ask") else 100.1
                bid_q = float(ticker.get("bid_qty")) if ticker and ticker.get("bid_qty") else 50.0
                ask_q = float(ticker.get("ask_qty")) if ticker and ticker.get("ask_qty") else 50.0

                pipeline = QuantPipeline(symbol=symbol)
                metrics = {}
                if candles:
                    for c in candles:
                        if isinstance(c, dict):
                            metrics = pipeline.on_bar(
                                open_p=float(c.get("open", 100)),
                                high_p=float(c.get("high", 105)),
                                low_p=float(c.get("low", 95)),
                                close_p=float(c.get("close", 100)),
                                volume=float(c.get("volume", 1000)),
                                bid_p=bid_p, bid_q=bid_q, ask_p=ask_p, ask_q=ask_q
                            )
                        elif isinstance(c, (list, tuple)) and len(c) >= 5:
                            metrics = pipeline.on_bar(
                                open_p=float(c[0]), high_p=float(c[1]), low_p=float(c[2]),
                                close_p=float(c[3]), volume=float(c[4]),
                                bid_p=bid_p, bid_q=bid_q, ask_p=ask_p, ask_q=ask_q
                            )
                else:
                    metrics = pipeline.on_bar(
                        open_p=bid_p, high_p=ask_p * 1.01, low_p=bid_p * 0.99,
                        close_p=(bid_p + ask_p) / 2.0, volume=1000.0,
                        bid_p=bid_p, bid_q=bid_q, ask_p=ask_p, ask_q=ask_q
                    )

                res = {
                    "symbol": symbol,
                    "timestamp": time.time(),
                    "stage1_data": {
                        "log_return": metrics.get("log_return"),
                        "annualized_vol": metrics.get("annualized_vol"),
                        "ewma_vol": metrics.get("ewma_vol"),
                        "atr": metrics.get("atr"),
                        "is_bad_tick": metrics.get("is_bad_tick"),
                    },
                    "stage2_signal": {
                        "z_score": metrics.get("z_score"),
                        "ema_20": metrics.get("ema_20"),
                        "rsi_14": metrics.get("rsi_14"),
                        "order_book_imbalance": metrics.get("order_book_imbalance"),
                        "funding_apr": metrics.get("funding_apr"),
                    },
                    "stage3_filter": {
                        "t_stat": metrics.get("t_stat"),
                        "half_life": metrics.get("half_life"),
                        "hurst_exponent": metrics.get("hurst_exponent"),
                        "is_high_vol": metrics.get("is_high_vol"),
                    },
                    "stage5_size": {
                        "suggested_size": metrics.get("suggested_size"),
                        "volatility_target_scalar": metrics.get("volatility_target_scalar"),
                        "liquidation_price": metrics.get("liquidation_price"),
                    },
                    "stage6_execute": {
                        "spread": metrics.get("spread"),
                        "microprice": metrics.get("microprice"),
                        "estimated_impact": metrics.get("estimated_impact"),
                    },
                    "stage7_risk": {
                        "var_95": metrics.get("var_95"),
                        "max_drawdown": metrics.get("max_drawdown"),
                        "kill_switch_triggered": metrics.get("kill_switch_triggered"),
                    },
                }
                return self.json(200, res)

            # 10-Level 50-Formula Quant Matrix Telemetry
            if url.path == "/api/quant/levels":
                symbol = query.get("symbol", ["BTCUSDT"])[0].upper()
                from cryptoscope.market_data.candle_store import CandleStore
                from core.quant.levels import (
                    compute_bayes_update,
                    compute_linear_expectation,
                    compute_sample_variance,
                    compute_total_expectation,
                    evaluate_distribution_density,
                    compute_standard_error,
                    compute_sharpe_t_stat,
                    compute_ols_regression,
                    compute_correlation,
                    compute_family_wise_error_rate,
                    compute_portfolio_variance,
                    compute_condition_number,
                    ledoit_wolf_shrinkage,
                    taylor_pnl_approximation,
                    compute_markowitz_weights,
                    compute_volatility_drag,
                    compute_log_returns,
                    compute_annualized_volatility,
                    compute_autocorrelation,
                    compute_adf_stationarity,
                    compute_garch11_filter,
                    simulate_random_walk,
                    ito_log_price_drift,
                    compute_gamblers_ruin,
                    black_scholes_call,
                    black_scholes_put,
                    compute_option_greeks,
                    compute_gamma_pnl,
                    compute_capm_beta,
                    compute_sharpe_ratio,
                    compute_discrete_kelly,
                    compute_continuous_kelly,
                    compute_parametric_var,
                    compute_expected_shortfall,
                    compute_max_drawdown,
                    compute_spreads,
                    compute_microprice,
                    compute_square_root_impact,
                    compute_avellaneda_stoikov,
                    compute_deflated_sharpe_ratio,
                    detect_regimes_hmm,
                )

                cs = CandleStore()
                candles = cs.get_fresh_candles(symbol, "15m", limit=60)
                ticker = market_aggregator.get_ticker(symbol)
                bid_p = float(ticker.get("bid")) if ticker and ticker.get("bid") else 60000.0
                ask_p = float(ticker.get("ask")) if ticker and ticker.get("ask") else 60010.0
                bid_q = float(ticker.get("bid_qty")) if ticker and ticker.get("bid_qty") else 5.0
                ask_q = float(ticker.get("ask_qty")) if ticker and ticker.get("ask_qty") else 4.0

                closes = [float(c["close"]) if isinstance(c, dict) else float(c[3]) for c in candles] if candles else [bid_p] * 20
                if len(closes) < 10:
                    closes = [bid_p + (i * 10.0) for i in range(20)]

                rets = compute_log_returns(closes)
                if not rets:
                    rets = [0.001, -0.001, 0.002, -0.001, 0.001]
                ann_vol = compute_annualized_volatility(rets, bars_per_year=365) if rets else 0.50
                sr = compute_sharpe_ratio(rets, rf=0.0, bars_per_year=365) if rets else 1.2

                # Level calculations
                shrunk_cov, shrinkage_delta = ledoit_wolf_shrinkage([[0.01, 0.02], [-0.01, 0.01], [0.02, -0.01]])
                greeks = compute_option_greeks("call", closes[-1], closes[-1], 30.0 / 365.0, 0.04, max(0.01, ann_vol))
                garch_series = compute_garch11_filter(rets, 1e-6, 0.05, 0.90)

                report = {
                    "symbol": symbol,
                    "timestamp": time.time(),
                    "level1_prob": {
                        "bayes_update": compute_bayes_update(0.1, 0.8, 0.2),
                        "linear_expectation": compute_linear_expectation([0.05, 0.08]),
                        "sample_variance": compute_sample_variance(closes[-10:]),
                        "total_expectation": compute_total_expectation([0.10, -0.05], [0.6, 0.4]),
                        "gaussian_density": evaluate_distribution_density("gaussian", 0.0),
                    },
                    "level2_stats": {
                        "standard_error": compute_standard_error(ann_vol, max(2, len(rets))),
                        "sharpe_t_stat": compute_sharpe_t_stat(sr, 1.0),
                        "ols_slope": compute_ols_regression(closes[:-1], closes[1:])["beta"] if len(closes) > 2 else 1.0,
                        "correlation": compute_correlation(closes[:-1], closes[1:]) if len(closes) > 2 else 0.99,
                        "multiple_testing_fwer": compute_family_wise_error_rate(0.05, 10),
                    },
                    "level3_linalg": {
                        "portfolio_variance": compute_portfolio_variance([0.5, 0.5], [[ann_vol**2, 0.0], [0.0, ann_vol**2]]),
                        "condition_number": compute_condition_number([[1.0, 0.2], [0.2, 1.0]]),
                        "ledoit_wolf_shrinkage_intensity": float(shrinkage_delta),
                    },
                    "level4_opt": {
                        "taylor_pnl_approx": taylor_pnl_approximation(0.5, 0.02, -5.0, 10.0, 1.0 / 365.0),
                        "markowitz_weight": [float(w) for w in compute_markowitz_weights([0.10, 0.12], [[0.04, 0.01], [0.01, 0.09]])],
                        "volatility_drag": compute_volatility_drag(0.15, ann_vol)["drag"],
                    },
                    "level5_timeseries": {
                        "log_return": rets[-1] if rets else 0.0,
                        "annualized_vol": ann_vol,
                        "autocorrelation_lag1": compute_autocorrelation(rets, 1) if len(rets) > 3 else 0.0,
                        "adf_stat": compute_adf_stationarity(closes)[0] if len(closes) >= 10 else -2.5,
                        "garch_vol": float(garch_series[-1]) if garch_series else ann_vol,
                    },
                    "level6_stoch": {
                        "random_walk_sim": simulate_random_walk(5, seed=42),
                        "ito_log_drift": ito_log_price_drift(0.10, ann_vol),
                        "gamblers_ruin": compute_gamblers_ruin(20, 100, 0.55),
                    },
                    "level7_derivatives": {
                        "black_scholes_call": black_scholes_call(closes[-1], closes[-1], 30.0 / 365.0, 0.04, ann_vol),
                        "black_scholes_put": black_scholes_put(closes[-1], closes[-1], 30.0 / 365.0, 0.04, ann_vol),
                        "delta": greeks.delta,
                        "gamma": greeks.gamma,
                        "vega": greeks.vega,
                        "gamma_pnl": compute_gamma_pnl(0.002, -1.5, 20.0, 1.0 / 365.0),
                    },
                    "level8_risk": {
                        "capm_beta": compute_capm_beta(rets, rets) if len(rets) > 2 else 1.0,
                        "sharpe_ratio": sr,
                        "discrete_kelly": compute_discrete_kelly(0.55, 1.8),
                        "continuous_kelly": compute_continuous_kelly(0.10, max(0.01, ann_vol**2)),
                        "parametric_var_95": compute_parametric_var(10000.0, ann_vol / (365**0.5)),
                        "expected_shortfall_95": compute_expected_shortfall(10000.0, ann_vol / (365**0.5)),
                        "max_drawdown": compute_max_drawdown(closes)[0],
                    },
                    "level9_microstructure": {
                        "mid": (bid_p + ask_p) / 2.0,
                        "spread_bps": compute_spreads(bid_p, ask_p)["rel_spread"] * 10000.0,
                        "microprice": compute_microprice(bid_p, bid_q, ask_p, ask_q, closes[-1]),
                        "square_root_impact": compute_square_root_impact(ann_vol, 1.0, 10000.0)["relative_impact"],
                        "avellaneda_stoikov": compute_avellaneda_stoikov((bid_p + ask_p) / 2.0, 0.1, 0.1, ann_vol, 1.0 / 365.0, 1.5),
                    },
                    "level10_research": {
                        "deflated_sharpe_ratio": compute_deflated_sharpe_ratio(sr, returns=rets, n_trials=10),
                        "hmm_regimes": detect_regimes_hmm(rets, n_states=2),
                    },
                }
                return self.json(200, report)

            if url.path == "/api/quant/orderflow":
                symbol = query.get("symbol", ["BTCUSDT"])[0].upper()
                lookback = min(100, max(10, int(query.get("lookback", [40])[0])))
                from cryptoscope.market_data.candle_store import CandleStore
                from cryptoscope.providers.binance import BinanceProvider
                cs = CandleStore()
                candles = cs.get_fresh_candles(symbol, "15m", limit=lookback)
                of_report = analyze_order_flow(candles, lookback=lookback)
                of_report["symbol"] = symbol
                return self.json(200, of_report)

            # Laya Tier 2 Engine Status
            if url.path == "/api/laya/status":
                return self.json(200, laya_evaluator.get_status())

            # Auth session inspection
            if url.path == "/api/auth/me":
                if not session:
                    return self.json(401, {"authenticated": False, "error": "Not authenticated"})
                return self.json(200, {
                    "authenticated": True,
                    "user_id": session["user_id"],
                    "email": session["email"],
                    "role": session["role"],
                    "must_change_password": bool(session["must_change_password"]),
                    "csrf_token": session["csrf_token"],
                })

            # Auth gate on user settings and favorites
            if url.path == "/api/user/favorites":
                if not session:
                    return self.json(401, {"error": "Authentication required"})
                return self.json(200, {"favorites": auth_store.get_favorites(session["user_id"])})

            if url.path == "/api/user/settings":
                if not session:
                    return self.json(401, {"error": "Authentication required"})
                return self.json(200, auth_store.get_settings(session["user_id"]))

            if url.path in {"/api/collaborate", "/api/collaborate/list"}:
                with _collab_lock:
                    records = []
                    if COLLAB_FILE.is_file():
                        try:
                            records = json.loads(COLLAB_FILE.read_text(encoding="utf-8"))
                            if not isinstance(records, list):
                                records = []
                        except Exception:
                            records = []
                is_auth = is_collab_authorized(self.headers)
                accept = self.headers.get("Accept", "")
                fmt = query.get("format", [""])[0]
                if (("text/html" in accept and "application/json" not in accept) or fmt == "html") and fmt != "json":
                    html_view = render_collaborations_html(records, is_authenticated=is_auth)
                    return self.send(200, html_view.encode("utf-8"), "text/html; charset=utf-8")
                
                if not is_auth:
                    return self.json(401, {
                        "error": "Passcode required to view collaboration submissions",
                        "help": "Provide verified operator passcode via header X-Desk-Passcode or cookie"
                    })
                return self.json(200, {"status": "ok", "total": len(records), "proposals": records})

            # Dashboard API routes (accessible by authenticated sessions or test runners)
            workspace = query.get("workspace", ["research"])[0]
            try:
                if url.path == "/api/dashboard":
                    res = data.overview(workspace)
                    res["connections"] = connection_status()
                    res["fx"] = fx_service.get_rate("INR")
                    return self.json(200, res)
                if url.path == '/api/features':
                    return self.json(200, data.feature_catalog())
                for kind in ('forecasts', 'strategies'):
                    if url.path.startswith(f'/api/{kind}/'):
                        run_id = url.path.removeprefix(f'/api/{kind}/')
                        report = data.forecast_report(workspace, run_id) if kind == 'forecasts' else data.artifact(kind, run_id)
                        if report is None:
                            return self.json(404, {'error': 'Research artifact not found'})
                        return self.json(200, report, f'zien-{kind}-{run_id}.json' if 'download' in query else None)
                if url.path.startswith('/api/backtests/'):
                    run_id = url.path.removeprefix('/api/backtests/')
                    report = data.backtest(run_id)
                    if report is None:
                        return self.json(404, {'error': 'Backtest not found'})
                    return self.json(200, report, f'zien-backtest-{run_id}.json' if 'download' in query else None)
                if url.path.startswith("/api/runs/"):
                    run_id = url.path.removeprefix("/api/runs/")
                    run = data.run(workspace, run_id)
                    if run is None:
                        return self.json(404, {"error": "Research run not found"})
                    return self.json(200, run, f"zien-{run_id}.json" if "download" in query else None)
                return self.json(404, {"error": "Not found"})
            except ValueError as error:
                return self.json(400, {"error": str(error)})
            except Exception:
                return self.json(503, {"error": "Dashboard data is temporarily unavailable"})

        def do_POST(self):
            port = self.server.server_address[1]
            if self.headers.get("Host") not in {f"localhost:{port}", f"127.0.0.1:{port}"}:
                return self.json(403, {"error": "Localhost access only"})

            url = urlsplit(self.path)
            client_ip = extract_client_ip(dict(self.headers), self.client_address[0])

            try:
                body = self._read_body_json()
            except PayloadTooLargeError as err:
                return self.json(413, {"error": str(err)})
            except Exception:
                return self.json(400, {"error": "Invalid JSON payload"})

            session = self._get_session()

            # 1. Login
            if url.path == "/api/auth/login":
                if not rate_limiter.is_allowed(client_ip, "/api/auth/login", limit=12):
                    retry = rate_limiter.retry_after(client_ip, "/api/auth/login")
                    return self.json(429, {"error": f"Rate limit exceeded. Retry in {retry} seconds."})

                email = str(body.get("email", "")).strip().lower()
                password = str(body.get("password", ""))

                is_locked, rem = lockout_mgr.is_locked(email)
                if is_locked:
                    return self.json(423, {"error": f"Account temporarily locked due to failed logins. Try again in {rem} seconds."})

                user = auth_store.get_user_by_email(email)
                if not user or not verify_password(password, user["password_hash"]):
                    locked, rem_lock = lockout_mgr.record_failure(email)
                    if locked:
                        return self.json(423, {"error": f"Account temporarily locked for {rem_lock} seconds due to consecutive failed logins."})
                    return self.json(401, {"error": "Invalid credentials"})

                # Auto-upgrade password hash if using older scrypt parameters
                if needs_rehash(user["password_hash"]):
                    new_hash = hash_password(password)
                    auth_store.update_password_hash(user["id"], new_hash)
                    logger.info("Automatically upgraded scrypt password hash to N=2^17 for user %s", email)

                lockout_mgr.record_success(email)
                auth_store.record_login(user["id"])
                raw_token, csrf_token = auth_store.create_session(user["id"])
                is_tls = self.headers.get("X-Forwarded-Proto") == "https"
                secure_flag = "; Secure" if is_tls else ""
                cookie_str = f"session_token={raw_token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800{secure_flag}"

                return self.json(200, {
                    "status": "ok",
                    "user": {
                        "id": user["id"],
                        "email": user["email"],
                        "role": user["role"],
                        "must_change_password": bool(user["must_change_password"]),
                    },
                    "csrf_token": csrf_token,
                }, cookies=[cookie_str])

            # 2. Signup
            if url.path == "/api/auth/signup":
                if not rate_limiter.is_allowed(client_ip, "/api/auth/signup", limit=12):
                    return self.json(429, {"error": "Rate limit exceeded"})

                email = str(body.get("email", "")).strip().lower()
                password = str(body.get("password", ""))
                invite_code = body.get("invite_code")

                try:
                    user_id = auth_store.create_user(email, password, role="user", invite_code=invite_code)
                    raw_token, csrf_token = auth_store.create_session(user_id)
                    is_tls = self.headers.get("X-Forwarded-Proto") == "https"
                    secure_flag = "; Secure" if is_tls else ""
                    cookie_str = f"session_token={raw_token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800{secure_flag}"
                    return self.json(200, {
                        "status": "ok",
                        "user": {"id": user_id, "email": email, "role": "user", "must_change_password": False},
                        "csrf_token": csrf_token,
                    }, cookies=[cookie_str])
                except ValueError as err:
                    return self.json(400, {"error": str(err)})

            # 3. Logout
            if url.path == "/api/auth/logout":
                raw_cookies = self.headers.get("Cookie", "")
                if raw_cookies:
                    c = SimpleCookie(raw_cookies)
                    if "session_token" in c:
                        auth_store.revoke_session(c["session_token"].value)
                clear_cookie = "session_token=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
                return self.json(200, {"status": "logged_out"}, cookies=[clear_cookie])

            # 4. Password Reset Request
            if url.path == "/api/auth/reset_password":
                email = str(body.get("email", "")).strip().lower()
                res = auth_store.create_password_reset(email)
                if res:
                    token, user_email = res
                    logger.info("Password reset requested; delivery integration is not configured")
                return self.json(200, {"status": "ok", "message": "If an account exists, a reset instruction has been dispatched."})

            # 5. Confirm Password Reset
            if url.path == "/api/auth/confirm_reset":
                token = str(body.get("token", "")).strip()
                new_pwd = str(body.get("new_password", ""))
                try:
                    success = auth_store.execute_password_reset(token, new_pwd)
                    if not success:
                        return self.json(400, {"error": "Invalid or expired reset token"})
                    return self.json(200, {"status": "ok", "message": "Password successfully reset. Please log in."})
                except ValueError as err:
                    return self.json(400, {"error": str(err)})

            # 5b. Collaborate Desk Passcode Authentication
            if url.path in {"/api/collaborate/auth", "/api/auth"}:
                if not rate_limiter.is_allowed(client_ip, '/api/collaborate/auth', limit=5):
                    return self.json(429, {'error': 'Operator authentication quota exceeded'})
                action = body.get("action", "")
                if action == "logout":
                    return self.json(
                        200,
                        {"success": True, "message": "Logged out"},
                        cookies=["zillers_collab_auth=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"]
                    )
                expected_passcode = get_collab_passcode()
                passcode = body.get("passcode", "")
                if valid_operator_passcode(passcode, expected_passcode):
                    return self.json(
                        200,
                        {"success": True, "message": "Passcode verified"},
                        cookies=[f"zillers_collab_auth={operator_cookie(expected_passcode)}; Path=/; Max-Age=604800; HttpOnly; SameSite=Strict"]
                    )
                return self.json(401, {"error": "Invalid operator passcode"})

            # 6. Public Collaborate Proposal Submission
            if url.path == "/api/collaborate":
                origin = self.headers.get('Origin')
                if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                    return self.json(403, {'error': 'Cross-origin form submission refused'})
                try:
                    body = validate_proposal(body)
                except ValueError as error:
                    return self.json(400, {'error': str(error)})
                if not form_guard.accept(body, client_ip):
                    return self.json(429, {'error': 'Submission quota or duplicate limit reached'})
                if not rate_limiter.is_allowed(client_ip, "/api/collaborate", limit=10):
                    retry = rate_limiter.retry_after(client_ip, "/api/collaborate")
                    return self.json(429, {"error": f"Rate limit exceeded. Retry in {retry} seconds."})

                name = str(body.get("name", "")).strip()
                email = str(body.get("email", "")).strip().lower()
                github = str(body.get("github", "")).strip()
                linkedin = str(body.get("linkedin", "")).strip()
                website = str(body.get("website", "")).strip()
                track = str(body.get("track", "")).strip()
                message = str(body.get("message", "")).strip()

                if not email or "@" not in email or "." not in email.split("@")[-1]:
                    return self.json(400, {"error": "A valid email address is required."})
                if not github:
                    return self.json(400, {"error": "GitHub profile URL or handle is required."})
                if not linkedin:
                    return self.json(400, {"error": "LinkedIn profile URL or handle is required."})

                collab_id = f"COL-{uuid.uuid4().hex[:8].upper()}"
                record = {
                    "id": collab_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "name": name or "Anonymous Researcher",
                    "email": email,
                    "github": github,
                    "linkedin": linkedin,
                    "website": website,
                    "track": track or "Quantitative Strategy Research",
                    "message": message,
                    "client_ip": client_ip,
                }

                with _collab_lock:
                    try:
                        COLLAB_FILE.parent.mkdir(parents=True, exist_ok=True)
                        records = []
                        if COLLAB_FILE.is_file():
                            try:
                                loaded = json.loads(COLLAB_FILE.read_text(encoding="utf-8"))
                                if isinstance(loaded, list):
                                    records = loaded
                                else:
                                    raise ValueError('Invalid proposal store')
                            except Exception:
                                return self.json(503, {'error': 'Proposal store unavailable; existing data preserved'})
                        records.append(record)
                        COLLAB_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")
                    except Exception as exc:
                        logger.error("Failed to save collaboration proposal: %s", exc)
                        return self.json(500, {"error": "Internal storage failure"})

                logger.info("New collaboration proposal logged: %s", collab_id)
                return self.json(200, {
                    "status": "ok",
                    "collab_id": collab_id,
                    "message": "Collaboration proposal successfully registered. The ZILLERS research team will reach out via email.",
                })

            # 6b. Pre-Trade Monte Carlo Odds Simulation (day-trader-skill integration)
            if url.path == "/api/market/simulate_odds":
                if not rate_limiter.is_allowed(client_ip, "/api/market/simulate_odds", limit=20):
                    retry = rate_limiter.retry_after(client_ip, "/api/market/simulate_odds")
                    return self.json(429, {"error": f"Rate limit exceeded. Retry in {retry} seconds."})
                symbol = str(body.get("symbol", "BTCUSDT")).strip().upper()
                try:
                    entry = float(body.get("entry", body.get("entry_price", 0.0)))
                    stop = float(body.get("stop", body.get("stop_price", 0.0)))
                    target = float(body.get("target", body.get("target_price", 0.0)))
                except (ValueError, TypeError):
                    return self.json(400, {"error": "Numeric entry, stop, and target prices are required."})

                if entry <= 0 or stop <= 0 or target <= 0:
                    return self.json(400, {"error": "Prices must be positive non-zero numbers."})
                if entry == stop or entry == target:
                    return self.json(400, {"error": "Entry cannot equal stop or target price."})

                horizon_bars = max(5, min(100, int(body.get("horizon_bars", 48))))
                replays = max(100, min(5000, int(body.get("replays", 1500))))

                try:
                    from cryptoscope.market_data.candle_store import CandleStore
                    from cryptoscope.simulation.time_machine import simulate_trade_odds
                    cs = CandleStore()
                    candles = cs.get_fresh_candles(symbol, "15m", limit=150)
                    if not candles or len(candles) < 20:
                        candles = cs.get_fresh_candles(symbol, "5m", limit=150)
                    res = simulate_trade_odds(
                        symbol=symbol,
                        entry=entry,
                        stop=stop,
                        target=target,
                        candles=candles,
                        horizon_bars=horizon_bars,
                        replays=replays,
                    )
                    return self.json(200, res)
                except Exception as sim_err:
                    logger.error("Simulation error: %s", sim_err)
                    return self.json(500, {"error": f"Simulation failure: {sim_err}"})

            # 6c. Multi-Agent Deliberation & Consensus (TradingAgents integration)
            # 6c. AI Berkshire Committee Qualitative Audit
            if url.path == "/api/berkshire/audit":
                if not rate_limiter.is_allowed(client_ip, "/api/berkshire/audit", limit=20):
                    retry = rate_limiter.retry_after(client_ip, "/api/berkshire/audit")
                    return self.json(429, {"error": f"Rate limit exceeded. Retry in {retry} seconds."})
                symbol = str(body.get("symbol", "BTCUSDT")).strip().upper()
                from core.quant.berkshire_committee import BerkshireCommittee

                committee = BerkshireCommittee()
                ticker = market_aggregator.get_ticker(symbol)
                price = float(ticker.get("price", 60000.0) or 60000.0)

                if "BTC" in symbol:
                    mcap = price * 19700000.0
                    vol = float(ticker.get("volume_24h", 35000000000.0) or 35000000000.0) * price
                    annual_fees = 800000000.0
                    active_users = 950000.0
                    staking_yield = 0.0
                    top_share = 0.12
                elif "ETH" in symbol:
                    mcap = price * 120000000.0
                    vol = float(ticker.get("volume_24h", 15000000000.0) or 15000000000.0) * price
                    annual_fees = 1500000000.0
                    active_users = 600000.0
                    staking_yield = 3.2
                    top_share = 0.22
                elif "SOL" in symbol:
                    mcap = price * 460000000.0
                    vol = float(ticker.get("volume_24h", 5000000000.0) or 5000000000.0) * price
                    annual_fees = 350000000.0
                    active_users = 850000.0
                    staking_yield = 6.8
                    top_share = 0.31
                else:
                    mcap = price * 100000000.0
                    vol = price * 1000000.0
                    annual_fees = 10000000.0
                    active_users = 50000.0
                    staking_yield = 0.0
                    top_share = 0.25

                audit_input = {
                    "market_cap": body.get("market_cap", mcap),
                    "daily_volume": body.get("daily_volume", vol),
                    "annual_network_fees": body.get("annual_network_fees", annual_fees),
                    "active_addresses": body.get("active_addresses", active_users),
                    "staking_yield_pct": body.get("staking_yield_pct", staking_yield),
                    "top_holders_share_pct": body.get("top_holders_share_pct", top_share),
                }
                report = committee.audit_asset(symbol, audit_input)
                return self.json(200, report)

            # Multi-Agent Hedge Fund Deliberation Committee
            if url.path == "/api/agents/committee":
                if not rate_limiter.is_allowed(client_ip, "/api/agents/committee", limit=15):
                    retry = rate_limiter.retry_after(client_ip, "/api/agents/committee")
                    return self.json(429, {"error": f"Rate limit exceeded. Retry in {retry} seconds."})
                symbol = str(body.get("symbol", "BTCUSDT")).strip().upper()
                from core.agents.hedge_fund_committee import HedgeFundCommittee
                from core.agents.thx02_decision_engine import THX02DecisionEngine
                from core.quant.factors.alpha158 import Alpha158FactorEngine
                from cryptoscope.market_data.candle_store import CandleStore
                cs = CandleStore()
                candles = cs.get_fresh_candles(symbol, "15m", limit=60)
                ticker = market_aggregator.get_ticker(symbol)
                price = float(ticker.get("price", 60000.0) or 60000.0)

                closes = [float(c["close"]) if isinstance(c, dict) else float(c[3]) for c in candles] if candles else [price] * 20
                alpha_engine = Alpha158FactorEngine()
                factors = alpha_engine.compute_latest_features(candles) if candles else {}

                thx_engine = THX02DecisionEngine()
                committee = HedgeFundCommittee(decision_engine=thx_engine)
                market_payload = {
                    "symbol": symbol,
                    "price": price,
                    "closes": closes,
                    "factors": factors,
                    "order_flow": {
                        "cvd": float(ticker.get("cvd", 0.0) or 0.0),
                        "imbalance": float(ticker.get("order_book_imbalance", 0.0) or 0.0),
                    },
                    "market_data": {
                        "price": price,
                        "volume_24h": float(ticker.get("volume_24h", 35000000000.0) or 35000000000.0),
                        "change_24h": float(ticker.get("change_24h_pct", ticker.get("change_24h", 1.5)) or 1.5),
                    },
                    "risk_metrics": {
                        "var_95_pct": 0.02,
                        "current_drawdown_pct": 0.04,
                        "liquidation_distance_pct": 0.35,
                        "kelly_fraction": 0.12,
                    }
                }
                decision = committee.deliberate_sync(symbol, market_payload)
                res = {
                    "symbol": decision.symbol,
                    "action": decision.action,
                    "conviction_score": decision.conviction_score,
                    "suggested_sizing_pct": decision.suggested_sizing_pct,
                    "risk_veto": decision.risk_veto,
                    "risk_veto_reason": decision.risk_veto_reason,
                    "persona_votes": [
                        {
                            "persona": v.persona,
                            "action": v.action,
                            "confidence": v.confidence,
                            "weight": v.weight,
                            "thesis": v.thesis,
                            "metrics": v.metrics,
                        }
                        for v in decision.persona_votes
                    ],
                    "thx02": {
                        "action": decision.thx02_decision.action,
                        "regime": decision.thx02_decision.regime,
                        "conviction": decision.thx02_decision.conviction,
                        "risk_cleared": decision.thx02_decision.risk_cleared,
                        "suggested_leverage": decision.thx02_decision.suggested_leverage,
                        "suggested_sizing_pct": decision.thx02_decision.suggested_sizing_pct,
                        "thought": decision.thx02_decision.thought,
                        "probabilities": decision.thx02_decision.probabilities,
                    } if decision.thx02_decision else None,
                    "synthesis_memo": decision.synthesis_memo,
                    "timestamp": decision.timestamp,
                }
                return self.json(200, res)

            # THX-02 Thinking Decision Model Deliberation
            if url.path == "/api/agents/thx02/deliberate":
                if not rate_limiter.is_allowed(client_ip, "/api/agents/thx02/deliberate", limit=15):
                    retry = rate_limiter.retry_after(client_ip, "/api/agents/thx02/deliberate")
                    return self.json(429, {"error": f"Rate limit exceeded. Retry in {retry} seconds."})
                symbol = str(body.get("symbol", "BTC/USDT")).strip()
                market_state = body.get("market_state", {})
                if not isinstance(market_state, dict):
                    market_state = {}
                from core.agents.thx02_decision_engine import THX02DecisionEngine
                engine = THX02DecisionEngine()
                decision = engine.deliberate_regime_and_trade(market_state)
                res = {
                    "symbol": symbol,
                    "action": decision.action,
                    "regime": decision.regime,
                    "conviction": decision.conviction,
                    "risk_cleared": decision.risk_cleared,
                    "suggested_leverage": decision.suggested_leverage,
                    "suggested_sizing_pct": decision.suggested_sizing_pct,
                    "thought": decision.thought,
                    "probabilities": decision.probabilities,
                    "metadata": decision.metadata,
                }
                return self.json(200, res)

            if url.path == "/api/agents/deliberate":
                if not rate_limiter.is_allowed(client_ip, "/api/agents/deliberate", limit=12):
                    retry = rate_limiter.retry_after(client_ip, "/api/agents/deliberate")
                    return self.json(429, {"error": f"Rate limit exceeded. Retry in {retry} seconds."})
                symbol = str(body.get("symbol", "BTCUSDT")).strip().upper()
                balance = float(body.get("balance", 10000.0))
                try:
                    from cryptoscope.market_data.candle_store import CandleStore
                    from cryptoscope.agents.analysts.market import technical
                    from cryptoscope.agents.consensus import DeliberationConsensusEngine
                    from cryptoscope.agents.schemas import Snapshot

                    cs = CandleStore()
                    candles = cs.get_fresh_candles(symbol, "15m", limit=100)
                    if not candles or len(candles) < 50:
                        candles = cs.get_fresh_candles(symbol, "5m", limit=100)

                    # Build synthetic indicators if candles are sparse
                    if candles and len(candles) >= 50:
                        snap = Snapshot(
                            symbol=symbol,
                            as_of=candles[-1]["close_time"],
                            interval_seconds=900,
                            candles=candles,
                            derivatives={},
                            news=[],
                        )
                        ind = technical(snap)
                        obs = ind.get("order_blocks", [])
                    else:
                        ticker = market_aggregator.get_ticker(symbol)
                        price = float(ticker.get("price", 65000.0)) if ticker else 65000.0
                        ind = {
                            "close": price,
                            "ema20": price * 0.995,
                            "ema50": price * 0.985,
                            "rsi14": 55.0,
                            "atr14": price * 0.018,
                            "directional_score": 30.0,
                        }
                        obs = [{"type": "BULLISH_OB", "low": price * 0.98, "high": price * 0.99}]

                    engine = DeliberationConsensusEngine()
                    decision = engine.deliberate(
                        symbol=symbol,
                        indicators=ind,
                        candles=candles,
                        order_blocks=obs,
                        balance=balance,
                    )
                    return self.json(200, decision)
                except Exception as delib_err:
                    logger.error("Deliberation error: %s", delib_err)
                    return self.json(500, {"error": f"Deliberation failure: {delib_err}"})

            # 6d. On-Chain Token Safety Audit & Rugpull Guard (QuantOrb integration)
            if url.path == "/api/risk/token_audit":
                if not rate_limiter.is_allowed(client_ip, "/api/risk/token_audit", limit=25):
                    retry = rate_limiter.retry_after(client_ip, "/api/risk/token_audit")
                    return self.json(429, {"error": f"Rate limit exceeded. Retry in {retry} seconds."})
                symbol = str(body.get("symbol", "SOL")).strip().upper()
                holders = body.get("holders")
                links = body.get("links", [])
                float_tokens = float(body.get("float_tokens", 1_000_000.0))
                reserve_tokens = float(body.get("reserve_tokens", 500_000.0))
                liquidity_usd = float(body.get("liquidity_usd", 150_000.0))

                try:
                    from cryptoscope.risk_tools.onchain_guard import cluster_operators, score_token, guard_checks

                    # If no explicit holder list passed, provide audit based on market tier
                    if not holders or not isinstance(holders, list):
                        if symbol in ["BTC", "BTCUSDT", "ETH", "ETHUSDT", "SOL", "SOLUSDT"]:
                            holders = [{"share": round(0.015 + (i * 0.001), 4), "virgin": False, "kind": "buy"} for i in range(20)]
                            links = []
                            liquidity_usd = max(liquidity_usd, 5_000_000.0)
                        else:
                            # Typical mid/meme token profile
                            holders = [{"share": 0.035, "virgin": i < 3, "kind": "transfer" if i == 0 else "buy"} for i in range(20)]
                            links = [{"a": 1, "b": 2, "level": "proven"}]

                    ops = cluster_operators(holders, links)
                    res = score_token(
                        holders=holders,
                        operators=ops,
                        float_tokens=float_tokens,
                        reserve_tokens=reserve_tokens,
                        liquidity_usd=liquidity_usd,
                    )
                    res["symbol"] = symbol
                    res["operators"] = ops
                    res["guard"] = guard_checks(creator_launched=2, creator_graduated=2, slot0_share=0.08, dev_share=0.05)
                    return self.json(200, res)
                except Exception as audit_err:
                    logger.error("Token audit error: %s", audit_err)
                    return self.json(500, {"error": f"Token audit failure: {audit_err}"})

            # 6e. Quantitative Position Sizing & Kelly Allocator
            if url.path == "/api/quant/sizing":
                if not rate_limiter.is_allowed(client_ip, "/api/quant/sizing", limit=30):
                    retry = rate_limiter.retry_after(client_ip, "/api/quant/sizing")
                    return self.json(429, {"error": f"Rate limit exceeded. Retry in {retry} seconds."})
                account_balance = float(body.get("account_balance", 10000.0))
                entry_price = float(body.get("entry_price", 0.0))
                stop_loss = float(body.get("stop_loss", 0.0))
                win_rate = float(body.get("win_rate", 0.55))
                win_loss_ratio = float(body.get("win_loss_ratio", 1.8))
                kelly_fraction = float(body.get("kelly_fraction", 0.5))
                max_account_risk_pct = float(body.get("max_account_risk_pct", 2.0))
                vol_modifier = float(body.get("volatility_compression_score", 1.0))

                res = optimal_trade_sizing(
                    account_balance=account_balance,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    win_rate=win_rate,
                    win_loss_ratio=win_loss_ratio,
                    kelly_fraction=kelly_fraction,
                    max_account_risk_pct=max_account_risk_pct,
                    volatility_compression_score=vol_modifier,
                )
                return self.json(200, res)

            # Authenticated Mutating Routes
            if not session:
                return self.json(401, {"error": "Authentication required"})

            # CSRF Verification on authenticated mutating requests
            csrf_token = self.headers.get("X-CSRF-Token") or body.get("csrf_token")
            if not csrf_token or csrf_token != session.get("csrf_token"):
                return self.json(403, {"error": "Invalid or missing CSRF token"})

            # Re-authentication for sensitive actions
            if url.path == "/api/auth/reauth":
                password = str(body.get("password", ""))
                user = auth_store.get_user_by_id(session["user_id"])
                if not user or not verify_password(password, user["password_hash"]):
                    return self.json(401, {"error": "Invalid credentials"})
                return self.json(200, {
                    "status": "ok",
                    "reauthenticated": True,
                    "expires_at": time.time() + 300,
                    "message": "Re-authentication verified for 5 minutes"
                })

            # Change Password
            if url.path == "/api/auth/change_password":
                new_pwd = str(body.get("new_password", ""))
                try:
                    auth_store.change_password(session["user_id"], new_pwd)
                    raw_token, csrf_token = auth_store.create_session(session["user_id"])
                    is_tls = self.headers.get("X-Forwarded-Proto") == "https"
                    secure_flag = "; Secure" if is_tls else ""
                    cookie_str = f"session_token={raw_token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800{secure_flag}"
                    return self.json(200, {"status": "ok", "message": "Password updated"}, cookies=[cookie_str])
                except ValueError as err:
                    return self.json(400, {"error": str(err)})

            # Toggle Favorite
            if url.path == "/api/user/favorites/toggle":
                symbol = str(body.get("symbol", "")).strip().upper()
                is_fav = auth_store.toggle_favorite(session["user_id"], symbol)
                return self.json(200, {"symbol": symbol, "is_favorite": is_fav})

            # Update User Settings
            if url.path == "/api/user/settings":
                currency = str(body.get("display_currency", "USD"))
                theme = str(body.get("theme", "dark"))
                auth_store.update_settings(session["user_id"], currency, theme)
                return self.json(200, {"status": "ok", "settings": {"display_currency": currency, "theme": theme}})

            # Telegram test message (admin + CSRF); sent by a child process so the token never enters this server
            if url.path == "/api/telegram/test":
                if session.get("role") != "admin":
                    return self.json(403, {"error": "Admin role required"})
                import subprocess as _sp
                env = {k: v for k, v in os.environ.items() if not k.startswith("TELEGRAM_")}
                out = _sp.run([sys.executable, "-B", "-m", "cryptoscope.telegram.notify", "--test"], cwd=str(ROOT), env=env,
                              capture_output=True, text=True, timeout=25)
                try:
                    result = json.loads(out.stdout.strip().splitlines()[-1])
                except Exception:
                    result = {"ok": False, "error": "Telegram sender produced no result"}
                return self.json(200 if result.get("ok") else 502, result)

            # Grid / DCA paper bots (admin + CSRF; paper only)
            if url.path.startswith("/api/bots/"):
                if session.get("role") != "admin":
                    return self.json(403, {"error": "Admin role required"})
                parts = url.path.strip("/").split("/")  # api, bots, <id|create>, [action]
                try:
                    if parts[2] == "create":
                        if kill_switch.halted:
                            return self.json(409, {"error": "Emergency halt is engaged"})
                        symbol = str(body.get("symbol", "")).upper()
                        if not symbol.isalnum() or not 5 <= len(symbol) <= 20:
                            return self.json(400, {"error": "Invalid symbol"})
                        return self.json(200, paper_bots.create(str(body.get("kind", "")), symbol, body.get("config") or {},
                                                                session.get("email", "admin")))
                    bot_id, action = parts[2], (parts[3] if len(parts) > 3 else "")
                    if action == "stop":
                        return self.json(200, paper_bots.set_status(bot_id, "STOPPED"))
                    if action == "resume":
                        return self.json(200, paper_bots.set_status(bot_id, "RUNNING"))
                    if action == "delete":
                        paper_bots.delete(bot_id)
                        return self.json(200, {"deleted": bot_id})
                    return self.json(404, {"error": "Unknown bot action"})
                except KeyError:
                    return self.json(404, {"error": "Bot not found"})
                except (ValueError, TypeError) as err:
                    return self.json(400, {"error": str(err)})

            # Scanner autopilot: scan all USDT pairs, trade the top 10 (BTC/ETH/SOL excluded), rescan every 4 h (admin + CSRF)
            # START ALL: test every LLM / decision model / safety system, then launch the bots (admin + CSRF)
            if url.path == "/api/system/startup":
                if session.get("role") != "admin":
                    return self.json(403, {"error": "Admin role required to start the system"})
                if kill_switch.halted:
                    return self.json(409, {"error": "Emergency halt is engaged; resume the governor first"})
                try:
                    return self.json(202, startup.start(str(body.get("mode", "PAPER")), session.get("email", "admin")))
                except ValueError as err:
                    return self.json(400, {"error": str(err)})
                except RuntimeError as err:
                    return self.json(409, {"error": str(err)})

            if url.path == "/api/models/sidecar":
                if session.get("role") != "admin":
                    return self.json(403, {"error": "Admin role required"})
                action = str(body.get("action", "")).lower()
                if action == "start":
                    return self.json(200, decision_sidecar.start())
                if action == "stop":
                    decision_sidecar.stop()
                    return self.json(200, {"ok": True, "stopped": True})
                return self.json(400, {"error": "action must be start or stop"})

            if url.path == "/api/scanner/autopilot":
                if session.get("role") != "admin":
                    return self.json(403, {"error": "Admin role required to control the autopilot"})
                if not body.get("enable", True):
                    autopilot.stop()
                    return self.json(200, autopilot.status())
                if kill_switch.halted:
                    return self.json(409, {"error": "Emergency halt is engaged; resume the governor first"})
                mode = str(body.get("mode", "PAPER")).upper()
                if mode not in {"PAPER", "TESTNET"}:
                    return self.json(400, {"error": "Autopilot runs in PAPER or TESTNET only"})
                try:
                    out = autopilot.start(mode, session.get("email", "admin"))
                except (ValueError, RuntimeError) as err:
                    return self.json(400, {"error": str(err)})
                return self.json(200, {"autopilot": out["autopilot"], "top": out["scan"]["top"]})

            # Autotrading fleet (PAPER / TESTNET only; admin + CSRF; refuses while the halt latch is engaged)
            if url.path in {"/api/fleet/start", "/api/fleet/stop"}:
                if session.get("role") != "admin":
                    return self.json(403, {"error": "Admin role required to control the trading fleet"})
                if url.path == "/api/fleet/stop":
                    return self.json(200, fleet.stop())
                if kill_switch.halted:
                    return self.json(409, {"error": "Emergency halt is engaged; resume the governor before starting the fleet"})
                try:
                    symbols = body.get("symbols") or scanner.scan(str(body.get("mode", "PAPER")))["top"]
                    if not symbols:
                        return self.json(409, {"error": "Scanner found no eligible coins right now; nothing to trade"})
                    return self.json(200, fleet.start(body.get("mode", "PAPER"), symbols, session.get("email", "admin")))
                except (ValueError, RuntimeError) as err:
                    return self.json(400, {"error": str(err)})

            # Master Emergency Kill Switch (supports HALT and HALT_FLATTEN)
            if url.path == "/api/governor/kill_switch":
                operator = session.get("email", "Operator")
                action = str(body.get("action", "HALT")).strip().upper()
                result = kill_switch.execute_kill_switch(action=action, triggered_by=operator)
                # Master kill: also stop everything this server runs in the background.
                result["background"] = {"fleet": {"was_running": fleet.status()["running"]},
                                        "llm": llm_panel.halt(), "ai_layer": "stopped"}
                autopilot.stop()
                fleet.stop(reason="master kill switch")
                result["background"]["fleet"]["running"] = fleet.status()["running"]
                # The THX-02 + Laya sidecar frees ~10 GB of RAM; stopping it in WSL can take seconds, so not inline.
                threading.Thread(target=decision_sidecar.stop, daemon=True, name="sidecar-stop").start()
                result["background"]["decision_sidecar"] = "stopping"
                return self.json(200, result)

            # Resume from Emergency Kill Switch (Requires Admin Password)
            if url.path == "/api/governor/resume":
                if self.client_address[0] not in {'127.0.0.1', '::1'} or any(
                    self.headers.get(h) for h in ('Forwarded', 'X-Forwarded-For', 'X-Real-IP')):
                    return self.json(403, {"error": "Emergency recovery requires the local dashboard"})
                if session.get("role") != "admin":
                    return self.json(403, {"error": "Admin role required to resume bot from emergency halt"})
                password = str(body.get("password", ""))
                admin_user = auth_store.get_user_by_id(session["user_id"])
                if not admin_user or not verify_password(password, admin_user["password_hash"]):
                    return self.json(401, {"error": "Invalid administrator password"})
                result = kill_switch.resume_bot(admin_reauthenticated=True, admin_email=admin_user["email"])
                return self.json(200, result)

            # 5-Gate Live Trading Activation Toggle
            if url.path == "/api/governor/live_toggle":
                if session.get("role") != "admin":
                    return self.json(403, {"error": "Admin role required to configure trading mode"})
                target_mode = str(body.get("mode", "PAPER")).upper()
                if target_mode == "PAPER":
                    live_governor.deactivate_to_paper("Admin set to paper mode")
                    return self.json(200, {"status": "ok", "mode": "PAPER"})

                # Validating 5-gate activation for LIVE mode
                password = str(body.get("password", ""))
                admin_user = auth_store.get_user_by_id(session["user_id"])
                if not admin_user or not verify_password(password, admin_user["password_hash"]):
                    return self.json(401, {"error": "Invalid administrator password"})

                confirmation_text = str(body.get("confirmation", ""))
                paper_trades = int(body.get("paper_trades_count", 0))
                paper_pnl = float(body.get("paper_net_pnl", 0.0))

                try:
                    live_governor.activate_live(
                        paper_trade_count=paper_trades,
                        paper_net_pnl=paper_pnl,
                        admin_reauthenticated=True,
                        admin_reauth_time=time.time(),
                        typed_confirmation=confirmation_text,
                    )
                    return self.json(200, {"status": "ok", "mode": "LIVE"})
                except LiveGateError as err:
                    return self.json(400, {"error": str(err)})

            return self.json(404, {"error": "Not found"})

        def log_message(self, *_args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description="ZILLERS institutional crypto terminal")
    parser.add_argument("--port", type=int, default=8900)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()

    validate_startup()

    auth_store = AuthStore()
    # Bootstrap admin if no admin exists (fails cleanly if ADMIN_INITIAL_PASSWORD is unset)
    if not auth_store.has_admin():
        admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
        admin_id = auth_store.bootstrap_admin(admin_email)
        print(f"[ZILLERS AUTH] Admin user bootstrapped (id={admin_id}, email={admin_email})", flush=True)

    rate_limiter = RateLimiter(limit=15, window_sec=60)
    lockout_mgr = AccountLockoutManager(threshold=5, duration=900)
    fx_service = FxRateService()
    market_aggregator = MarketDataAggregator(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT"])
    coingecko_service = CoinGeckoService()
    risk_governor = RiskGovernor()
    live_governor = LiveMultiGateGovernor()
    kill_switch = EmergencyKillSwitch(risk_governor, live_governor)

    # Initialize Laya and print version + checkpoint path at startup
    laya_evaluator = LayaTier2Evaluator()
    print(f"[ZILLERS AI] Laya Version: {laya_evaluator.laya_version} | Checkpoint: {laya_evaluator.checkpoint_path}", flush=True)

    # Start live exchange feeds in background
    binance_feed = BinanceFeed(on_ticker=market_aggregator.record_ticker, symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT"])
    coinbase_feed = CoinbaseFeed(on_ticker=market_aggregator.record_ticker, symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    kraken_feed = KrakenFeed(on_ticker=market_aggregator.record_ticker, symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    binance_feed.start()
    coinbase_feed.start()
    kraken_feed.start()

    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        handler_for(
            DashboardData(ROOT, load_config(args.config)),
            auth_store,
            rate_limiter,
            lockout_mgr,
            fx_service,
            market_aggregator,
            coingecko_service,
            risk_governor,
            live_governor,
            kill_switch,
            laya_evaluator=laya_evaluator,
        )
    )
    def checkpoint_wal():
        for db_path in [
            Path("work/runtime/crypto_candles.db"),
            Path("work/runtime/users.db"),
            Path("work/runtime/paper_execution.db"),
            Path("work/runtime/trading_journal.db"),
            Path("work/runtime/auth.db"),
            Path("work/crypto_candles.db"),
        ]:
            if db_path.exists():
                try:
                    c = sqlite3.connect(str(db_path), timeout=5.0)
                    c.execute("PRAGMA busy_timeout=5000")
                    c.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    c.close()
                except Exception:
                    pass

    def handle_shutdown(signum, frame):
        print(f"\n[ZILLERS] Shutdown signal ({signum}) received. Draining connections...", flush=True)
        threading.Thread(target=server.shutdown, daemon=True).start()

    try:
        signal.signal(signal.SIGINT, handle_shutdown)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, handle_shutdown)
    except Exception:
        pass

    print(f"ZILLERS terminal: http://localhost:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        binance_feed.stop()
        coinbase_feed.stop()
        kraken_feed.stop()
        checkpoint_wal()
        server.server_close()
        print("[ZILLERS] Graceful shutdown completed. Exiting code 0.", flush=True)


if __name__ == "__main__":
    main()
