"""Serve the institutional ZILLERS crypto terminal: python -m cryptoscope.dashboard --port 8900."""
import argparse
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
)
from cryptoscope.auth.store import AuthStore
from cryptoscope.dashboard.data import DashboardData
from cryptoscope.fx.rate_service import FxRateService
from cryptoscope.market_data.aggregator import MarketDataAggregator
from cryptoscope.market_data.binance_feed import BinanceFeed
from cryptoscope.market_data.coinbase_feed import CoinbaseFeed
from cryptoscope.market_data.coingecko import CoinGeckoService
from cryptoscope.research.settings import ROOT, load_config

logger = logging.getLogger("cryptoscope.server")
STATIC = Path(__file__).parent / "static"


def handler_for(data, auth_store=None, rate_limiter=None, lockout_mgr=None, fx_service=None, market_aggregator=None, coingecko_service=None):
    auth_store = auth_store or AuthStore()
    rate_limiter = rate_limiter or RateLimiter()
    lockout_mgr = lockout_mgr or AccountLockoutManager()
    fx_service = fx_service or FxRateService()
    market_aggregator = market_aggregator or MarketDataAggregator()
    coingecko_service = coingecko_service or CoinGeckoService()

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, content, kind, download=None, cookies=None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
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

            if url.path.startswith("/assets/"):
                asset_path = (STATIC / url.path.lstrip("/")).resolve()
                if STATIC in asset_path.parents and asset_path.is_file():
                    mime = "image/png" if asset_path.suffix == ".png" else "image/svg+xml" if asset_path.suffix == ".svg" else "application/octet-stream"
                    return self.send(200, asset_path.read_bytes(), mime)

            # Public market data and FX APIs
            if url.path == "/api/fx/rate":
                target = query.get("target", ["INR"])[0]
                return self.json(200, fx_service.get_rate(target))

            if url.path == "/api/market/tickers":
                return self.json(200, {"tickers": market_aggregator.get_all_tickers()})

            if url.path == "/api/market/ticker":
                symbol = query.get("symbol", ["BTCUSDT"])[0].upper()
                return self.json(200, market_aggregator.get_ticker(symbol))

            if url.path == "/api/market/connections":
                return self.json(200, market_aggregator.get_connection_status())

            if url.path == "/api/market/listings":
                page = int(query.get("page", [1])[0])
                per_page = int(query.get("per_page", [50])[0])
                return self.json(200, coingecko_service.get_top_listings(per_page, page))

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
                if not rate_limiter.is_allowed(client_ip):
                    retry = rate_limiter.retry_after(client_ip)
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
                        return self.json(423, {"error": f"Account locked for {rem_lock} seconds due to 5 consecutive failures."})
                    return self.json(401, {"error": "Invalid email or password"})

                lockout_mgr.record_success(email)
                raw_token, csrf_token = auth_store.create_session(user["id"])
                cookie_str = f"session_token={raw_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200"

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
                if not rate_limiter.is_allowed(client_ip):
                    return self.json(429, {"error": "Rate limit exceeded"})

                email = str(body.get("email", "")).strip().lower()
                password = str(body.get("password", ""))
                invite_code = body.get("invite_code")

                try:
                    user_id = auth_store.create_user(email, password, role="user", invite_code=invite_code)
                    raw_token, csrf_token = auth_store.create_session(user_id)
                    cookie_str = f"session_token={raw_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200"
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
                clear_cookie = "session_token=; Path=/; HttpOnly; Max-Age=0"
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

            # Authenticated Mutating Routes
            if not session:
                return self.json(401, {"error": "Authentication required"})

            # Change Password
            if url.path == "/api/auth/change_password":
                new_pwd = str(body.get("new_password", ""))
                try:
                    auth_store.change_password(session["user_id"], new_pwd)
                    raw_token, csrf_token = auth_store.create_session(session["user_id"])
                    cookie_str = f"session_token={raw_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200"
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
    # Bootstrap admin if ADMIN_INITIAL_PASSWORD is provided or required
    if os.environ.get("ADMIN_INITIAL_PASSWORD"):
        try:
            admin_id = auth_store.bootstrap_admin()
            print(f"[ZILLERS AUTH] Admin user bootstrapped (id={admin_id})", flush=True)
        except Exception as e:
            logger.warning("Admin bootstrap note: %s", e)

    rate_limiter = RateLimiter(limit=15, window_sec=60)
    lockout_mgr = AccountLockoutManager(threshold=5, duration=900)
    fx_service = FxRateService()
    market_aggregator = MarketDataAggregator(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    coingecko_service = CoinGeckoService()

    # Start live exchange feeds in background
    binance_feed = BinanceFeed(on_ticker=market_aggregator.record_ticker, symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    coinbase_feed = CoinbaseFeed(on_ticker=market_aggregator.record_ticker, symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    binance_feed.start()
    coinbase_feed.start()

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
        server.server_close()


if __name__ == "__main__":
    main()
