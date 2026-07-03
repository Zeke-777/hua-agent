"""Shared test fixtures."""
import sqlite3

import pytest

from hua_agent.db import init_meta_db


@pytest.fixture
def db_conn():
    """Create a fresh in-memory SQLite database for each test."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_meta_db(conn)
    yield conn
    conn.close()
