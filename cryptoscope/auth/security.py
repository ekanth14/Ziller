"""Cryptographic security utilities, scrypt password hashing, rate limiting, and account lockouts."""
import hashlib
import hmac
import logging
import os
import secrets
import time
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("cryptoscope.auth.security")

SCRYPT_N = 131072  # 2^17
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 256 * 1024 * 1024  # 256 MB to support N=2^17
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 minutes
MAX_LOCKOUT_DURATION_SECONDS = 60 * 60  # 1 hour cap (never permanent)


def hash_password(password: str, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> str:
    """Hash password using scrypt with random 32-byte salt and explicit parameters stored in hash."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = secrets.token_bytes(32)
    maxmem = max(SCRYPT_MAXMEM, 128 * n * r * 2)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=maxmem)
    return f"scrypt${n}${r}${p}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification of password against stored scrypt hash with dynamic parameters."""
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = bytes.fromhex(parts[4])
        expected_key = bytes.fromhex(parts[5])
        maxmem = max(SCRYPT_MAXMEM, 128 * n * r * 2)
        key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=maxmem)
        return hmac.compare_digest(key, expected_key)
    except Exception as e:
        logger.debug("Password verification error: %s", e)
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Return True if stored hash does not match current target scrypt parameters (N=2^17, r=8, p=1)."""
    if not stored_hash:
        return True
    try:
        parts = stored_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return True
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        return n != SCRYPT_N or r != SCRYPT_R or p != SCRYPT_P
    except Exception:
        return True


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
    """Sliding-window in-memory rate limiter per IP address and endpoint."""
    def __init__(self, limit: int = 10, window_sec: int = 60):
        self.limit = limit
        self.window_sec = window_sec
        self.requests: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, ip: str, endpoint: str = "", limit: Optional[int] = None) -> bool:
        key = f"{ip}:{endpoint}" if endpoint else ip
        max_reqs = limit or self.limit
        now = time.time()
        cutoff = now - self.window_sec
        with self._lock:
            history = [t for t in self.requests.get(key, []) if t > cutoff]
            if len(history) >= max_reqs:
                self.requests[key] = history
                return False
            history.append(now)
            self.requests[key] = history
            return True

    def retry_after(self, ip: str, endpoint: str = "") -> int:
        key = f"{ip}:{endpoint}" if endpoint else ip
        now = time.time()
        cutoff = now - self.window_sec
        with self._lock:
            history = [t for t in self.requests.get(key, []) if t > cutoff]
            if not history:
                return 1
            return max(1, int(history[0] + self.window_sec - now))


class AccountLockoutManager:
    """Tracks consecutive failed logins per account with temporary exponential backoff:
    - 3 failed logins -> 1 min (60s)
    - 5 failed logins -> 15 min (900s)
    - 10+ failed logins -> 1 hour (3600s max cap, NEVER permanent)
    Lockout expires automatically after the duration or via admin CLI unlock.
    """
    def __init__(self, threshold: Optional[int] = None, duration: Optional[int] = None, tiered: Optional[bool] = None):
        self.tiered = (tiered is True) or (threshold is None and tiered is not False)
        self.threshold = threshold or LOCKOUT_THRESHOLD
        self.duration = min(duration or LOCKOUT_DURATION_SECONDS, MAX_LOCKOUT_DURATION_SECONDS)
        # email -> {"failures": int, "locked_until": float}
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def is_locked(self, email: str) -> Tuple[bool, int]:
        normalized = email.strip().lower()
        now = time.time()
        with self._lock:
            rec = self.accounts.get(normalized)
            if not rec:
                return False, 0
            locked_until = rec.get("locked_until", 0.0)
            if now < locked_until:
                rem = max(1, int(locked_until - now))
                return True, rem
            # Lockout expired
            if locked_until > 0.0:
                rec["locked_until"] = 0.0
            return False, 0

    def record_failure(self, email: str) -> Tuple[bool, int]:
        normalized = email.strip().lower()
        now = time.time()
        with self._lock:
            rec = self.accounts.setdefault(normalized, {"failures": 0, "locked_until": 0.0})
            rec["failures"] += 1
            fails = rec["failures"]

            if self.tiered:
                if fails >= 10:
                    lock_time = MAX_LOCKOUT_DURATION_SECONDS  # 1 hour cap, temporary, never permanent
                    rec["locked_until"] = now + lock_time
                    logger.warning("Account %s locked for 1 hour (10+ failures, capped at 1h)", normalized)
                    return True, lock_time
                elif fails >= 5:
                    lock_time = 900
                    rec["locked_until"] = now + lock_time
                    logger.warning("Account %s locked for 15 min (>=5 failures)", normalized)
                    return True, lock_time
                elif fails >= 3:
                    lock_time = 60
                    rec["locked_until"] = now + lock_time
                    logger.warning("Account %s locked for 1 min (>=3 failures)", normalized)
                    return True, lock_time
                return False, 0
            else:
                if fails >= self.threshold:
                    lock_time = min(self.duration, MAX_LOCKOUT_DURATION_SECONDS)
                    rec["locked_until"] = now + lock_time
                    logger.warning("Account %s locked out due to %d consecutive failed logins", normalized, fails)
                    return True, lock_time
                return False, 0

    def record_success(self, email: str):
        normalized = email.strip().lower()
        with self._lock:
            if normalized in self.accounts:
                self.accounts[normalized] = {"failures": 0, "locked_until": 0.0}

    def admin_unlock(self, email: str) -> bool:
        """Unlock an account immediately, resetting failures and clearing lock expiration."""
        normalized = email.strip().lower()
        with self._lock:
            self.accounts[normalized] = {"failures": 0, "locked_until": 0.0}
            logger.info("Account %s unlocked by administrator", normalized)
            return True

    def unlock_all(self):
        """Unlock all tracked accounts."""
        with self._lock:
            self.accounts.clear()
            logger.info("All account lockouts cleared")
