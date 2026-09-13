"""Small OpenAI Responses API adapters shared by the application's AI services."""
from __future__ import annotations

from typing import Any, TypeVar
import logging
from time import perf_counter

from openai import OpenAI
from pydantic import BaseModel

from config import OPENAI_API_KEY, OPENAI_MODEL, REQUEST_TIMEOUT_SECONDS

SchemaT = TypeVar("SchemaT", bound=BaseModel)
logger = logging.getLogger(__name__)


class OpenAIServiceError(RuntimeError):
    """A safe provider error that can be shown without exposing API details."""


class OpenAIStructuredChain:
    """Keeps the old ``chain.invoke`` seam while using Responses structured output."""

    def __init__(self, system_prompt: str, user_template: str, response_model: type[SchemaT],
                 client: OpenAI | None = None) -> None:
        self.system_prompt = system_prompt
        self.user_template = user_template
        self.response_model = response_model
        self.client = client

    def invoke(self, values: dict[str, Any]) -> SchemaT:
        started = perf_counter()
        try:
            if self.client is None:
                if not OPENAI_API_KEY:
                    raise OpenAIServiceError("OPENAI_API_KEY is not configured.")
                self.client = OpenAI(api_key=OPENAI_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=1)
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
            logger.warning("AI stage %s failed (%s) after %.2fs", self.response_model.__name__,
                           type(exc).__name__, perf_counter() - started)
            raise OpenAIServiceError("OpenAI structured-output request failed.") from exc
        if response.output_parsed is None:
            raise OpenAIServiceError("OpenAI returned no structured response.")
        usage = getattr(response, "usage", None)
        logger.info("AI stage %s completed in %.2fs; input_tokens=%s output_tokens=%s",
                    self.response_model.__name__, perf_counter() - started,
                    getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
        return response.output_parsed
