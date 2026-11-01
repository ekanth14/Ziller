"""Tests for institutional scrypt authentication, rate limiting, and account lockouts."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptoscope.auth.security import (
    hash_password,
    verify_password,
    hash_token,
    RateLimiter,
    AccountLockoutManager,
    extract_client_ip,
)
from cryptoscope.auth.store import AuthStore


class AuthSecurityTests(unittest.TestCase):
    def test_scrypt_hashing_and_verification(self):
        pwd = "InstitutionalPassword123!"
        hashed = hash_password(pwd)
        self.assertTrue(hashed.startswith("scrypt$16384$8$1$"))
        self.assertTrue(verify_password(pwd, hashed))
        self.assertFalse(verify_password("WrongPassword123!", hashed))
        self.assertFalse(verify_password("", hashed))

    def test_password_length_constraint(self):
        with self.assertRaises(ValueError):
            hash_password("short")

    def test_ip_rate_limiter(self):
        limiter = RateLimiter(limit=3, window_sec=10)
        ip = "192.168.1.100"
        self.assertTrue(limiter.is_allowed(ip))
        self.assertTrue(limiter.is_allowed(ip))
        self.assertTrue(limiter.is_allowed(ip))
        self.assertFalse(limiter.is_allowed(ip))
        self.assertGreater(limiter.retry_after(ip), 0)

    def test_account_lockout_after_five_failed_attempts(self):
        mgr = AccountLockoutManager(threshold=5, duration=900)
        email = "trader@zillers.local"
        self.assertFalse(mgr.is_locked(email)[0])

        for _ in range(4):
            locked, _ = mgr.record_failure(email)
            self.assertFalse(locked)

        # 5th attempt triggers lockout
        locked, rem = mgr.record_failure(email)
        self.assertTrue(locked)
        self.assertGreaterEqual(rem, 890)

        is_locked, rem2 = mgr.is_locked(email)
        self.assertTrue(is_locked)
        self.assertGreater(rem2, 0)

        # Successful login resets failure count
        mgr.record_success(email)
        mgr.accounts[email]["locked_until"] = 0.0
        self.assertFalse(mgr.is_locked(email)[0])

    def test_proxy_header_trust_only_when_configured(self):
        headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18"}
        # Without TRUST_PROXY, raw socket IP must be used
        with patch.dict(os.environ, {"TRUST_PROXY": "false"}):
            self.assertEqual(extract_client_ip(headers, "127.0.0.1"), "127.0.0.1")

        # With TRUST_PROXY=true, leftmost client IP is used
        with patch.dict(os.environ, {"TRUST_PROXY": "true"}):
            self.assertEqual(extract_client_ip(headers, "127.0.0.1"), "203.0.113.195")


class AuthStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "test_users.db"
        self.store = AuthStore(self.db_path)

    def test_admin_bootstrap_fails_if_password_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                self.store.bootstrap_admin()
            self.assertIn("ADMIN_INITIAL_PASSWORD", str(ctx.exception))

    def test_admin_bootstrap_forces_password_change_on_first_login(self):
        with patch.dict(os.environ, {"ADMIN_INITIAL_PASSWORD": "AdminSuperSecurePass2026!"}):
            admin_id = self.store.bootstrap_admin("admin@zillers.local")
            user = self.store.get_user_by_id(admin_id)
            self.assertEqual(user["role"], "admin")
            self.assertEqual(user["must_change_password"], 1)

    def test_session_lifecycle(self):
        with patch.dict(os.environ, {"ADMIN_INITIAL_PASSWORD": "AdminSuperSecurePass2026!"}):
            admin_id = self.store.bootstrap_admin()
            raw_token, csrf_token = self.store.create_session(admin_id)
            session = self.store.validate_session(raw_token)
            self.assertIsNotNone(session)
            self.assertEqual(session["user_id"], admin_id)
            self.assertEqual(session["csrf_token"], csrf_token)

            # Revoke session
            self.store.revoke_session(raw_token)
            self.assertIsNone(self.store.validate_session(raw_token))

    def test_password_reset_flow(self):
        with patch.dict(os.environ, {"ADMIN_INITIAL_PASSWORD": "AdminSuperSecurePass2026!"}):
            admin_id = self.store.bootstrap_admin()
            raw_reset_token, email = self.store.create_password_reset("admin@zillers.local")
            self.assertEqual(email, "admin@zillers.local")

            # Execute reset
            success = self.store.execute_password_reset(raw_reset_token, "NewStrongPassword456!")
            self.assertTrue(success)

            # Token is single-use: second execution fails
            self.assertFalse(self.store.execute_password_reset(raw_reset_token, "AnotherPassword789!"))

            # New password works
            user = self.store.get_user_by_id(admin_id)
            self.assertTrue(verify_password("NewStrongPassword456!", user["password_hash"]))

    def test_favorites_and_settings(self):
        with patch.dict(os.environ, {"ADMIN_INITIAL_PASSWORD": "AdminSuperSecurePass2026!"}):
            admin_id = self.store.bootstrap_admin()
            # Toggle favorite
            self.assertTrue(self.store.toggle_favorite(admin_id, "BTCUSDT"))
            self.assertIn("BTCUSDT", self.store.get_favorites(admin_id))
            # Toggle off
            self.assertFalse(self.store.toggle_favorite(admin_id, "BTCUSDT"))
            self.assertEqual(self.store.get_favorites(admin_id), [])

            # Update settings
            self.store.update_settings(admin_id, display_currency="INR", theme="dark")
            settings = self.store.get_settings(admin_id)
            self.assertEqual(settings["display_currency"], "INR")


if __name__ == "__main__":
    unittest.main()
