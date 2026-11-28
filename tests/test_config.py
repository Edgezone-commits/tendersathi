"""Tests for get_env's whitespace stripping and required-value guard."""

from __future__ import annotations

import pytest

from tendersathi.config import get_env


def test_get_env_strips_surrounding_whitespace(monkeypatch):
    monkeypatch.setenv("SOME_VAR", "  value-with-padding\n")

    assert get_env("SOME_VAR") == "value-with-padding"


def test_get_env_returns_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_VAR", raising=False)

    assert get_env("SOME_VAR", default="fallback") == "fallback"


def test_get_env_raises_when_required_and_missing(monkeypatch):
    monkeypatch.delenv("SOME_VAR", raising=False)

    with pytest.raises(RuntimeError, match="SOME_VAR"):
        get_env("SOME_VAR", required=True)


def test_get_env_raises_when_required_and_only_whitespace(monkeypatch):
    monkeypatch.setenv("SOME_VAR", "   \n")

    with pytest.raises(RuntimeError, match="SOME_VAR"):
        get_env("SOME_VAR", required=True)
