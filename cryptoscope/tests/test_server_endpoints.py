"""Integration tests for ZILLERS server endpoints, auth session cookies, and market data."""
import json
import os
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptoscope.auth.security import RateLimiter, AccountLockoutManager
from cryptoscope.auth.store import AuthStore
from cryptoscope.dashboard.__main__ import handler_for
from cryptoscope.dashboard.data import DashboardData
from cryptoscope.fx.rate_service import FxRateService
from cryptoscope.market_data.aggregator import MarketDataAggregator
from cryptoscope.market_data.coingecko import CoinGeckoService


class ServerEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "test_auth.db"
        cls.auth_store = AuthStore(cls.db_path)
        os.environ["ALLOW_OPEN_SIGNUP"] = "true"
        os.environ["ADMIN_EMAIL"] = "admin@zillers.local"
        os.environ["ADMIN_INITIAL_PASSWORD"] = "AdminSuperSecurePass2026!#"
        os.environ["COLLAB_DESK_PASSCODE"] = "LocalFixtureDeskPassword!"
        cls.admin_id = cls.auth_store.bootstrap_admin("admin@zillers.local")

        cls.rate_limiter = RateLimiter(limit=50, window_sec=60)
        cls.lockout_mgr = AccountLockoutManager(threshold=5, duration=900)
        cls.fx_service = FxRateService()
        cls.market_agg = MarketDataAggregator(["BTCUSDT"])
        cls.coingecko = CoinGeckoService()

        # Dummy dashboard data
        root = Path(__file__).resolve().parents[2]
        data = DashboardData(root, {"symbols": ["BTCUSDT"], "interval": "15m", "model": "gemma4:12b", "ollama_url": "http://127.0.0.1:11434", "model_timeout_seconds": 10, "model_max_output_tokens": 100, "model_thinking": False})

        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            handler_for(data, cls.auth_store, cls.rate_limiter, cls.lockout_mgr, cls.fx_service, cls.market_agg, cls.coingecko)
        )
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp_dir.cleanup()

    def test_00_local_admin_is_the_only_emergency_recovery_path(self):
        from cryptoscope.security.halt_state import GovernorState
        req = Request(self.base_url + '/api/auth/login',
                      data=json.dumps({'email': 'admin@zillers.local', 'password': os.environ['ADMIN_INITIAL_PASSWORD']}).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req) as response:
            cookie = response.headers['Set-Cookie'].split(';', 1)[0]
            csrf = json.load(response)['csrf_token']
        state = GovernorState()
        state.halt('isolated HTTP recovery test')
        with self.assertRaises(HTTPError) as unauthenticated:
            urlopen(Request(self.base_url + '/api/governor/resume', data=b'{}',
                            headers={'Content-Type': 'application/json'}))
        self.assertEqual(unauthenticated.exception.code, 401)
        with self.assertRaises(HTTPError) as missing_csrf:
            urlopen(Request(self.base_url + '/api/governor/resume', data=b'{}',
                            headers={'Content-Type': 'application/json', 'Cookie': cookie}))
        self.assertEqual(missing_csrf.exception.code, 403)
        def recover(password, extra=None):
            return urlopen(Request(self.base_url + '/api/governor/resume',
                           data=json.dumps({'password': password, 'csrf_token': csrf}).encode(),
                           headers={'Content-Type': 'application/json', 'Cookie': cookie, **(extra or {})}))
        with self.assertRaises(HTTPError) as wrong:
            recover('not-the-fixture-password')
        self.assertEqual(wrong.exception.code, 401)
        self.assertTrue(state.snapshot()['halted'])
        from unittest.mock import patch
        with patch.dict(os.environ, {'SIGNUP_MODE': 'open', 'ALLOW_OPEN_SIGNUP': 'true'}):
            ordinary_id = self.auth_store.create_user('ordinary-boundary@example.invalid', 'fictional-boundary-password')
        ordinary_token, ordinary_csrf = self.auth_store.create_session(ordinary_id)
        with self.assertRaises(HTTPError) as ordinary:
            recover('not-used', {'Cookie': 'session_token=' + ordinary_token, 'X-CSRF-Token': ordinary_csrf})
        self.assertEqual(ordinary.exception.code, 403)
        self.assertTrue(state.snapshot()['halted'])
        with self.assertRaises(HTTPError) as proxy:
            recover(os.environ['ADMIN_INITIAL_PASSWORD'], {'X-Forwarded-For': '127.0.0.1'})
        self.assertEqual(proxy.exception.code, 403)
        self.assertTrue(state.snapshot()['halted'])
        with recover(os.environ['ADMIN_INITIAL_PASSWORD']) as response:
            self.assertEqual(response.status, 200)
        self.assertFalse(state.snapshot()['halted'])

    def test_01_public_form_is_unauthenticated_but_rejects_duplicates_and_bad_origin(self):
        payload = {'name': 'Abuse Fixture', 'email': 'abuse@example.invalid', 'github': 'fixture',
                   'linkedin': 'fixture', 'message': 'Local abuse-control regression fixture.'}
        def post(data, extra=None):
            return urlopen(Request(self.base_url + '/api/collaborate', data=json.dumps(data).encode(),
                           headers={'Content-Type': 'application/json', **(extra or {})}))
        with post(payload) as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError) as duplicate:
            post(payload)
        self.assertEqual(duplicate.exception.code, 429)
        with self.assertRaises(HTTPError) as origin:
            post({**payload, 'name': 'Other'}, {'Origin': 'https://wrong.invalid'})
        self.assertEqual(origin.exception.code, 403)
        with self.assertRaises(HTTPError) as oversized:
            post({**payload, 'message': 'x' * 4001})
        self.assertEqual(oversized.exception.code, 400)

    def test_02_invalid_proposal_store_is_not_overwritten(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'collaborations.json'
            path.write_text('{invalid storage')
            original = path.read_bytes()
            payload = {'name': 'Storage Fixture', 'email': 'storage@example.invalid', 'github': 'fixture',
                       'linkedin': 'fixture', 'message': 'Local storage preservation regression fixture.'}
            with patch('cryptoscope.dashboard.__main__.COLLAB_FILE', path):
                with self.assertRaises(HTTPError) as failure:
                    urlopen(Request(self.base_url + '/api/collaborate', data=json.dumps(payload).encode(),
                                    headers={'Content-Type': 'application/json'}))
            self.assertEqual(failure.exception.code, 503)
            self.assertEqual(path.read_bytes(), original)

    def test_health_and_ready_endpoints(self):
        with urlopen(f"{self.base_url}/health") as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["status"], "healthy")
            self.assertEqual(data["terminal"], "ZILLERS")

            # Validate institutional security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
            headers = dict(resp.headers)
            self.assertIn("Content-Security-Policy", headers)
            self.assertIn("Strict-Transport-Security", headers)
            self.assertEqual(headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

        from unittest.mock import patch
        with patch.object(self.market_agg,'get_connection_status',return_value={}), self.assertRaises(HTTPError) as failure:
            urlopen(f"{self.base_url}/ready")
        self.assertEqual(failure.exception.code,503)
        connected={name:dict(state='connected',last_heartbeat_age=0) for name in ('binance','coinbase','kraken')}
        with patch.object(self.market_agg,'get_connection_status',return_value=connected), patch.object(self.market_agg,'get_ticker',return_value={'status':'verified'}):
            with urlopen(f"{self.base_url}/ready") as resp:
                self.assertEqual(resp.status,200)
                data=json.load(resp)
                self.assertEqual(data['status'],'ready')
                self.assertFalse(data['trading_authorized'])

    def test_login_success_sets_session_cookie(self):
        login_data = json.dumps({"email": "admin@zillers.local", "password": "AdminSuperSecurePass2026!#"}).encode()
        req = Request(f"{self.base_url}/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["user"]["role"], "admin")
            self.assertTrue(data["user"]["must_change_password"])
            self.assertIn("csrf_token", data)

            # Validate Set-Cookie header contains session_token
            set_cookie = resp.headers.get("Set-Cookie")
            self.assertIsNotNone(set_cookie)
            self.assertIn("session_token=", set_cookie)
            self.assertIn("HttpOnly", set_cookie)

    def test_auth_me_requires_valid_session(self):
        # Unauthenticated request returns 401
        req = Request(f"{self.base_url}/api/auth/me")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req)
        self.assertEqual(ctx.exception.code, 401)

        # Authenticated request returns user profile
        raw_token, _ = self.auth_store.create_session(self.admin_id)
        req_auth = Request(f"{self.base_url}/api/auth/me", headers={"Cookie": f"session_token={raw_token}"})
        with urlopen(req_auth) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertTrue(data["authenticated"])
            self.assertEqual(data["email"], "admin@zillers.local")

    def test_market_sse_stream_delivers_payload(self):
        req = Request(f"{self.base_url}/api/market/stream")
        with urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
            line = resp.readline().decode("utf-8")
            self.assertTrue(line.startswith("data: "))
            payload = json.loads(line.removeprefix("data: ").strip())
            self.assertIn("tickers", payload)
            self.assertIn("connections", payload)

    def test_fx_rate_endpoint(self):
        req = Request(f"{self.base_url}/api/fx/rate?target=INR")
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertIn("status", data)
            self.assertEqual(data["target"], "INR")
            # Cold state without upstream mock returns unavailable
            self.assertIn(data["status"], ["available", "stale", "unavailable"])

    def test_csrf_token_validation_on_mutating_requests(self):
        raw_token, csrf_token = self.auth_store.create_session(self.admin_id)
        payload = json.dumps({"display_currency": "USD", "theme": "dark"}).encode()

        # Request missing CSRF header returns 403 Forbidden
        req_no_csrf = Request(
            f"{self.base_url}/api/user/settings",
            data=payload,
            headers={"Cookie": f"session_token={raw_token}", "Content-Type": "application/json"}
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_no_csrf)
        self.assertEqual(ctx.exception.code, 403)

        # Request with valid X-CSRF-Token header succeeds 200 OK
        req_with_csrf = Request(
            f"{self.base_url}/api/user/settings",
            data=payload,
            headers={
                "Cookie": f"session_token={raw_token}",
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf_token,
            }
        )
        with urlopen(req_with_csrf) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["status"], "ok")

    def test_reauth_endpoint(self):
        raw_token, csrf_token = self.auth_store.create_session(self.admin_id)

        # Invalid password returns 401
        invalid_body = json.dumps({"password": "WrongPassword999!"}).encode()
        req_invalid = Request(
            f"{self.base_url}/api/auth/reauth",
            data=invalid_body,
            headers={"Cookie": f"session_token={raw_token}", "Content-Type": "application/json", "X-CSRF-Token": csrf_token}
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_invalid)
        self.assertEqual(ctx.exception.code, 401)

        # Correct password returns 200 with reauthenticated: True
        valid_body = json.dumps({"password": "AdminSuperSecurePass2026!#"}).encode()
        req_valid = Request(
            f"{self.base_url}/api/auth/reauth",
            data=valid_body,
            headers={"Cookie": f"session_token={raw_token}", "Content-Type": "application/json", "X-CSRF-Token": csrf_token}
        )
        with urlopen(req_valid) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertTrue(data["reauthenticated"])

    def test_market_listings_endpoint(self):
        req = Request(f"{self.base_url}/api/market/listings?page=1&per_page=10")
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertIn("items", data)
            self.assertIn("total", data)
            self.assertEqual(data["page"], 1)
            self.assertEqual(data["per_page"], 10)
            self.assertIn("attribution", data)
            self.assertIn("CoinGecko", data["attribution"])

    def test_market_candles_endpoint(self):
        req = Request(f"{self.base_url}/api/market/candles?symbol=ETHUSDT&interval=5m&limit=10")
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["symbol"], "ETHUSDT")
            self.assertEqual(data["interval"], "5m")
            self.assertIn("candles", data)
            self.assertIsInstance(data["candles"], list)
            if data["candles"]:
                c = data["candles"][-1]
                for key in ("open", "high", "low", "close", "volume"):
                    self.assertIn(key, c)

    def test_landing_page_and_documentation_routes(self):
        for route in ("/landing", "/docs", "/about", "/landing/", "/collaborate", "/collaborate/", "/setup", "/setup/"):
            req = Request(f"{self.base_url}{route}")
            with urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                html = resp.read().decode("utf-8")
                self.assertIn("ZILLERS", html)
                self.assertIn("Zien Organisation", html)



    def test_collaborate_list_endpoint(self):
        from urllib.error import HTTPError
        
        # 1. Without passcode: JSON request must return 401 Unauthorized
        req_no_auth = Request(f"{self.base_url}/api/collaborate/list", headers={"Accept": "application/json"})
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_no_auth)
        self.assertEqual(ctx.exception.code, 401)

        # 2. Authenticate with LocalFixtureDeskPassword! via /api/collaborate/auth
        auth_req = Request(
            f"{self.base_url}/api/collaborate/auth",
            data=json.dumps({"passcode": "LocalFixtureDeskPassword!"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urlopen(auth_req) as resp:
            self.assertEqual(resp.status, 200)
            cookie = resp.headers.get("Set-Cookie", "")
            self.assertIn("zillers_collab_auth", cookie)

        # 3. With passcode header: returns 200 and proposal data
        req_auth = Request(
            f"{self.base_url}/api/collaborate/list",
            headers={"Accept": "application/json", "X-Desk-Passcode": "LocalFixtureDeskPassword!"}
        )
        with urlopen(req_auth) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["status"], "ok")
            self.assertIn("proposals", data)

        # 4. Browser HTML view for /collaborations without auth -> Locked screen
        req_html = Request(f"{self.base_url}/collaborations", headers={"Accept": "text/html"})
        with urlopen(req_html) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("Restricted Access", body)

        # 5. Browser HTML view for /collaborations with auth cookie -> Unlocked desk
        req_html_auth = Request(f"{self.base_url}/collaborations", headers={"Accept": "text/html", "Cookie": cookie.split(";", 1)[0]})
        with urlopen(req_html_auth) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("ZILLERS Collaboration Proposals Desk", body)

    def test_collaborate_proposal_submission(self):
        payload = {
            "name": "Jane Quant",
            "email": "jane@quantlab.org",
            "github": "https://github.com/janequant",
            "linkedin": "https://linkedin.com/in/janequant",
            "website": "https://janequant.dev",
            "track": "Quantitative Strategy Research",
            "message": "Interested in contributing to SMC / FVG statistical research.",
        }
        req = Request(
            f"{self.base_url}/api/collaborate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"localhost:{self.port}"},
            method="POST",
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["status"], "ok")
            self.assertTrue(data["collab_id"].startswith("COL-"))
            self.assertIn("message", data)

        # Missing email validation
        invalid_payload = dict(payload)
        del invalid_payload["email"]
        req_bad = Request(
            f"{self.base_url}/api/collaborate",
            data=json.dumps(invalid_payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"localhost:{self.port}"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_bad)
        self.assertEqual(ctx.exception.code, 400)

        # Missing github validation
        no_github = dict(payload)
        no_github["github"] = ""
        req_no_gh = Request(
            f"{self.base_url}/api/collaborate",
            data=json.dumps(no_github).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"localhost:{self.port}"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_no_gh)
        self.assertEqual(ctx.exception.code, 400)

        # Missing linkedin validation
        no_li = dict(payload)
        no_li["linkedin"] = ""
        req_no_li = Request(
            f"{self.base_url}/api/collaborate",
            data=json.dumps(no_li).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"localhost:{self.port}"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_no_li)
        self.assertEqual(ctx.exception.code, 400)


    def test_simulate_odds_endpoint(self):
        payload = {
            "symbol": "BTCUSDT",
            "entry": 50000.0,
            "stop": 49000.0,
            "target": 52000.0,
            "horizon_bars": 20,
            "replays": 150,
        }
        req = Request(
            f"{self.base_url}/api/market/simulate_odds",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"localhost:{self.port}"},
            method="POST",
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["symbol"], "BTCUSDT")
            self.assertEqual(data["side"], "LONG")
            self.assertIn("empirical_win_rate", data)
            self.assertIn("expected_r", data)
            self.assertIn("percentiles", data)

        # Invalid zero price
        bad_req = Request(
            f"{self.base_url}/api/market/simulate_odds",
            data=json.dumps({"symbol": "BTCUSDT", "entry": 0, "stop": 49000, "target": 52000}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"localhost:{self.port}"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(bad_req)
        self.assertEqual(ctx.exception.code, 400)


    def test_agents_deliberate_endpoint(self):
        payload = {
            "symbol": "BTCUSDT",
            "balance": 15000.0,
        }
        req = Request(
            f"{self.base_url}/api/agents/deliberate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"localhost:{self.port}"},
            method="POST",
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["symbol"], "BTCUSDT")
            self.assertIn(data["action"], ["BUY", "SELL", "STAND_ASIDE"])
            self.assertIn("conviction_score", data)
            self.assertIn("bull_thesis", data)
            self.assertIn("bear_thesis", data)
            self.assertIn("risk_debate", data)


    def test_token_audit_endpoint(self):
        payload = {
            "symbol": "SOL",
            "float_tokens": 1000000.0,
            "reserve_tokens": 500000.0,
            "liquidity_usd": 250000.0,
        }
        req = Request(
            f"{self.base_url}/api/risk/token_audit",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"localhost:{self.port}"},
            method="POST",
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["symbol"], "SOL")
            self.assertIn("score", data)
            self.assertIn(data["band"], ["CLEAN", "OK", "RISKY", "DANGER"])
            self.assertIn("operators", data)
            self.assertIn("guard", data)

    def test_quant_pairs_endpoint(self):
        with urlopen(f"{self.base_url}/api/quant/pairs?pairs=ETHUSDT:BTCUSDT") as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertIn("pairs", data)
            self.assertIsInstance(data["pairs"], list)
            if data["pairs"]:
                pair0 = data["pairs"][0]
                self.assertIn("pair", pair0)
                self.assertIn("cointegration", pair0)
                self.assertIn("ornstein_uhlenbeck", pair0)
                self.assertIn("zscore", pair0)

    def test_quant_volatility_endpoint(self):
        with urlopen(f"{self.base_url}/api/quant/volatility?symbol=BTCUSDT&interval=15m") as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["symbol"], "BTCUSDT")
            self.assertIn("regime", data)
            self.assertIn("estimators", data)
            self.assertIn("compression_ratio", data)

    def test_quant_orderflow_endpoint(self):
        with urlopen(f"{self.base_url}/api/quant/orderflow?symbol=BTCUSDT&lookback=25") as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["symbol"], "BTCUSDT")
            self.assertIn("buy_volume_ratio", data)
            self.assertIn("divergence", data)
            self.assertIn("taker_dominance", data)

    def test_quant_sizing_endpoint(self):
        payload = {
            "account_balance": 25000.0,
            "entry_price": 65000.0,
            "stop_loss": 63500.0,
            "win_rate": 0.56,
            "win_loss_ratio": 1.9,
            "kelly_fraction": 0.5,
        }
        req = Request(
            f"{self.base_url}/api/quant/sizing",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"localhost:{self.port}"},
            method="POST",
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "APPROVED")
            self.assertGreater(data["position_size_usd"], 0)
            self.assertGreater(data["risk_usd"], 0)
            self.assertIn("kelly_metrics", data)


if __name__ == "__main__":
    unittest.main()
