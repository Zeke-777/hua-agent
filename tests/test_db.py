"""DB tests: token expiry (F9), table whitelist (F14), session CRUD."""
import time

import pytest

from hua_agent.db import (
    _ALLOWED_TABLES,
    _get_column_names,
    create_token,
    get_or_create_flower_session,
    init_meta_db,
    verify_session_ownership,
    verify_token,
)


# ============================================================================
# F9 — Token Expiry
# ============================================================================


class TestTokenExpiry:
    """Verify NULL expires_at is treated as expired."""

    def test_null_expiry_is_expired(self, db_conn):
        """Token with NULL expires_at should be rejected."""
        # Manually insert a token with NULL expires_at (simulating pre-migration)
        from hua_agent.db import now_iso

        db_conn.execute(
            "INSERT INTO tokens (token, username, created_at, expires_at) "
            "VALUES (?, ?, ?, NULL)",
            ("test_token_null", "alice", now_iso()),
        )
        db_conn.commit()

        # Should return None (expired)
        result = verify_token(db_conn, "test_token_null")
        assert result is None

    def test_valid_token(self, db_conn):
        """Token with future expiry returns username."""
        token = create_token(db_conn, "alice", expiry_days=7)
        result = verify_token(db_conn, token)
        assert result == "alice"

    def test_expired_token(self, db_conn):
        """Token with past expiry returns None."""
        token = create_token(db_conn, "alice", expiry_days=7)
        # Manually set expiry to past
        from hua_agent.db import now_iso

        db_conn.execute(
            "UPDATE tokens SET expires_at = ? WHERE token = ?",
            ("2020-01-01T00:00:00+00:00", token),
        )
        db_conn.commit()
        result = verify_token(db_conn, token)
        assert result is None

    def test_nonexistent_token(self, db_conn):
        """Nonexistent token returns None."""
        result = verify_token(db_conn, "nonexistent_token")
        assert result is None


# ============================================================================
# F14 — Table Whitelist
# ============================================================================


class TestTableWhitelist:
    """Verify _get_column_names rejects unlisted tables."""

    def test_allowed_table_sessions(self, db_conn):
        """'sessions' is in the whitelist."""
        cols = _get_column_names(db_conn, "sessions")
        assert "session_id" in cols
        assert "username" in cols

    def test_allowed_table_tokens(self, db_conn):
        """'tokens' is in the whitelist."""
        cols = _get_column_names(db_conn, "tokens")
        assert "token" in cols
        assert "username" in cols

    def test_sql_injection_attempt(self, db_conn):
        """SQL injection table name raises ValueError."""
        with pytest.raises(ValueError, match="不允许查询表"):
            _get_column_names(db_conn, "users; DROP TABLE users;--")

    def test_unlisted_table(self, db_conn):
        """Table not in whitelist raises ValueError."""
        with pytest.raises(ValueError):
            _get_column_names(db_conn, "users")


# ============================================================================
# F2 — Session Ownership (supplementary DB tests)
# ============================================================================


class TestSessionCRUD:
    """Basic session CRUD verification."""

    def test_create_session(self, db_conn):
        """Creating a new session returns is_new=True."""
        sid, is_new = get_or_create_flower_session(db_conn, "alice", "rose")
        assert is_new is True
        assert "alice" in sid
        assert "rose" in sid

    def test_get_existing_session(self, db_conn):
        """Getting an existing session returns is_new=False."""
        sid1, is_new1 = get_or_create_flower_session(db_conn, "alice", "rose")
        sid2, is_new2 = get_or_create_flower_session(db_conn, "alice", "rose")
        assert is_new1 is True
        assert is_new2 is False
        assert sid1 == sid2
