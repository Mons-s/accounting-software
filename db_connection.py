"""
Database connection abstraction layer.

Tries PostgreSQL (Supabase, `accounting` schema) first; falls back to
local SQLite when the cloud is unreachable, so billing works offline.

Usage
-----
    # At app startup, after loading config:
    import db_connection
    cfg = load_config()
    if cfg.get("pg_url") and cfg.get("shop_id"):
        db_connection.configure(cfg["pg_url"], cfg["shop_id"])

    # Everywhere else — unchanged from before:
    conn = db_connection.get_connection()
    # ... use conn exactly like a sqlite3 connection
"""

import os
import sqlite3
import sys
import threading
from typing import Optional

if getattr(sys, "frozen", False):
    _app_dir = os.path.dirname(sys.executable)
else:
    _app_dir = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(_app_dir, "accounting.db")

_pg_url: Optional[str] = None
_shop_id: Optional[str] = None
_cloud_ok: Optional[bool] = None   # None = untested
_lock = threading.Lock()


def configure(pg_url: str, shop_id: str) -> None:
    """Call once at startup with the PostgreSQL URL and this shop's UUID."""
    global _pg_url, _shop_id, _cloud_ok
    _pg_url = pg_url
    _shop_id = shop_id
    _cloud_ok = None  # re-probe on next connect


def is_cloud() -> bool:
    """True if the last successful get_connection() used PostgreSQL."""
    return _cloud_ok is True


# ---------------------------------------------------------------------------
# PostgreSQL cursor wrapper
# ---------------------------------------------------------------------------

class _PgCursor:
    """
    Wraps a psycopg2 RealDictCursor so it behaves like sqlite3.Cursor:
    - Accepts '?' placeholders (converts to '%s' for PostgreSQL)
    - Provides .lastrowid via RETURNING id on INSERT
    - fetchone() / fetchall() return dict-like rows
    """

    def __init__(self, cur):
        self._cur = cur
        self._lastrowid: Optional[int] = None

    def execute(self, query: str, params=()):
        query = query.replace("?", "%s")
        # Auto-append RETURNING id to bare INSERTs so .lastrowid works
        stripped = query.lstrip().upper()
        if stripped.startswith("INSERT") and "RETURNING" not in stripped:
            query = query.rstrip().rstrip(";") + " RETURNING id"
            self._cur.execute(query, params)
            row = self._cur.fetchone()
            self._lastrowid = row["id"] if row else None
        else:
            self._cur.execute(query, params)
            self._lastrowid = None
        return self

    def executemany(self, query: str, params_seq):
        query = query.replace("?", "%s")
        self._cur.executemany(query, params_seq)

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        rows = self._cur.fetchall() or []
        return [dict(r) for r in rows]

    @property
    def lastrowid(self) -> Optional[int]:
        return self._lastrowid

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def close(self):
        self._cur.close()

    def __iter__(self):
        for row in self._cur:
            yield dict(row)


# ---------------------------------------------------------------------------
# PostgreSQL connection wrapper
# ---------------------------------------------------------------------------

class _PgConnection:
    """
    Wraps a psycopg2 connection to look like sqlite3.Connection.
    is_pg = True lets callers (initialize_db, _migrate_db) skip
    SQLite-specific code such as PRAGMA and executescript.
    """
    is_pg = True

    def __init__(self, conn):
        self._conn = conn

    def cursor(self) -> _PgCursor:
        import psycopg2.extras
        return _PgCursor(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))

    def execute(self, query: str, params=()):
        """Shortcut matching sqlite3.Connection.execute()."""
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def executescript(self, _sql: str):
        """No-op: PostgreSQL schema is managed in Supabase, not here."""

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # Context-manager support (matches sqlite3: commits on success)
    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_connection():
    """
    Return a database connection.

    Prefers PostgreSQL (Supabase) when configured; falls back to local
    SQLite automatically.  The returned object has the same interface as
    sqlite3.Connection so database.py works without query changes.
    """
    global _cloud_ok

    if _pg_url and _shop_id:
        try:
            import psycopg2
            with _lock:
                conn = psycopg2.connect(_pg_url, connect_timeout=5)
            cur = conn.cursor()
            # Set schema search path so queries find `accounting.*` tables
            cur.execute("SET search_path TO accounting, public")
            # Store shop context for the trigger / future RLS policies
            cur.execute("SET app.shop_id = %s", (_shop_id,))
            conn.commit()
            cur.close()
            _cloud_ok = True
            return _PgConnection(conn)
        except Exception:
            _cloud_ok = False
            # Fall through to SQLite

    _cloud_ok = False
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
