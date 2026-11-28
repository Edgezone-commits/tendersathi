"""Shared fixtures for API tests.

`api_client` overrides the two app-level dependencies (db client, compiled
graph) with plain mocks instead of running the real `lifespan` -- that
would open a real Supabase/Postgres connection, which no test may do.
Individual routes still get their actual db-module calls checked by
patching `tendersathi.api.<module>.<name>_db` directly, same style as the
agent tests (e.g. `tests/agents/test_notifier.py`).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tendersathi.api.app import app
from tendersathi.api.deps import get_db_client, get_graph


@pytest.fixture
def mock_db_client():
    return MagicMock()


@pytest.fixture
def mock_graph():
    return MagicMock()


@pytest.fixture
def api_client(mock_db_client, mock_graph):
    app.dependency_overrides[get_db_client] = lambda: mock_db_client
    app.dependency_overrides[get_graph] = lambda: mock_graph
    yield TestClient(app)
    app.dependency_overrides.clear()
