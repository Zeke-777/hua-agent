"""Auth tests: registration, login, password hashing."""

import bcrypt
import pytest

from hua_agent.db import _hash_password, login_user, register_user


class TestPasswordHashing:
    """Verify bcrypt hashing."""

    def test_bcrypt_format(self):
        """Password hash is a valid bcrypt string."""
        h = _hash_password("testpassword")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_different_salts(self):
        """Same password twice produces different hashes (unique salt)."""
        h1 = _hash_password("testpassword")
        h2 = _hash_password("testpassword")
        assert h1 != h2

    def test_empty_password(self):
        """Empty password hashing still works (validation is at API level)."""
        h = _hash_password("")
        assert bcrypt.checkpw(b"", h.encode())


class TestRegistration:
    """Verify user registration."""

    def test_register_success(self, db_conn):
        """New user registers successfully."""
        ok, msg = register_user(db_conn, "alice", "password123")
        assert ok is True
        assert "成功" in msg

    def test_register_duplicate(self, db_conn):
        """Duplicate username is rejected."""
        register_user(db_conn, "alice", "password123")
        ok, msg = register_user(db_conn, "alice", "another_password")
        assert ok is False
        assert "已存在" in msg

    def test_register_special_chars(self, db_conn):
        """Username with allowed special characters works."""
        ok, msg = register_user(db_conn, "user.name-1@test", "password123")
        assert ok is True

    def test_password_stored_as_bcrypt(self, db_conn):
        """Registered user password is stored as bcrypt."""
        register_user(db_conn, "alice", "password123")
        row = db_conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("alice",)
        ).fetchone()
        assert row[0].startswith("$2b$") or row[0].startswith("$2a$")


class TestLogin:
    """Verify user login."""

    def test_login_success(self, db_conn):
        """Correct password returns username."""
        register_user(db_conn, "alice", "password123")
        username, msg = login_user(db_conn, "alice", "password123")
        assert username == "alice"
        assert msg == "登录成功"

    def test_login_wrong_password(self, db_conn):
        """Wrong password returns None."""
        register_user(db_conn, "alice", "password123")
        username, msg = login_user(db_conn, "alice", "wrong_password")
        assert username is None
        assert "错误" in msg

    def test_login_nonexistent_user(self, db_conn):
        """Non-existent user returns None."""
        username, msg = login_user(db_conn, "nobody", "password123")
        assert username is None
        assert "不存在" in msg
