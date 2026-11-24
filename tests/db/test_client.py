"""Tests for get_supabase_client, with the Supabase SDK call mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tendersathi.db.client import get_supabase_client


@patch("tendersathi.db.client.create_client")
def test_get_supabase_client_builds_client_from_config(mock_create_client, monkeypatch):
    monkeypatch.setattr("tendersathi.config.SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr("tendersathi.config.SUPABASE_KEY", "fake-key")
    mock_create_client.return_value = MagicMock()

    client = get_supabase_client()

    mock_create_client.assert_called_once_with("https://example.supabase.co", "fake-key")
    assert client is mock_create_client.return_value


def test_get_supabase_client_raises_clear_error_when_unconfigured(monkeypatch):
    monkeypatch.setattr("tendersathi.config.SUPABASE_URL", None)
    monkeypatch.setattr("tendersathi.config.SUPABASE_KEY", None)

    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        get_supabase_client()
