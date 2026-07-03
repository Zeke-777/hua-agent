"""Auth tests: password hashing and migration (F3)."""
import hashlib
import secrets

import bcrypt
import pytest

from hua_agent.db import _hash_password, login_user, register_user


class TestPasswordHashing:
    """Verify bcrypt hashing (F3.1)."""

    def test_bcrypt_format(self):
        """Password hash is a valid bcrypt string."""
        h = _hash_password("testpassword")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_different_salts(self):
        """Same password twice produces different hashes (unique salt)."""
        h1 = _hash_password("testpassword")
        h2 = _hash_password("testpassword")
        assert h1 != h2

    def test_empty_password_rejected(self):
        """Empty password hashing still works (validation is at API level)."""
        h = _hash_password("")
        assert bcrypt.checkpw(b"", h.encode())


class TestPasswordMigration:
    """Verify legacy SHA-256 passwords are auto-upgraded (F3.2)."""

    def _insert_legacy_user(self, conn, username, password):
        """Insert a user with old-style SHA-256 hash."""
        salt = secrets.token_hex(16)
        pw_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, created_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (username, pw_hash, salt),
        )
        conn.commit()

    def test_login_upgrades_legacy_hash(self, db_conn):
        """Login with legacy SHA-256 hash auto-upgrades to bcrypt."""
        self._insert_legacy_user(db_conn, "legacy_user", "correct_password")

        # Login should succeed
        username, msg = login_user(db_conn, "legacy_user", "correct_password")
        assert username == "legacy_user"

        # Hash should now be bcrypt
        row = db_conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("legacy_user",)
        ).fetchone()
        assert row[0].startswith("$2b$") or row[0].startswith("$2a$")

    def test_legacy_wrong_password(self, db_conn):
        """Wrong password with legacy hash is rejected."""
        self._insert_legacy_user(db_conn, "legacy_user", "correct_password")
        username, msg = login_user(db_conn, "legacy_user", "wrong_password")
        assert username is None

    def test_bcrypt_user_login(self, db_conn):
        """New bcrypt user can login correctly."""
        register_user(db_conn, "new_user", "password123")
        username, msg = login_user(db_conn, "new_user", "password123")
        assert username == "new_user"

    def test_bcrypt_wrong_password(self, db_conn):
        """Wrong password for bcrypt user is rejected."""
        register_user(db_conn, "new_user", "password123")
        username, msg = login_user(db_conn, "new_user", "wrong_password")
        assert username is None
