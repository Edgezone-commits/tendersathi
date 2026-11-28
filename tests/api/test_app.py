"""Tests for the app-level /health route, which touches no dependency.

Deliberately doesn't use the `api_client` fixture: it exists to prove
`/health` works even with no dependency overrides in place and without the
real `lifespan` ever running (a plain `TestClient(app)`, not used as a
context manager, never triggers startup -- see `tendersathi.api.app`).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tendersathi.api.app import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
