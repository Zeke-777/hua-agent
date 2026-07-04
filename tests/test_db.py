"""DB tests: full coverage of db.py functions."""

import json

import pytest

from hua_agent.db import (
    _get_column_names,
    create_token,
    delete_token,
    get_latest_session,
    get_or_create_flower_session,
    get_session_data,
    init_meta_db,
    list_sessions,
    login_user,
    register_user,
    update_last_active,
    update_session_flower_info,
    verify_session_ownership,
    verify_token,
)


# ============================================================================
# init_meta_db
# ============================================================================


class TestInitMetaDb:
    def test_init_empty_db(self, db_conn):
        """Tables are created on empty database."""
        tables = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = [r[0] for r in tables]
        assert "users" in names
        assert "sessions" in names
        assert "tokens" in names

    def test_init_idempotent(self, db_conn):
        """Repeated init_meta_db does not error."""
        init_meta_db(db_conn)  # second call
        tables = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert len(tables) >= 3

    def test_users_no_salt_column(self, db_conn):
        """After migration, users table has no salt column."""
        cols = [r[1] for r in db_conn.execute("PRAGMA table_info(users)").fetchall()]
        assert "salt" not in cols
        assert "password_hash" in cols


# ============================================================================
# Token management
# ============================================================================


class TestTokenManagement:
    def test_create_token_returns_64_hex(self, db_conn):
        """Token is 64 hex characters."""
        token = create_token(db_conn, "alice")
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_different_users_different_tokens(self, db_conn):
        """Different users get different tokens."""
        t1 = create_token(db_conn, "alice")
        t2 = create_token(db_conn, "bob")
        assert t1 != t2

    def test_verify_valid_token(self, db_conn):
        """Valid token returns username."""
        token = create_token(db_conn, "alice")
        assert verify_token(db_conn, token) == "alice"

    def test_verify_invalid_token(self, db_conn):
        """Invalid token returns None."""
        assert verify_token(db_conn, "invalid_token") is None

    def test_verify_null_expiry(self, db_conn):
        """Token with NULL expires_at is rejected."""
        from hua_agent.db import now_iso

        db_conn.execute(
            "INSERT INTO tokens (token, username, created_at, expires_at) "
            "VALUES (?, ?, ?, NULL)",
            ("null_expiry_token", "alice", now_iso()),
        )
        db_conn.commit()
        assert verify_token(db_conn, "null_expiry_token") is None

    def test_verify_expired_token(self, db_conn):
        """Expired token returns None."""
        token = create_token(db_conn, "alice")
        db_conn.execute(
            "UPDATE tokens SET expires_at = ? WHERE token = ?",
            ("2020-01-01T00:00:00+00:00", token),
        )
        db_conn.commit()
        assert verify_token(db_conn, token) is None

    def test_delete_token(self, db_conn):
        """Deleted token can no longer be verified."""
        token = create_token(db_conn, "alice")
        delete_token(db_conn, token)
        assert verify_token(db_conn, token) is None


# ============================================================================
# Session CRUD
# ============================================================================


class TestSessionCRUD:
    def test_create_new_session(self, db_conn):
        """New session returns is_new=True."""
        sid, is_new = get_or_create_flower_session(db_conn, "alice", "rose")
        assert is_new is True
        assert "alice" in sid
        assert "rose" in sid

    def test_get_existing_session(self, db_conn):
        """Existing session returns is_new=False."""
        sid1, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        sid2, is_new = get_or_create_flower_session(db_conn, "alice", "rose")
        assert is_new is False
        assert sid1 == sid2

    def test_session_with_image_url(self, db_conn):
        """Session creation stores image_url."""
        sid, is_new = get_or_create_flower_session(
            db_conn, "alice", "rose", image_url="http://example.com/img.jpg"
        )
        assert is_new is True
        img_url, _ = get_session_data(db_conn, sid)
        assert img_url == "http://example.com/img.jpg"

    def test_update_session_flower_info(self, db_conn):
        """Flower info is stored and retrieved correctly."""
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        info = {"名称": "玫瑰", "形态结构": "灌木"}
        update_session_flower_info(db_conn, sid, info)
        _, retrieved = get_session_data(db_conn, sid)
        assert retrieved == info

    def test_update_with_image_url(self, db_conn):
        """update_session_flower_info stores image_url."""
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        info = {"名称": "玫瑰"}
        update_session_flower_info(
            db_conn, sid, info, image_url="http://example.com/new.jpg"
        )
        img_url, retrieved = get_session_data(db_conn, sid)
        assert retrieved == info
        assert img_url == "http://example.com/new.jpg"

    def test_get_session_data_nonexistent(self, db_conn):
        """Non-existent session returns None, None."""
        img_url, info = get_session_data(db_conn, "nonexistent_session")
        assert img_url is None
        assert info is None

    def test_get_session_data_no_flower_info(self, db_conn):
        """Session without flower_info returns None for info."""
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        img_url, info = get_session_data(db_conn, sid)
        assert info is None

    def test_list_sessions(self, db_conn):
        """Multiple sessions listed in order."""
        get_or_create_flower_session(db_conn, "alice", "rose")
        get_or_create_flower_session(db_conn, "alice", "lily")
        sessions = list_sessions(db_conn, "alice")
        assert len(sessions) == 2
        assert sessions[0]["last_active"] >= sessions[1]["last_active"]

    def test_list_sessions_empty(self, db_conn):
        """Empty user returns empty list."""
        assert list_sessions(db_conn, "nobody") == []

    def test_list_sessions_includes_flower_info(self, db_conn):
        """Session list includes parsed flower_info."""
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        update_session_flower_info(db_conn, sid, {"名称": "玫瑰"})
        sessions = list_sessions(db_conn, "alice")
        assert sessions[0]["flower_info"] == {"名称": "玫瑰"}

    def test_get_latest_session(self, db_conn):
        """Latest session by last_active is returned."""
        get_or_create_flower_session(db_conn, "alice", "rose")
        import time
        time.sleep(0.01)
        get_or_create_flower_session(db_conn, "alice", "lily")
        latest = get_latest_session(db_conn, "alice")
        assert latest is not None
        assert "lily" in latest

    def test_get_latest_session_none(self, db_conn):
        """No sessions returns None."""
        assert get_latest_session(db_conn, "nobody") is None

    def test_update_last_active(self, db_conn):
        """update_last_active changes last_active timestamp."""
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        import time
        time.sleep(0.01)
        update_last_active(db_conn, sid)
        sessions = list_sessions(db_conn, "alice")
        # last_active should be updated (more recent than created_at)
        assert sessions[0]["last_active"] >= sessions[0]["created_at"]


# ============================================================================
# Session ownership
# ============================================================================


class TestSessionOwnership:
    def test_owns_own_session(self, db_conn):
        """User can access their own session."""
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        assert verify_session_ownership(db_conn, "alice", sid) is True

    def test_cannot_access_others(self, db_conn):
        """User cannot access another user's session."""
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        assert verify_session_ownership(db_conn, "bob", sid) is False

    def test_same_flower_different_users(self, db_conn):
        """Same flower name isolated across users."""
        sid1, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        sid2, _ = get_or_create_flower_session(db_conn, "bob", "rose")
        assert sid1 != sid2
        assert verify_session_ownership(db_conn, "alice", sid2) is False

    def test_nonexistent_session(self, db_conn):
        """Non-existent session returns False."""
        assert verify_session_ownership(db_conn, "alice", "nonexistent") is False


# ============================================================================
# Table whitelist
# ============================================================================


class TestTableWhitelist:
    def test_allowed_sessions(self, db_conn):
        """'sessions' is allowed."""
        cols = _get_column_names(db_conn, "sessions")
        assert "session_id" in cols
        assert "username" in cols

    def test_allowed_tokens(self, db_conn):
        """'tokens' is allowed."""
        cols = _get_column_names(db_conn, "tokens")
        assert "token" in cols
        assert "username" in cols

    def test_sql_injection_blocked(self, db_conn):
        """SQL injection in table name raises ValueError."""
        with pytest.raises(ValueError, match="不允许查询表"):
            _get_column_names(db_conn, "users; DROP TABLE users;--")

    def test_unlisted_table_blocked(self, db_conn):
        """Table not in whitelist raises ValueError."""
        with pytest.raises(ValueError):
            _get_column_names(db_conn, "users")


# ============================================================================
# Registration and login (db-level)
# ============================================================================


class TestRegistration:
    def test_register_success(self, db_conn):
        ok, msg = register_user(db_conn, "alice", "password123")
        assert ok is True

    def test_register_duplicate(self, db_conn):
        register_user(db_conn, "alice", "password123")
        ok, msg = register_user(db_conn, "alice", "another")
        assert ok is False

    def test_login_correct(self, db_conn):
        register_user(db_conn, "alice", "password123")
        username, msg = login_user(db_conn, "alice", "password123")
        assert username == "alice"

    def test_login_wrong_password(self, db_conn):
        register_user(db_conn, "alice", "password123")
        username, msg = login_user(db_conn, "alice", "wrong")
        assert username is None

    def test_login_nonexistent(self, db_conn):
        username, msg = login_user(db_conn, "nobody", "password123")
        assert username is None
