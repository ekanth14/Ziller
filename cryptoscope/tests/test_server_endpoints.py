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
        os.environ["ADMIN_INITIAL_PASSWORD"] = "AdminTestingPassword123!"
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

    def test_health_and_ready_endpoints(self):
        with urlopen(f"{self.base_url}/health") as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["status"], "healthy")
            self.assertEqual(data["terminal"], "ZILLERS")

        with urlopen(f"{self.base_url}/ready") as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data["status"], "ready")
            self.assertIn("exchanges", data)
            self.assertIn("fx", data)

    def test_login_success_sets_session_cookie(self):
        login_data = json.dumps({"email": "admin@zillers.local", "password": "AdminTestingPassword123!"}).encode()
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
        valid_body = json.dumps({"password": "AdminTestingPassword123!"}).encode()
        req_valid = Request(
            f"{self.base_url}/api/auth/reauth",
            data=valid_body,
            headers={"Cookie": f"session_token={raw_token}", "Content-Type": "application/json", "X-CSRF-Token": csrf_token}
        )
        with urlopen(req_valid) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertTrue(data["reauthenticated"])


if __name__ == "__main__":
    unittest.main()
