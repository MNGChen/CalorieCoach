"""Constrained LLM re-ranker for ambiguous local food-catalogue candidates."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai.openai_client import OpenAIStructuredChain, OpenAIServiceError
from ai.prompts import FOOD_MATCH_PROMPT


class FoodMatchAgentError(RuntimeError):
    pass


class FoodMatchSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food_id: int | None = None
    confidence: Literal["high", "medium", "low"]
    reason: str = Field(min_length=1, max_length=240)


class FoodMatchAgent:
    """Selects only a supplied food ID, never nutrition data or a new food name."""

    def __init__(self, chain: Any | None = None) -> None:
        self.chain = chain

    @staticmethod
    def _build_chain() -> Any:
        try:
            return OpenAIStructuredChain(FOOD_MATCH_PROMPT, "Food-match context:\n{context}", FoodMatchSchema)
        except OpenAIServiceError as exc:
            raise FoodMatchAgentError(str(exc)) from exc

    def choose(self, query: str, candidates: list[dict[str, Any]]) -> FoodMatchSchema:
        if not candidates:
            return FoodMatchSchema(food_id=None, confidence="low", reason="No locally eligible candidates.")
        try:
            chain = self.chain or self._build_chain()
            data = chain.invoke({"context": json.dumps({"user_food": query, "candidates": candidates}, ensure_ascii=False)})
            result = data if isinstance(data, FoodMatchSchema) else FoodMatchSchema.model_validate(data)
        except Exception as exc:
            raise FoodMatchAgentError("Local food match could not be verified.") from exc
        allowed_ids = {item["id"] for item in candidates}
        if result.food_id is not None and result.food_id not in allowed_ids:
            raise FoodMatchAgentError("Food matcher selected an item outside the candidate list.")
        return result
