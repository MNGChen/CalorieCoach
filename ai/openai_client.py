"""Small OpenAI Responses API adapters shared by the application's AI services."""
from __future__ import annotations

from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from config import OPENAI_API_KEY, OPENAI_MODEL, REQUEST_TIMEOUT_SECONDS

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class OpenAIServiceError(RuntimeError):
    """A safe provider error that can be shown without exposing API details."""


class OpenAIStructuredChain:
    """Keeps the old ``chain.invoke`` seam while using Responses structured output."""

    def __init__(self, system_prompt: str, user_template: str, response_model: type[SchemaT],
                 client: OpenAI | None = None) -> None:
        if client is None and not OPENAI_API_KEY:
            raise OpenAIServiceError("OPENAI_API_KEY is not configured.")
        self.system_prompt = system_prompt
        self.user_template = user_template
        self.response_model = response_model
        self.client = client or OpenAI(api_key=OPENAI_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS)

    def invoke(self, values: dict[str, Any]) -> SchemaT:
        try:
            response = self.client.responses.parse(
                model=OPENAI_MODEL,
                input=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self.user_template.format(**values)},
                ],
                text_format=self.response_model,
                # Nutrition context is user data; do not use the API's default response storage.
                store=False,
            )
        except Exception as exc:
            raise OpenAIServiceError("OpenAI structured-output request failed.") from exc
        if response.output_parsed is None:
            raise OpenAIServiceError("OpenAI returned no structured response.")
        return response.output_parsed
