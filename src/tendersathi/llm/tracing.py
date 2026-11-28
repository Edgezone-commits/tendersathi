"""Langfuse tracing wrapper, applied once in `tendersathi.llm.get_llm_client`.

Every agent calls `get_llm_client()` rather than constructing a provider
client directly, so wrapping here -- instead of inside `GroqClient` -- is
what makes "every LLM call is traced" (see CLAUDE.md) hold for every
current and future provider without touching provider code.
"""

from __future__ import annotations

from langfuse import Langfuse

from tendersathi import config
from tendersathi.llm.base import LLMClient, ResponseModel


def build_langfuse_client() -> Langfuse:
    """Build the Langfuse client from config, rather than its own env-var fallback.

    A missing public/secret key doesn't raise -- the Langfuse SDK logs a
    warning and returns a disabled client that no-ops on every call, which
    is exactly what local dev without Langfuse configured should do.
    """
    return Langfuse(
        public_key=config.LANGFUSE_PUBLIC_KEY,
        secret_key=config.LANGFUSE_SECRET_KEY,
        host=config.LANGFUSE_HOST,
    )


class TracedLLMClient(LLMClient):
    """Wraps another LLMClient, recording one Langfuse generation span per `generate()` call."""

    def __init__(self, wrapped: LLMClient, langfuse_client: Langfuse | None = None) -> None:
        self.wrapped = wrapped
        self.langfuse_client = langfuse_client or build_langfuse_client()

    def generate(
        self,
        prompt: str,
        response_model: type[ResponseModel],
        max_retries: int = 2,
        max_tokens: int | None = None,
    ) -> ResponseModel:
        model_name = getattr(self.wrapped, "model", type(self.wrapped).__name__)
        with self.langfuse_client.start_as_current_observation(
            name=f"{response_model.__name__}.generate",
            as_type="generation",
            input=prompt,
            model=model_name,
            metadata={"response_model": response_model.__name__, "max_retries": max_retries},
        ) as generation:
            try:
                result = self.wrapped.generate(prompt, response_model, max_retries, max_tokens)
            except Exception as error:
                generation.update(level="ERROR", status_message=str(error))
                raise
            generation.update(output=result.model_dump(mode="json"))
            return result
