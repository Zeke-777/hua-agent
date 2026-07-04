import functools
import logging
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import bcrypt

_db_lock = threading.Lock()

_logger = logging.getLogger(__name__)


def _locked(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _db_lock:
            return func(*args, **kwargs)
    return wrapper


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str) -> str:
    """Hash password using bcrypt. Returns bcrypt hash string."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


_ALLOWED_TABLES = {"sessions", "tokens"}


def _get_column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"不允许查询表: {table}")
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


# ============================================================================
# Database init
# ============================================================================


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def init_meta_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT ''
        )
    """)
    # Migrate: drop salt column if it exists (bcrypt stores salt internally)
    users_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "salt" in users_cols:
        # SQLite doesn't support DROP COLUMN well in older versions; rebuild table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users_new (
                username      TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL DEFAULT '',
                created_at    TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO users_new (username, password_hash, created_at) "
            "SELECT username, password_hash, created_at FROM users"
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_new RENAME TO users")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            username    TEXT NOT NULL,
            name        TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            last_active TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            token      TEXT PRIMARY KEY,
            username   TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Non-destructive migrations: add columns that may be missing
    sessions_cols = _get_column_names(conn, "sessions")
    for col, col_type in [("image_url", "TEXT"), ("flower_info", "TEXT")]:
        if col not in sessions_cols:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {col_type} DEFAULT NULL")

    tokens_cols = _get_column_names(conn, "tokens")
    if "expires_at" not in tokens_cols:
        conn.execute("ALTER TABLE tokens ADD COLUMN expires_at TEXT DEFAULT NULL")

    # Migrate NULL expires_at tokens: set to 7 days from now
    conn.execute(
        "UPDATE tokens SET expires_at = ? WHERE expires_at IS NULL",
        ((datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),),
    )
    # Clean up expired tokens on startup
    conn.execute(
        "DELETE FROM tokens WHERE expires_at IS NOT NULL AND expires_at < ?",
        (now_iso(),),
    )

    conn.commit()


# ============================================================================
# User auth
# ============================================================================


@_locked
def register_user(conn: sqlite3.Connection, username: str, password: str) -> tuple[bool, str]:
    existing = conn.execute(
        "SELECT 1 FROM users WHERE username = ?", (username,)
    ).fetchone()
    if existing:
        return False, "用户名已存在"

    password_hash = _hash_password(password)
    conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, password_hash, now_iso()),
    )
    conn.commit()
    return True, "注册成功"


@_locked
def login_user(conn: sqlite3.Connection, username: str, password: str) -> tuple[str | None, str]:
    row = conn.execute(
        "SELECT password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    if not row:
        return None, "用户不存在"

    stored_hash = row[0]
    if bcrypt.checkpw(password.encode(), stored_hash.encode()):
        return username, "登录成功"
    return None, "密码错误"


# ============================================================================
# Token management
# ============================================================================


@_locked
def create_token(conn: sqlite3.Connection, username: str, expiry_days: int = 7) -> str:
    token = secrets.token_hex(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat()
    conn.execute(
        "INSERT INTO tokens (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, username, now_iso(), expires_at),
    )
    conn.commit()
    return token


@_locked
def verify_token(conn: sqlite3.Connection, token: str) -> str | None:
    row = conn.execute(
        "SELECT username, expires_at FROM tokens WHERE token = ?", (token,)
    ).fetchone()
    if not row:
        return None
    expires_at = row[1]
    # NULL expiry = treat as expired (defense in depth)
    if expires_at is None or expires_at < now_iso():
        return None
    return row[0]


@_locked
def delete_token(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
    conn.commit()


# ============================================================================
# Session management
# ============================================================================


@_locked
def list_sessions(conn: sqlite3.Connection, username: str) -> list[dict]:
    import json
    rows = conn.execute(
        "SELECT session_id, name, created_at, last_active, image_url, flower_info "
        "FROM sessions WHERE username = ? ORDER BY last_active DESC",
        (username,),
    ).fetchall()
    result = []
    for r in rows:
        fi = r[5]
        if fi:
            try:
                parsed = json.loads(fi)
            except (json.JSONDecodeError, TypeError):
                parsed = None
        else:
            parsed = None
        result.append({
            "session_id": r[0], "name": r[1], "created_at": r[2], "last_active": r[3],
            "image_url": r[4],
            "flower_info": parsed,
        })
    return result


@_locked
def get_or_create_flower_session(
    conn: sqlite3.Connection, username: str, flower_name: str,
    image_url: str | None = None,
) -> tuple[str, bool]:
    session_id = f"{username}:{flower_name}"
    existing = conn.execute(
        "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if existing:
        _update_last_active_locked(conn, session_id)
        if image_url:
            conn.execute(
                "UPDATE sessions SET image_url = ? WHERE session_id = ?",
                (image_url, session_id),
            )
            conn.commit()
        return session_id, False
    conn.execute(
        "INSERT INTO sessions (session_id, username, name, created_at, last_active, image_url) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, username, flower_name, now_iso(), now_iso(), image_url),
    )
    conn.commit()
    return session_id, True


@_locked
def update_session_flower_info(
    conn: sqlite3.Connection, session_id: str, flower_info: dict,
    image_url: str | None = None,
) -> None:
    import json
    cols = ["flower_info = ?"]
    vals: list = [json.dumps(flower_info, ensure_ascii=False)]
    if image_url:
        cols.append("image_url = ?")
        vals.append(image_url)
    vals.append(session_id)
    conn.execute(
        f"UPDATE sessions SET {', '.join(cols)} WHERE session_id = ?",
        vals,
    )
    conn.commit()


@_locked
def update_last_active(conn: sqlite3.Connection, session_id: str) -> None:
    _update_last_active_locked(conn, session_id)


def _update_last_active_locked(conn: sqlite3.Connection, session_id: str) -> None:
    """Internal: caller must hold _db_lock."""
    conn.execute(
        "UPDATE sessions SET last_active = ? WHERE session_id = ?",
        (now_iso(), session_id),
    )
    conn.commit()


@_locked
def get_session_data(conn: sqlite3.Connection, session_id: str) -> tuple[str | None, dict | None]:
    import json
    row = conn.execute(
        "SELECT image_url, flower_info FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return None, None
    fi = row[1]
    if fi:
        try:
            return row[0], json.loads(fi)
        except (json.JSONDecodeError, TypeError):
            return row[0], None
    return row[0], None


@_locked
def get_latest_session(conn: sqlite3.Connection, username: str) -> str | None:
    row = conn.execute(
        "SELECT session_id FROM sessions WHERE username = ? ORDER BY last_active DESC LIMIT 1",
        (username,),
    ).fetchone()
    return row[0] if row else None


@_locked
def verify_session_ownership(conn: sqlite3.Connection, username: str, session_id: str) -> bool:
    """Verify that a session belongs to the given user via DB lookup."""
    row = conn.execute(
        "SELECT 1 FROM sessions WHERE username = ? AND session_id = ?",
        (username, session_id),
    ).fetchone()
    return row is not None
