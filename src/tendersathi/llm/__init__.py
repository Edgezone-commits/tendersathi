"""Factory for the configured LLM provider.

Agents should call `get_llm_client()` and never import a provider
class (e.g. `GroqClient`) directly, so changing `LLM_PROVIDER` in
`.env` is enough to switch providers everywhere.
"""

from __future__ import annotations

from tendersathi import config
from tendersathi.llm.base import LLMClient


def get_llm_client() -> LLMClient:
    """Build the LLMClient selected by the `LLM_PROVIDER` env var."""
    provider = (config.LLM_PROVIDER or "groq").lower()

    if provider == "groq":
        from tendersathi.llm.groq_client import GroqClient

        return GroqClient()

    raise ValueError(
        f"Unsupported LLM_PROVIDER: {provider!r}. "
        "Supported values: 'groq' (Gemini and Ollama land in a later phase)."
    )
