"""Tests for TracedLLMClient, with the Langfuse client mocked (no real network calls)."""

from __future__ import annotations

from unittest.mock import MagicMock

from pydantic import BaseModel

from tendersathi.llm.tracing import TracedLLMClient


class Answer(BaseModel):
    value: int


def _mock_langfuse_client() -> tuple[MagicMock, MagicMock]:
    """A Langfuse mock whose `start_as_current_observation(...)` is usable as a context manager."""
    langfuse_client = MagicMock()
    generation = MagicMock()
    langfuse_client.start_as_current_observation.return_value.__enter__.return_value = generation
    return langfuse_client, generation


def test_generate_records_a_successful_span_and_returns_the_result() -> None:
    langfuse_client, generation = _mock_langfuse_client()
    wrapped = MagicMock()
    wrapped.generate.return_value = Answer(value=42)
    wrapped.model = "fake-model"

    client = TracedLLMClient(wrapped, langfuse_client=langfuse_client)
    result = client.generate("What is 6 times 7?", Answer)

    assert result == Answer(value=42)
    wrapped.generate.assert_called_once_with("What is 6 times 7?", Answer, 2, None)
    langfuse_client.start_as_current_observation.assert_called_once()
    kwargs = langfuse_client.start_as_current_observation.call_args.kwargs
    assert kwargs["as_type"] == "generation"
    assert kwargs["model"] == "fake-model"
    assert kwargs["input"] == "What is 6 times 7?"
    generation.update.assert_called_once_with(output={"value": 42})


def test_generate_records_an_errored_span_and_reraises() -> None:
    langfuse_client, generation = _mock_langfuse_client()
    wrapped = MagicMock()
    wrapped.generate.side_effect = RuntimeError("boom")

    client = TracedLLMClient(wrapped, langfuse_client=langfuse_client)

    try:
        client.generate("prompt", Answer)
    except RuntimeError as error:
        assert str(error) == "boom"
    else:
        raise AssertionError("Expected the wrapped client's error to propagate")

    generation.update.assert_called_once_with(level="ERROR", status_message="boom")
