"""Persistent SQLite WAL-mode user, session, password reset, and settings store."""
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from cryptoscope.auth.security import hash_password, hash_token, generate_session_token

DEFAULT_USERS_DB = Path(__file__).resolve().parents[2] / "work/runtime/users.db"
SESSION_LIFETIME_SECONDS = 12 * 3600  # 12 hours
RESET_TOKEN_LIFETIME_SECONDS = 3600    # 1 hour


class AuthStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_USERS_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'user',
                        must_change_password INTEGER NOT NULL DEFAULT 0,
                        disabled INTEGER NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        token_hash TEXT UNIQUE NOT NULL,
                        csrf_token TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS password_resets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        token_hash TEXT UNIQUE NOT NULL,
                        expires_at REAL NOT NULL,
                        used INTEGER NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS watchlists (
                        user_id INTEGER NOT NULL,
                        symbol TEXT NOT NULL,
                        is_favorite INTEGER NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        PRIMARY KEY (user_id, symbol),
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INTEGER PRIMARY KEY,
                        display_currency TEXT NOT NULL DEFAULT 'USD',
                        theme TEXT NOT NULL DEFAULT 'dark',
                        updated_at REAL NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def bootstrap_admin(self, admin_email: str = "admin@zillers.local") -> Optional[int]:
        """Bootstrap default administrator. Fails startup if ADMIN_INITIAL_PASSWORD is unset."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
                existing = cur.fetchone()
                if existing:
                    return existing[0]

                # No admin exists yet: require explicit environment variable
                initial_pwd = os.environ.get("ADMIN_INITIAL_PASSWORD", "").strip()
                if not initial_pwd:
                    raise RuntimeError(
                        "Startup failed: ADMIN_INITIAL_PASSWORD environment variable must be explicitly "
                        "set to bootstrap the administrator account. No default passwords permitted."
                    )
                if len(initial_pwd) < 10:
                    raise RuntimeError(
                        "Startup failed: ADMIN_INITIAL_PASSWORD must be at least 10 characters long."
                    )

                now = time.time()
                phash = hash_password(initial_pwd)
                cur.execute("""
                    INSERT INTO users (email, password_hash, role, must_change_password, disabled, created_at, updated_at)
                    VALUES (?, ?, 'admin', 1, 0, ?, ?)
                """, (admin_email.strip().lower(), phash, now, now))
                admin_id = cur.lastrowid
                # Seed default user settings
                cur.execute("""
                    INSERT INTO user_settings (user_id, display_currency, theme, updated_at)
                    VALUES (?, 'USD', 'dark', ?)
                """, (admin_id, now))
                conn.commit()
                return admin_id
            finally:
                conn.close()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM users WHERE email = ? LIMIT 1", (email.strip().lower(),))
                row = cur.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (user_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def create_user(self, email: str, password: str, role: str = "user", invite_code: Optional[str] = None) -> int:
        signup_mode = os.environ.get("SIGNUP_MODE", "open").lower()
        if signup_mode == "invite":
            expected_code = os.environ.get("INVITE_CODE", "").strip()
            if not expected_code or invite_code != expected_code:
                raise ValueError("Registration is invite-only. A valid invite code is required.")

        normalized_email = email.strip().lower()
        if "@" not in normalized_email or len(normalized_email) < 5:
            raise ValueError("Valid email address is required")

        phash = hash_password(password)
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO users (email, password_hash, role, must_change_password, disabled, created_at, updated_at)
                    VALUES (?, ?, ?, 0, 0, ?, ?)
                """, (normalized_email, phash, role, now, now))
                user_id = cur.lastrowid
                cur.execute("""
                    INSERT INTO user_settings (user_id, display_currency, theme, updated_at)
                    VALUES (?, 'USD', 'dark', ?)
                """, (user_id, now))
                conn.commit()
                return user_id
            except sqlite3.IntegrityError:
                raise ValueError("An account with this email address already exists.")
            finally:
                conn.close()

    def create_session(self, user_id: int) -> Tuple[str, str]:
        raw_token, csrf_token = generate_session_token()
        thash = hash_token(raw_token)
        now = time.time()
        expires = now + SESSION_LIFETIME_SECONDS
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO sessions (user_id, token_hash, csrf_token, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, thash, csrf_token, now, expires))
                conn.commit()
                return raw_token, csrf_token
            finally:
                conn.close()

    def validate_session(self, raw_token: str) -> Optional[Dict[str, Any]]:
        if not raw_token:
            return None
        thash = hash_token(raw_token)
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT s.id as session_id, s.csrf_token, s.expires_at,
                           u.id as user_id, u.email, u.role, u.must_change_password, u.disabled
                    FROM sessions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.token_hash = ? AND s.expires_at > ?
                """, (thash, now))
                row = cur.fetchone()
                if not row or row["disabled"]:
                    return None
                return dict(row)
            finally:
                conn.close()

    def revoke_session(self, raw_token: str):
        if not raw_token:
            return
        thash = hash_token(raw_token)
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (thash,))
                conn.commit()
            finally:
                conn.close()

    def change_password(self, user_id: int, new_password: str):
        phash = hash_password(new_password)
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ?
                    WHERE id = ?
                """, (phash, now, user_id))
                # Invalidate existing sessions on password change
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
                conn.commit()
            finally:
                conn.close()

    def create_password_reset(self, email: str) -> Optional[Tuple[str, str]]:
        user = self.get_user_by_email(email)
        if not user:
            return None
        raw_reset_token, _ = generate_session_token()
        thash = hash_token(raw_reset_token)
        now = time.time()
        expires = now + RESET_TOKEN_LIFETIME_SECONDS
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT INTO password_resets (user_id, token_hash, expires_at, used, created_at)
                    VALUES (?, ?, ?, 0, ?)
                """, (user["id"], thash, expires, now))
                conn.commit()
                return raw_reset_token, user["email"]
            finally:
                conn.close()

    def execute_password_reset(self, raw_reset_token: str, new_password: str) -> bool:
        thash = hash_token(raw_reset_token)
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, user_id FROM password_resets
                    WHERE token_hash = ? AND expires_at > ? AND used = 0
                """, (thash, now))
                rec = cur.fetchone()
                if not rec:
                    return False
                reset_id, user_id = rec["id"], rec["user_id"]
                phash = hash_password(new_password)
                cur.execute("UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE id = ?", (phash, now, user_id))
                cur.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (reset_id,))
                cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
                conn.commit()
                return True
            finally:
                conn.close()

    def get_favorites(self, user_id: int) -> List[str]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT symbol FROM watchlists WHERE user_id = ? AND is_favorite = 1", (user_id,))
                return [r["symbol"] for r in cur.fetchall()]
            finally:
                conn.close()

    def toggle_favorite(self, user_id: int, symbol: str) -> bool:
        sym = symbol.strip().upper()
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT is_favorite FROM watchlists WHERE user_id = ? AND symbol = ?", (user_id, sym))
                row = cur.fetchone()
                if row:
                    new_val = 0 if row["is_favorite"] == 1 else 1
                    cur.execute("UPDATE watchlists SET is_favorite = ? WHERE user_id = ? AND symbol = ?", (new_val, user_id, sym))
                    conn.commit()
                    return bool(new_val)
                else:
                    cur.execute("INSERT INTO watchlists (user_id, symbol, is_favorite, created_at) VALUES (?, ?, 1, ?)", (user_id, sym, now))
                    conn.commit()
                    return True
            finally:
                conn.close()

    def get_settings(self, user_id: int) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT display_currency, theme FROM user_settings WHERE user_id = ?", (user_id,))
                row = cur.fetchone()
                return dict(row) if row else {"display_currency": "USD", "theme": "dark"}
            finally:
                conn.close()

    def update_settings(self, user_id: int, display_currency: str = "USD", theme: str = "dark"):
        now = time.time()
        curr = display_currency.upper() if display_currency in {"USD", "INR"} else "USD"
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT INTO user_settings (user_id, display_currency, theme, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET display_currency = excluded.display_currency, theme = excluded.theme, updated_at = excluded.updated_at
                """, (user_id, curr, theme, now))
                conn.commit()
            finally:
                conn.close()
