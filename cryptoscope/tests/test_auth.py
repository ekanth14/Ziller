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
    needs_rehash,
    hash_token,
    RateLimiter,
    AccountLockoutManager,
    extract_client_ip,
)
from cryptoscope.auth.store import AuthStore
from cryptoscope.auth.cli import cmd_unlock, cmd_list_users


class AuthSecurityTests(unittest.TestCase):
    def test_scrypt_hashing_and_verification(self):
        pwd = "InstitutionalPassword123!"
        hashed = hash_password(pwd)
        self.assertTrue(hashed.startswith("scrypt$131072$8$1$"))
        parts = hashed.split("$")
        # Ensure 32-byte salt (64 hex characters)
        self.assertEqual(len(parts[4]), 64)
        self.assertTrue(verify_password(pwd, hashed))
        self.assertFalse(verify_password("WrongPassword123!", hashed))
        self.assertFalse(verify_password("", hashed))
        self.assertFalse(needs_rehash(hashed))

    def test_needs_rehash_on_legacy_parameters(self):
        pwd = "LegacyPassword123!"
        legacy_hash = hash_password(pwd, n=16384, r=8, p=1)
        self.assertTrue(legacy_hash.startswith("scrypt$16384$8$1$"))
        self.assertTrue(verify_password(pwd, legacy_hash))
        self.assertTrue(needs_rehash(legacy_hash))

    def test_password_length_constraint(self):
        with self.assertRaises(ValueError):
            hash_password("short")

    def test_scrypt_concurrency_semaphore_limits_parallel_execution(self):
        from concurrent.futures import ThreadPoolExecutor
        from cryptoscope.auth.security import SCRYPT_SEMAPHORE
        import threading

        active_count = 0
        max_active = 0
        lock = threading.Lock()

        orig_acquire = SCRYPT_SEMAPHORE.acquire
        orig_release = SCRYPT_SEMAPHORE.release

        def instrumented_acquire(*args, **kwargs):
            nonlocal active_count, max_active
            res = orig_acquire(*args, **kwargs)
            with lock:
                active_count += 1
                if active_count > max_active:
                    max_active = active_count
            return res

        def instrumented_release(*args, **kwargs):
            nonlocal active_count
            with lock:
                active_count -= 1
            return orig_release(*args, **kwargs)

        with patch.object(SCRYPT_SEMAPHORE, 'acquire', side_effect=instrumented_acquire), \
             patch.object(SCRYPT_SEMAPHORE, 'release', side_effect=instrumented_release):
            with ThreadPoolExecutor(max_workers=6) as executor:
                # Use smaller n for test speed while testing semaphore concurrency boundary
                futures = [executor.submit(hash_password, f"PasswordTest{i}!", n=2048) for i in range(6)]
                results = [f.result() for f in futures]
                self.assertEqual(len(results), 6)
                self.assertLessEqual(max_active, 2)

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

    def test_exponential_tiered_lockout(self):
        mgr = AccountLockoutManager(tiered=True)
        email = "tiered_trader@zillers.local"

        # 1 and 2 failures: not locked
        self.assertFalse(mgr.record_failure(email)[0])
        self.assertFalse(mgr.record_failure(email)[0])

        # 3 failures: 1 min (60s) lockout
        locked3, rem3 = mgr.record_failure(email)
        self.assertTrue(locked3)
        self.assertLessEqual(rem3, 60)

        # 4th failure
        mgr.record_failure(email)

        # 5th failure: 15 min (900s) lockout
        locked5, rem5 = mgr.record_failure(email)
        self.assertTrue(locked5)
        self.assertGreater(rem5, 60)
        self.assertLessEqual(rem5, 900)

        # Up to 10 failures: temporary 1 hour cap (NEVER permanent)
        for _ in range(4):
            mgr.record_failure(email)
        locked10, rem10 = mgr.record_failure(email)
        self.assertTrue(locked10)
        self.assertGreater(rem10, 900)
        self.assertLessEqual(rem10, 3600)  # Capped at 1 hour

        # Admin unlock releases the account
        mgr.admin_unlock(email)
        self.assertFalse(mgr.is_locked(email)[0])

    def test_cli_account_unlock(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test_users.db"
            store = AuthStore(db_path)
            with patch.dict(os.environ, {"ADMIN_INITIAL_PASSWORD": "AdminSecurePassword2026!", "ADMIN_EMAIL": "admin@zillers.local"}):
                store.bootstrap_admin()
            # Disable user
            with store._lock:
                conn = store._get_connection()
                conn.execute("UPDATE users SET disabled = 1 WHERE email = 'admin@zillers.local'")
                conn.commit()
                conn.close()
            user_disabled = store.get_user_by_email("admin@zillers.local")
            self.assertEqual(user_disabled["disabled"], 1)

            # Use CLI unlock command
            cmd_unlock("admin@zillers.local", db_path=str(db_path))
            user_active = store.get_user_by_email("admin@zillers.local")
            self.assertEqual(user_active["disabled"], 0)

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
        os.environ["ADMIN_EMAIL"] = "admin@zillers.local"

    def test_admin_bootstrap_fails_if_password_unset(self):
        # Fails if email is unset
        with patch.dict(os.environ, {"ADMIN_INITIAL_PASSWORD": "AdminSuperSecurePass2026!"}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                self.store.bootstrap_admin()
            self.assertIn("ADMIN_EMAIL", str(ctx.exception))

        # Fails if password is unset
        with patch.dict(os.environ, {"ADMIN_EMAIL": "admin@zillers.local"}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                self.store.bootstrap_admin()
            self.assertIn("ADMIN_INITIAL_PASSWORD", str(ctx.exception))

        # Fails on weak or default password
        with patch.dict(os.environ, {"ADMIN_EMAIL": "admin@zillers.local", "ADMIN_INITIAL_PASSWORD": "AdminTestingPassword123!"}):
            with self.assertRaises(RuntimeError) as ctx:
                self.store.bootstrap_admin()
            self.assertIn("Insecure/weak default password", str(ctx.exception))

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
