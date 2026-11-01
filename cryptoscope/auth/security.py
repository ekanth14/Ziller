"""Cryptographic security utilities, scrypt password hashing, rate limiting, and account lockouts."""
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cryptoscope.auth.security")

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 minutes


def hash_password(password: str) -> str:
    """Hash password using scrypt with random 16-byte salt."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification of password against stored scrypt hash."""
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = bytes.fromhex(parts[4])
        expected_key = bytes.fromhex(parts[5])
        key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p)
        return hmac.compare_digest(key, expected_key)
    except Exception as e:
        logger.debug("Password verification error: %s", e)
        return False


def hash_token(token: str) -> str:
    """Deterministic SHA-256 hash of a session token for secure database indexing."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_session_token() -> Tuple[str, str]:
    """Generate high-entropy raw session token and accompanying CSRF token."""
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    return raw_token, csrf_token


def extract_client_ip(headers: Dict[str, str], socket_ip: str) -> str:
    """Extract client IP, honoring X-Forwarded-For only if TRUST_PROXY is explicitly enabled."""
    trust_proxy = os.environ.get("TRUST_PROXY", "").lower() in {"1", "true", "yes"}
    if trust_proxy:
        xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if xff:
            # Client IP is the leftmost entry in X-Forwarded-For
            client = xff.split(",")[0].strip()
            if client:
                return client
    return socket_ip


class RateLimiter:
    """Sliding-window in-memory rate limiter per IP address."""
    def __init__(self, limit: int = 10, window_sec: int = 60):
        self.limit = limit
        self.window_sec = window_sec
        self.requests: Dict[str, List[float]] = {}

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        cutoff = now - self.window_sec
        history = [t for t in self.requests.get(ip, []) if t > cutoff]
        if len(history) >= self.limit:
            self.requests[ip] = history
            return False
        history.append(now)
        self.requests[ip] = history
        return True

    def retry_after(self, ip: str) -> int:
        now = time.time()
        cutoff = now - self.window_sec
        history = [t for t in self.requests.get(ip, []) if t > cutoff]
        if not history:
            return 1
        return max(1, int(history[0] + self.window_sec - now))


class AccountLockoutManager:
    """Tracks consecutive failed logins per account; locks for 15 minutes after 5 failures."""
    def __init__(self, threshold: int = LOCKOUT_THRESHOLD, duration: int = LOCKOUT_DURATION_SECONDS):
        self.threshold = threshold
        self.duration = duration
        # email -> {"failures": int, "locked_until": float}
        self.accounts: Dict[str, Dict[str, float]] = {}

    def is_locked(self, email: str) -> Tuple[bool, int]:
        normalized = email.strip().lower()
        now = time.time()
        rec = self.accounts.get(normalized)
        if not rec:
            return False, 0
        locked_until = rec.get("locked_until", 0.0)
        if now < locked_until:
            rem = int(locked_until - now)
            return True, rem
        # Lockout expired
        if locked_until > 0.0:
            rec["failures"] = 0
            rec["locked_until"] = 0.0
        return False, 0

    def record_failure(self, email: str) -> Tuple[bool, int]:
        normalized = email.strip().lower()
        now = time.time()
        rec = self.accounts.setdefault(normalized, {"failures": 0, "locked_until": 0.0})
        rec["failures"] += 1
        if rec["failures"] >= self.threshold:
            rec["locked_until"] = now + self.duration
            logger.warning("Account %s locked out due to %d consecutive failed logins", normalized, rec["failures"])
            return True, self.duration
        return False, 0

    def record_success(self, email: str):
        normalized = email.strip().lower()
        if normalized in self.accounts:
            self.accounts[normalized] = {"failures": 0, "locked_until": 0.0}
