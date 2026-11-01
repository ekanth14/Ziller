"""Administrative Command-Line Interface for user account management and lockouts."""
import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cryptoscope.auth.store import AuthStore
from cryptoscope.auth.security import hash_password


def cmd_unlock(email: str, db_path: str = None):
    store = AuthStore(Path(db_path) if db_path else None)
    user = store.get_user_by_email(email)
    if not user:
        print(f"[ERROR] User with email '{email}' not found in database.")
        sys.exit(1)
    
    success = store.unlock_user_by_email(email)
    if success:
        print(f"[OK] Account '{email}' successfully unlocked. (Role: {user['role']})")
    else:
        print(f"[WARN] Account '{email}' was already active.")


def cmd_list_users(db_path: str = None):
    store = AuthStore(Path(db_path) if db_path else None)
    with store._lock:
        conn = store._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, email, role, must_change_password, disabled, created_at, last_login FROM users ORDER BY id ASC")
            users = cur.fetchall()
        finally:
            conn.close()

    print(f"\n{'ID':<4} {'EMAIL':<30} {'ROLE':<10} {'DISABLED':<10} {'PW_RESET_REQ':<14} {'LAST_LOGIN'}")
    print("-" * 80)
    for u in users:
        last_log = time.ctime(u["last_login"]) if u["last_login"] else "Never"
        print(f"{u['id']:<4} {u['email']:<30} {u['role']:<10} {str(bool(u['disabled'])):<10} {str(bool(u['must_change_password'])):<14} {last_log}")
    print(f"\nTotal users: {len(users)}\n")


def cmd_reset_password(email: str, new_password: str, db_path: str = None):
    if len(new_password) < 8:
        print("[ERROR] Password must be at least 8 characters long.")
        sys.exit(1)
    store = AuthStore(Path(db_path) if db_path else None)
    user = store.get_user_by_email(email)
    if not user:
        print(f"[ERROR] User with email '{email}' not found.")
        sys.exit(1)
    store.change_password(user["id"], new_password)
    print(f"[OK] Password for '{email}' has been reset with scrypt (N=2^17, r=8, p=1).")


def main():
    parser = argparse.ArgumentParser(description="ZILLERS Account Administration & Unlock CLI")
    parser.add_argument("--db", type=str, default=None, help="Path to users.db (optional)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # unlock
    unlock_parser = subparsers.add_parser("unlock", help="Unlock any user or admin account")
    unlock_parser.add_argument("email", type=str, help="Email address of the account to unlock")

    # list-users
    subparsers.add_parser("list-users", help="List all registered accounts")

    # reset-password
    pw_parser = subparsers.add_parser("reset-password", help="Reset password for an account")
    pw_parser.add_argument("email", type=str, help="Email address")
    pw_parser.add_argument("new_password", type=str, help="New password (min 8 chars)")

    args = parser.parse_args()
    if args.command == "unlock":
        cmd_unlock(args.email, args.db)
    elif args.command == "list-users":
        cmd_list_users(args.db)
    elif args.command == "reset-password":
        cmd_reset_password(args.email, args.new_password, args.db)


if __name__ == "__main__":
    main()
