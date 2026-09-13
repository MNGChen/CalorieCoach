"""Structured LLM agent that interprets already-calculated nutrition progress."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai.openai_client import OpenAIStructuredChain, OpenAIServiceError
from ai.prompts import NUTRITION_COACH_PROMPT

class NutritionCoachAgentError(RuntimeError):
    pass


class CoachAdviceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=400)
    priority: str = Field(min_length=1, max_length=80)
    recommendation: str = Field(min_length=1, max_length=380)
    avoid_or_limit: list[str] = Field(default_factory=list, max_length=5)
    reasoning_summary: str = Field(min_length=1, max_length=400)


class NutritionCoachAgent:
    """Provides strategy-level guidance from a compact deterministic context."""

    def __init__(self, chain: Any | None = None) -> None:
        self.chain = chain or self._build_chain()

    @staticmethod
    def _build_chain() -> Any:
        try:
            return OpenAIStructuredChain(NUTRITION_COACH_PROMPT, "Coach context:\n{context}", CoachAdviceSchema)
        except OpenAIServiceError as exc:
            raise NutritionCoachAgentError(str(exc)) from exc

    def advise(self, context: dict[str, Any]) -> CoachAdviceSchema:
        try:
            data = self.chain.invoke({"context": json.dumps(context, ensure_ascii=False)})
            return data if isinstance(data, CoachAdviceSchema) else CoachAdviceSchema.model_validate(data)
        except Exception as exc:
            raise NutritionCoachAgentError("Nutrition coach returned an invalid response.") from exc
