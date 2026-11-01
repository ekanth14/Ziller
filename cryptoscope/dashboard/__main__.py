"""Serve the institutional ZILLERS crypto terminal: python -m cryptoscope.dashboard --port 8900."""
import argparse
from datetime import datetime, timezone
import threading
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
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
from cryptoscope.fx.rate_service import FxRateService
from cryptoscope.market_data.aggregator import MarketDataAggregator
from cryptoscope.market_data.binance_feed import BinanceFeed
from cryptoscope.market_data.coinbase_feed import CoinbaseFeed
from cryptoscope.market_data.kraken_feed import KrakenFeed
from cryptoscope.market_data.coingecko import CoinGeckoService
from cryptoscope.execution.governor import LiveMultiGateGovernor, RiskGovernor, EmergencyKillSwitch, LiveGateError
from cryptoscope.autotrader.decision import LayaTier2Evaluator
from cryptoscope.research.settings import ROOT, load_config

logger = logging.getLogger("cryptoscope.server")
STATIC = Path(__file__).parent / "static"
COLLAB_FILE = Path(__file__).resolve().parents[2] / "data" / "collaborations.json"
_collab_lock = threading.Lock()


def handler_for(data, auth_store=None, rate_limiter=None, lockout_mgr=None, fx_service=None, market_aggregator=None, coingecko_service=None, risk_governor=None, live_governor=None, kill_switch=None, laya_evaluator=None):
    auth_store = auth_store or AuthStore()
    rate_limiter = rate_limiter or RateLimiter()
    lockout_mgr = lockout_mgr or AccountLockoutManager()
    fx_service = fx_service or FxRateService()
    market_aggregator = market_aggregator or MarketDataAggregator()
    coingecko_service = coingecko_service or CoinGeckoService()
    risk_governor = risk_governor or RiskGovernor()
    live_governor = live_governor or LiveMultiGateGovernor()
    kill_switch = kill_switch or EmergencyKillSwitch(risk_governor, live_governor)
    laya_evaluator = laya_evaluator or LayaTier2Evaluator()

    class Handler(BaseHTTPRequestHandler):
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
                "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
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
            self.wfile.write(content)

        def json(self, status, body, download=None, cookies=None):
            self.send(status, json.dumps(body, allow_nan=False).encode(), "application/json; charset=utf-8", download, cookies)

        def _get_session(self):
            raw_cookies = self.headers.get("Cookie", "")
            if not raw_cookies:
                return None
            c = SimpleCookie(raw_cookies)
            if "session_token" not in c:
                return None
            token = c["session_token"].value
            return auth_store.validate_session(token)

        def _read_body_json(self):
            content_length = int(self.headers.get("Content-Length", 0))
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
                return self.json(200, {
                    "status": "ready",
                    "exchanges": market_aggregator.get_connection_status(),
                    "fx": fx_service.get_rate(),
                })

            # Static assets
            assets = {
                "/": ("index.html", "text/html"),
                "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
                "/static/app.js": ("app.js", "text/javascript"),
                "/static/style.css": ("style.css", "text/css"),
            }
            if url.path in assets:
                name, kind = assets[url.path]
                return self.send(200, (STATIC / name).read_bytes(), kind + "; charset=utf-8")

            if url.path in {"/landing", "/docs", "/about", "/landing/", "/collaborate", "/collaborate/"}:
                landing_html = STATIC / "landing" / "index.html"
                if landing_html.is_file():
                    return self.send(200, landing_html.read_bytes(), "text/html; charset=utf-8")

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

            # Public market data and FX APIs
            if url.path == "/api/fx/rate":
                target = query.get("target", ["INR"])[0]
                return self.json(200, fx_service.get_rate(target))

            if url.path == "/api/market/tickers":
                return self.json(200, {"tickers": market_aggregator.get_all_tickers()})

            if url.path == "/api/market/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                try:
                    for _ in range(60):
                        payload = json.dumps({
                            "tickers": market_aggregator.get_all_tickers(),
                            "connections": market_aggregator.get_connection_status(),
                            "timestamp": time.time(),
                        })
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(1.0)
                except (ConnectionError, BrokenPipeError, TimeoutError, OSError):
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
                                "median_price": mid,
                                "max_deviation_pct": 0.0,
                                "metadata": None
                            }
                    except Exception:
                        pass
                return self.json(200, ticker)

            if url.path == "/api/market/candles":
                symbol = query.get("symbol", ["BTCUSDT"])[0].upper()
                interval = query.get("interval", ["5m"])[0]
                limit = min(500, max(10, int(query.get("limit", [100])[0])))
                candles = []
                try:
                    from cryptoscope.market_data.candle_store import CandleStore
                    from cryptoscope.providers.binance import BinanceProvider
                    cs = CandleStore()
                    candles = cs.load_candles(symbol, interval, limit=limit)
                    if not candles or len(candles) < 20:
                        provider = BinanceProvider()
                        snap = provider.snapshot(symbol, interval)
                        if snap and snap.candles:
                            cs.save_candles(symbol, interval, snap.candles, source="binance")
                            candles = cs.load_candles(symbol, interval, limit=limit)
                            if not candles:
                                candles = snap.candles[-limit:]
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
                return self.json(200, market_aggregator.get_connection_status())

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
                })

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

            # Dashboard API routes (accessible by authenticated sessions or test runners)
            workspace = query.get("workspace", ["research"])[0]
            try:
                if url.path == "/api/dashboard":
                    res = data.overview(workspace)
                    res["connections"] = market_aggregator.get_connection_status()
                    res["fx"] = fx_service.get_rate("INR")
                    return self.json(200, res)
                if url.path == '/api/features':
                    return self.json(200, data.feature_catalog())
                if url.path == '/api/autotrader':
                    return self.json(200, data.autotrader())
                if url.path.startswith('/api/autotrader/runs/'):
                    run_id = url.path.removeprefix('/api/autotrader/runs/')
                    report = data.autotrader_run(run_id)
                    if report is None:
                        return self.json(404, {'error': 'Autonomous decision not found'})
                    return self.json(200, report, f'zien-auto-{run_id}.json' if 'download' in query else None)
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
                    logger.info("Password reset token generated for %s: %s", user_email, token)
                    print(f"\n[ZILLERS AUTH] Password reset token for {user_email}: {token}\n", flush=True)
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

            # 6. Public Collaborate Proposal Submission
            if url.path == "/api/collaborate":
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
                            except Exception:
                                records = []
                        records.append(record)
                        COLLAB_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")
                    except Exception as exc:
                        logger.error("Failed to save collaboration proposal: %s", exc)
                        return self.json(500, {"error": "Internal storage failure"})

                logger.info("New collaboration proposal logged: %s (%s)", collab_id, email)
                return self.json(200, {
                    "status": "ok",
                    "collab_id": collab_id,
                    "message": "Collaboration proposal successfully registered. The ZILLERS research team will reach out via email.",
                })

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

            # Master Emergency Kill Switch (supports HALT and HALT_FLATTEN)
            if url.path == "/api/governor/kill_switch":
                operator = session.get("email", "Operator")
                action = str(body.get("action", "HALT")).strip().upper()
                result = kill_switch.execute_kill_switch(action=action, triggered_by=operator)
                return self.json(200, result)

            # Resume from Emergency Kill Switch (Requires Admin Password)
            if url.path == "/api/governor/resume":
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

    auth_store = AuthStore()
    # Bootstrap admin if no admin exists (fails cleanly if ADMIN_INITIAL_PASSWORD is unset)
    if not auth_store.has_admin():
        admin_id = auth_store.bootstrap_admin()
        print(f"[ZILLERS AUTH] Admin user bootstrapped (id={admin_id})", flush=True)

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
        )
    )
    print(f"ZILLERS terminal: http://localhost:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        binance_feed.stop()
        coinbase_feed.stop()
        kraken_feed.stop()
        server.server_close()


if __name__ == "__main__":
    main()
