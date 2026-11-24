"""Tests for GroqClient, using a mocked Groq SDK client (no network calls)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from tendersathi.llm.groq_client import GroqClient


class Answer(BaseModel):
    value: int


def _mock_completion(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


@patch("tendersathi.llm.groq_client.Groq")
def test_generate_returns_valid_model_on_first_try(mock_groq_cls: MagicMock) -> None:
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.return_value = _mock_completion('{"value": 42}')
    mock_groq_cls.return_value = mock_sdk_client

    client = GroqClient(api_key="fake-key", model="fake-model")
    result = client.generate("What is 6 times 7?", Answer)

    assert result == Answer(value=42)
    assert mock_sdk_client.chat.completions.create.call_count == 1


@patch("tendersathi.llm.groq_client.Groq")
def test_generate_retries_after_invalid_json(mock_groq_cls: MagicMock) -> None:
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.side_effect = [
        _mock_completion('{"value": "not-an-int"}'),
        _mock_completion('{"value": 7}'),
    ]
    mock_groq_cls.return_value = mock_sdk_client

    client = GroqClient(api_key="fake-key", model="fake-model")
    result = client.generate("What is 7?", Answer, max_retries=1)

    assert result == Answer(value=7)
    assert mock_sdk_client.chat.completions.create.call_count == 2


@patch("tendersathi.llm.groq_client.Groq")
def test_generate_raises_after_exhausting_retries(mock_groq_cls: MagicMock) -> None:
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.return_value = _mock_completion(
        '{"value": "still-not-an-int"}'
    )
    mock_groq_cls.return_value = mock_sdk_client

    client = GroqClient(api_key="fake-key", model="fake-model")

    try:
        client.generate("What is 7?", Answer, max_retries=1)
    except Exception as error:  # noqa: BLE001 - we want to assert the type below
        assert "value" in str(error)
    else:
        raise AssertionError("Expected a ValidationError to be raised")

    assert mock_sdk_client.chat.completions.create.call_count == 2


@patch("tendersathi.llm.groq_client.Groq")
def test_generate_passes_max_tokens_through_when_given(mock_groq_cls: MagicMock) -> None:
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.return_value = _mock_completion('{"value": 1}')
    mock_groq_cls.return_value = mock_sdk_client

    client = GroqClient(api_key="fake-key", model="fake-model")
    client.generate("What is 1?", Answer, max_tokens=500)

    _, kwargs = mock_sdk_client.chat.completions.create.call_args
    assert kwargs["max_tokens"] == 500


@patch("tendersathi.llm.groq_client.Groq")
def test_generate_omits_max_tokens_when_not_given(mock_groq_cls: MagicMock) -> None:
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.return_value = _mock_completion('{"value": 1}')
    mock_groq_cls.return_value = mock_sdk_client

    client = GroqClient(api_key="fake-key", model="fake-model")
    client.generate("What is 1?", Answer)

    _, kwargs = mock_sdk_client.chat.completions.create.call_args
    assert "max_tokens" not in kwargs


def test_missing_api_key_raises_clear_error(monkeypatch) -> None:
    monkeypatch.setattr("tendersathi.config.GROQ_API_KEY", None)

    try:
        GroqClient(api_key=None)
    except RuntimeError as error:
        assert "GROQ_API_KEY" in str(error)
    else:
        raise AssertionError("Expected a RuntimeError when no API key is available")
