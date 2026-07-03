"""Security tests: path traversal (F1) and session ownership (F2)."""
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from hua_agent.db import (
    create_token,
    get_or_create_flower_session,
    init_meta_db,
    register_user,
    verify_session_ownership,
)


# ============================================================================
# F1 — Path Traversal
# ============================================================================


class TestPathTraversal:
    """Verify spa_fallback rejects directory traversal attempts."""

    @pytest.fixture
    def client(self):
        """Create a test client with a temporary static directory."""
        import hua_agent.server as server_mod

        tmpdir = tempfile.mkdtemp()
        static_dist = os.path.join(tmpdir, "static", "dist")
        os.makedirs(static_dist, exist_ok=True)
        with open(os.path.join(static_dist, "index.html"), "w", encoding="utf-8") as f:
            f.write("<html><body>test</body></html>")

        # Also create a subdirectory to test valid SPA paths
        os.makedirs(os.path.join(static_dist, "assets"), exist_ok=True)

        old_root = server_mod._PROJECT_ROOT
        server_mod._PROJECT_ROOT = tmpdir

        with TestClient(server_mod.app) as c:
            yield c

        server_mod._PROJECT_ROOT = old_root

    def test_normal_index(self, client):
        """Normal request to root returns 200."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_normal_spa_route(self, client):
        """Normal SPA route returns index.html (200)."""
        resp = client.get("/static/dist/index.html")
        assert resp.status_code == 200

    def test_dot_dot_starlette_normalizes(self, client):
        """Starlette normalizes ../ so it becomes a safe SPA fallback (200)."""
        resp = client.get("/../../../etc/passwd")
        # Starlette strips .. before routing, path becomes "etc/passwd"
        # which is within static dir and falls back to index.html
        assert resp.status_code == 200

    def test_double_slash_starlette_normalizes(self, client):
        """Starlette normalizes // so it becomes a safe SPA fallback (200)."""
        resp = client.get("//windows/win.ini")
        # Starlette normalizes double slash, path becomes "windows/win.ini"
        assert resp.status_code == 200

    def test_encoded_backslash_rejected(self, client):
        """URL-encoded backslash traversal is rejected (404)."""
        resp = client.get("/%5Cwindows%5Cwin.ini")
        assert resp.status_code == 404

    def test_drive_letter_rejected(self, client):
        """Drive letter path (C:/boot.ini) is rejected — realpath check catches it."""
        # On Windows os.path.join with "C:/boot.ini" treats it as absolute
        # realpath resolves it to C:\boot.ini which doesn't start with static dir
        resp = client.get("/C:/boot.ini")
        assert resp.status_code == 404


# ============================================================================
# F2 — Session Ownership
# ============================================================================


class TestSessionOwnership:
    """Verify session ownership is verified via DB, not string matching."""

    def test_verify_ownership_same_user(self, db_conn):
        """User can access their own session."""
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        assert verify_session_ownership(db_conn, "alice", sid) is True

    def test_verify_ownership_different_user(self, db_conn):
        """User cannot access another user's session."""
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        assert verify_session_ownership(db_conn, "bob", sid) is False

    def test_verify_ownership_colon_in_name(self, db_conn):
        """Username with colon no longer creates ambiguity with DB lookup."""
        get_or_create_flower_session(db_conn, "alice", "evil:rose")
        sid2, _ = get_or_create_flower_session(db_conn, "bob", "rose")
        assert verify_session_ownership(db_conn, "alice", sid2) is False

    def test_same_flower_different_user(self, db_conn):
        """Same flower name for different users are isolated."""
        sid1, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        sid2, _ = get_or_create_flower_session(db_conn, "bob", "rose")
        assert sid1 != sid2
        assert verify_session_ownership(db_conn, "alice", sid1) is True
        assert verify_session_ownership(db_conn, "alice", sid2) is False
        assert verify_session_ownership(db_conn, "bob", sid2) is True

    def test_nonexistent_session(self, db_conn):
        """Nonexistent session returns False."""
        assert verify_session_ownership(db_conn, "alice", "nonexistent") is False

    def test_username_with_special_chars_session_owned(self, db_conn):
        """Username with dot/hyphen can still own sessions properly."""
        register_user(db_conn, "test.user-1", "password123")
        sid, _ = get_or_create_flower_session(db_conn, "test.user-1", "rose")
        assert verify_session_ownership(db_conn, "test.user-1", sid) is True
