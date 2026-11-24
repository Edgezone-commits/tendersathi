"""Tests for the get_llm_client() provider factory."""

from __future__ import annotations

import pytest

from tendersathi.llm import get_llm_client


def test_get_llm_client_returns_groq_client_by_default(monkeypatch) -> None:
    monkeypatch.setattr("tendersathi.config.LLM_PROVIDER", "groq")
    monkeypatch.setattr("tendersathi.config.GROQ_API_KEY", "fake-key")

    client = get_llm_client()

    assert type(client).__name__ == "GroqClient"


def test_get_llm_client_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.setattr("tendersathi.config.LLM_PROVIDER", "some-unsupported-provider")

    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        get_llm_client()
