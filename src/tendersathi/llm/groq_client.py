"""Groq implementation of the LLMClient interface."""

from __future__ import annotations

import json

from groq import Groq
from pydantic import BaseModel, ValidationError

from tendersathi import config
from tendersathi.llm.base import LLMClient, ResponseModel


class GroqClient(LLMClient):
    """Calls Groq's chat completion API and validates the JSON reply."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        resolved_key = api_key or config.GROQ_API_KEY
        if not resolved_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file "
                "(get a free key at https://console.groq.com/keys)."
            )
        self.client = Groq(api_key=resolved_key)
        self.model = model or config.GROQ_MODEL

    def generate(
        self,
        prompt: str,
        response_model: type[ResponseModel],
        max_retries: int = 2,
        max_tokens: int | None = None,
    ) -> ResponseModel:
        system_prompt = _build_system_prompt(response_model)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        last_error: ValidationError | None = None
        for _ in range(max_retries + 1):
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                **({"max_tokens": max_tokens} if max_tokens is not None else {}),
            )
            content = completion.choices[0].message.content
            try:
                return response_model.model_validate_json(content)
            except ValidationError as error:
                last_error = error
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "That response failed schema validation with this "
                            f"error: {error}. Reply again with corrected JSON only."
                        ),
                    }
                )

        assert last_error is not None
        raise last_error


def _build_system_prompt(response_model: type[BaseModel]) -> str:
    schema = json.dumps(response_model.model_json_schema())
    return (
        "You are a precise data-extraction assistant. Respond with a single "
        "JSON object only (no markdown, no commentary) that matches this "
        f"JSON schema:\n{schema}"
    )
