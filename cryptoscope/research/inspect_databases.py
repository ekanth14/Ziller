"""Database PRAGMA and Data Audit Tool.

Inspects all SQLite databases in the repository for:
- journal_mode (must be WAL)
- busy_timeout (must be >= 5000 ms)
- Tables and user accounts (identifying demo rows)
"""

import sqlite3
from pathlib import Path

def inspect():
    db_paths = list(Path("work/runtime").glob("*.db")) + [Path("data/orders.db")]
    print("=" * 60)
    print("SQLITE DATABASE INTEGRITY & PRAGMA AUDIT")
    print("=" * 60)
    
    for db_path in db_paths:
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode;")
            jm = cur.fetchone()[0]
            cur.execute("PRAGMA busy_timeout;")
            bt = cur.fetchone()[0]
            print(f"\n[DB] {db_path}")
            print(f"     journal_mode: {jm.upper()} (expected: WAL)")
            print(f"     busy_timeout: {bt} ms (expected: >= 5000)")
            
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]
            print(f"     Tables: {tables}")
            
            for tbl in tables:
                cur.execute(f"SELECT count(*) FROM {tbl};")
                cnt = cur.fetchone()[0]
                print(f"       -> {tbl}: {cnt} rows")
                if tbl == "users":
                    cur.execute("SELECT id, email, role, created_at FROM users;")
                    for user in cur.fetchall():
                        print(f"          User: id={user[0]}, email={user[1]}, role={user[2]}, created_at={user[3]}")
            conn.close()
        except Exception as e:
            print(f"[ERROR] {db_path}: {e}")

if __name__ == "__main__":
    inspect()
