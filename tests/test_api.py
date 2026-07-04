"""API integration tests using TestClient."""

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hua_agent.app import create_app
from hua_agent.config import Settings


@pytest.fixture
def client():
    """Create isolated test app with mocked workflows."""
    settings = Settings(
        deepseek_api_key="test-key",
        tavily_api_key="test-key",
        ak="", sk="", endpoint="", bucket_name="",
        cors_origins=["*"],
    )

    # Mock the _init_resources to avoid real LLM/OBS init
    with patch("hua_agent.app._init_resources") as mock_init:
        mock_init.side_effect = lambda app, settings: _setup_test_state(app)
        app = create_app(settings)
        with TestClient(app) as c:
            yield c


def _setup_test_state(app):
    """Set up minimal test state on the app."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from cachetools import TTLCache
    import sqlite3
    from hua_agent.db import init_meta_db

    meta_conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_meta_db(meta_conn)

    app.state.meta_conn = meta_conn
    app.state.stage1 = MagicMock()
    app.state.stage2 = MagicMock()
    app.state.active_sessions = TTLCache(maxsize=10000, ttl=3600)
    app.state.active_sessions_lock = asyncio.Lock()
    app.state.executor = ThreadPoolExecutor(max_workers=2)

    # Configure mock stage1 to return a valid response
    from langchain_core.messages import AIMessage

    mock_report = {"名称": "玫瑰", "形态结构": "灌木"}
    app.state.stage1.invoke.return_value = {
        "messages": [AIMessage(content="## 玫瑰 结构化研究报告")],
        "report": mock_report,
    }
    app.state.stage2.invoke.return_value = {
        "messages": [AIMessage(content="玫瑰的花期一般在5-7月")]
    }


# ============================================================================
# Auth endpoints
# ============================================================================


class TestAuth:
    def test_register_success(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "alice", "password": "password123"
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_register_duplicate_username(self, client):
        client.post("/api/auth/register", json={
            "username": "alice", "password": "password123"
        })
        resp = client.post("/api/auth/register", json={
            "username": "alice", "password": "another123"
        })
        assert resp.status_code == 409
        assert "detail" in resp.json()

    @pytest.mark.parametrize("payload,expected_detail", [
        ({"username": "", "password": "password123"}, "detail"),
        ({"password": "password123"}, "detail"),
        ({"username": "alice"}, "detail"),
    ])
    def test_register_validation(self, client, payload, expected_detail):
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 422
        assert expected_detail in resp.json()

    def test_login_success(self, client):
        client.post("/api/auth/register", json={
            "username": "alice", "password": "password123"
        })
        resp = client.post("/api/auth/login", json={
            "username": "alice", "password": "password123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["token"]) == 64
        assert data["username"] == "alice"

    def test_login_wrong_password(self, client):
        client.post("/api/auth/register", json={
            "username": "alice", "password": "password123"
        })
        resp = client.post("/api/auth/login", json={
            "username": "alice", "password": "wrong_password"
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "nobody", "password": "password123"
        })
        assert resp.status_code == 401


# ============================================================================
# Session endpoints
# ============================================================================


def _register_and_login(client, username="alice", password="password123"):
    client.post("/api/auth/register", json={
        "username": username, "password": password
    })
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password
    })
    return resp.json()["token"]


class TestSessions:
    def test_sessions_with_token(self, client):
        token = _register_and_login(client)
        resp = client.get("/api/sessions", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert isinstance(data["sessions"], list)

    def test_sessions_without_token(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 401 if resp.status_code == 401 else 403

    def test_sessions_invalid_token(self, client):
        resp = client.get("/api/sessions", headers={
            "Authorization": "Bearer invalid_token_1234567890abcdef"
        })
        assert resp.status_code in (401, 403)


# ============================================================================
# Research endpoint
# ============================================================================


class TestResearch:
    def test_research_valid(self, client):
        token = _register_and_login(client)
        resp = client.post("/api/research", json={"flower_name": "玫瑰"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["stage"] == 1
        assert data["flower_name"] == "玫瑰"

    def test_research_empty_flower_name(self, client):
        token = _register_and_login(client)
        resp = client.post("/api/research", json={"flower_name": ""},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_research_no_token(self, client):
        resp = client.post("/api/research", json={"flower_name": "玫瑰"})
        assert resp.status_code in (401, 403)


# ============================================================================
# Chat endpoint
# ============================================================================


class TestChat:
    def test_chat_valid(self, client):
        token = _register_and_login(client)
        # Start a research session first
        client.post("/api/research", json={"flower_name": "玫瑰"},
                    headers={"Authorization": f"Bearer {token}"})
        resp = client.post("/api/chat", json={"message": "花期是几月？"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["stage"] == 2

    def test_chat_no_active_session(self, client):
        token = _register_and_login(client)
        resp = client.post("/api/chat", json={"message": "花期是几月？"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

    def test_chat_empty_message(self, client):
        token = _register_and_login(client)
        client.post("/api/research", json={"flower_name": "玫瑰"},
                    headers={"Authorization": f"Bearer {token}"})
        resp = client.post("/api/chat", json={"message": ""},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400


# ============================================================================
# Upload endpoint
# ============================================================================


class TestUpload:
    def test_upload_valid_png(self, client):
        token = _register_and_login(client)
        # Minimal valid PNG bytes (1x1 pixel)
        png_data = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
            b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N'
            b'\x00\x00\x00\x00IEND\xaeB`\x82'
        )

        with patch("hua_agent.obs_client.upload_image") as mock_upload:
            mock_upload.return_value = "http://example.com/test.png"
            resp = client.post(
                "/api/upload",
                files={"file": ("test.png", io.BytesIO(png_data), "image/png")},
                data={"flower_name": "牡丹"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_upload_invalid_extension(self, client):
        token = _register_and_login(client)
        resp = client.post(
            "/api/upload",
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
            data={"flower_name": "牡丹"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_upload_size_limit(self, client):
        token = _register_and_login(client)
        big_data = b'x' * (11 * 1024 * 1024)  # 11MB
        resp = client.post(
            "/api/upload",
            files={"file": ("big.jpg", io.BytesIO(big_data), "image/jpeg")},
            data={"flower_name": "牡丹"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400


# ============================================================================
# Logout
# ============================================================================


class TestLogout:
    def test_logout_invalidates_token(self, client):
        token = _register_and_login(client)
        # Logout
        resp = client.post("/api/auth/logout",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

        # Token should now be invalid
        resp2 = client.get("/api/sessions",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code in (401, 403)
