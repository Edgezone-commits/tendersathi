"""Abstract interface every LLM provider must implement.

Every agent calls `LLMClient.generate(...)` instead of talking to a
provider SDK directly. That is what lets us swap Groq for Gemini or
Ollama by changing one environment variable (`LLM_PROVIDER`), and
gives us one place to add tracing and retries for every LLM call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class LLMClient(ABC):
    """Common interface for all LLM providers used by TenderSathi."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        response_model: type[ResponseModel],
        max_retries: int = 2,
        max_tokens: int | None = None,
    ) -> ResponseModel:
        """Call the LLM and parse its reply into `response_model`.

        Implementations must retry up to `max_retries` times if the
        LLM's output fails Pydantic validation, and then raise the
        last validation error. `max_tokens` bounds the completion length;
        callers on tight free-tier rate limits (tokens per minute, not just
        per request) should pass it rather than rely on the provider's
        default, which can reserve far more than a call actually needs.
        """
        raise NotImplementedError
