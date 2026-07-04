"""Security tests: path traversal and session ownership."""

import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hua_agent.db import (
    get_or_create_flower_session,
    register_user,
    verify_session_ownership,
)


# ============================================================================
# F1 — Path Traversal
# ============================================================================


class TestPathTraversal:
    @pytest.fixture
    def client(self):
        """Create a test app with SPA fallback and temporary static dir."""
        from hua_agent.app import create_app
        from hua_agent.config import Settings
        from hua_agent.spa import create_spa_fallback

        tmpdir = tempfile.mkdtemp()
        static_dist = os.path.join(tmpdir, "static", "dist")
        os.makedirs(static_dist, exist_ok=True)
        with open(os.path.join(static_dist, "index.html"), "w", encoding="utf-8") as f:
            f.write("<html><body>test</body></html>")
        os.makedirs(os.path.join(static_dist, "assets"), exist_ok=True)

        # Patch _PROJECT_ROOT to use temp dir for SPA fallback
        with patch("hua_agent.app._PROJECT_ROOT", tmpdir), \
             patch("hua_agent.spa._PROJECT_ROOT", tmpdir):
            settings = Settings(
                deepseek_api_key="test", tavily_api_key="test",
                ak="", sk="", endpoint="", bucket_name="",
            )
            app = FastAPI(title="Test App")

            @app.get("/")
            async def root():
                import os as _os
                from fastapi.responses import FileResponse
                return FileResponse(_os.path.join(tmpdir, "static", "dist", "index.html"))

            @app.get("/{path:path}")
            async def spa_fallback(path: str):
                return create_spa_fallback()(path)

            with TestClient(app) as c:
                yield c

    def test_normal_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_normal_spa_route(self, client):
        resp = client.get("/static/dist/index.html")
        assert resp.status_code == 200

    def test_dot_dot_starlette_normalizes(self, client):
        resp = client.get("/../../../etc/passwd")
        assert resp.status_code == 200  # falls back to index.html

    def test_double_slash_starlette_normalizes(self, client):
        resp = client.get("//windows/win.ini")
        assert resp.status_code == 200

    def test_encoded_backslash_rejected(self, client):
        import platform
        if platform.system() != "Windows":
            pytest.skip(r"%5C (\) is a path separator only on Windows")
        resp = client.get("/%5Cwindows%5Cwin.ini")
        assert resp.status_code == 404

    def test_drive_letter_rejected(self, client):
        import platform
        if platform.system() != "Windows":
            pytest.skip("C:/ is only an absolute path on Windows")
        resp = client.get("/C:/boot.ini")
        assert resp.status_code == 404


# ============================================================================
# Session Ownership
# ============================================================================


class TestSessionOwnership:
    def test_verify_ownership_same_user(self, db_conn):
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        assert verify_session_ownership(db_conn, "alice", sid) is True

    def test_verify_ownership_different_user(self, db_conn):
        sid, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        assert verify_session_ownership(db_conn, "bob", sid) is False

    def test_same_flower_different_user(self, db_conn):
        sid1, _ = get_or_create_flower_session(db_conn, "alice", "rose")
        sid2, _ = get_or_create_flower_session(db_conn, "bob", "rose")
        assert sid1 != sid2
        assert verify_session_ownership(db_conn, "alice", sid2) is False

    def test_nonexistent_session(self, db_conn):
        assert verify_session_ownership(db_conn, "alice", "nonexistent") is False

    def test_username_with_special_chars(self, db_conn):
        register_user(db_conn, "test.user-1", "password123")
        sid, _ = get_or_create_flower_session(db_conn, "test.user-1", "rose")
        assert verify_session_ownership(db_conn, "test.user-1", sid) is True
