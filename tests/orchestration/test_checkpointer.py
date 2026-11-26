"""Tests for get_checkpointer's config guard.

The success path opens a real Postgres connection, so it isn't covered
here (no test may make a real network call); this only checks the clear
error raised when DATABASE_URL isn't configured.
"""

from __future__ import annotations

import pytest

from tendersathi.orchestration.checkpointer import get_checkpointer


def test_get_checkpointer_raises_clear_error_when_unconfigured(monkeypatch):
    monkeypatch.setattr("tendersathi.config.DATABASE_URL", None)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        with get_checkpointer():
            pass
