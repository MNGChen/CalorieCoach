"""Structured extraction of consumed food names and explicitly stated portions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai.nutrition_ai import AIServiceError
from ai.openai_client import OpenAIStructuredChain, OpenAIServiceError
from ai.prompts import FOOD_INPUT_PARSE_PROMPT


@dataclass(frozen=True)
class FoodInput:
    name: str
    quantity: float | None
    unit: str | None


class FoodItemSchema(BaseModel):
    """The only fields the LLM may emit for one food item."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None


class FoodParseResult(BaseModel):
    """Provider-validated structured food extraction."""

    model_config = ConfigDict(extra="forbid")

    items: list[FoodItemSchema]


class FoodInputParser:
    """Converts free text into validated food inputs, without nutrition estimates."""

    def __init__(self, chain: Any | None = None) -> None:
        self.chain = chain or self._build_chain()

    @staticmethod
    def _build_chain() -> Any:
        try:
            return OpenAIStructuredChain(FOOD_INPUT_PARSE_PROMPT, "User message: {food_description}", FoodParseResult)
        except OpenAIServiceError as exc:
            raise AIServiceError(str(exc)) from exc

    def parse(self, message: str) -> list[FoodInput]:
        if not message.strip():
            return []
        try:
            data = self.chain.invoke({"food_description": message})
        except Exception as exc:
            raise AIServiceError("Food parsing is currently unavailable. Check your OpenAI API key and connection, then try again.") from exc
        return self.validate(data)

    @staticmethod
    def validate(data: object) -> list[FoodInput]:
        """Validate the chain output once more before deterministic processing."""
        try:
            parsed = data if isinstance(data, FoodParseResult) else FoodParseResult.model_validate(data)
        except ValidationError as exc:
            raise ValueError("Food parser returned an invalid response shape.") from exc
        return [FoodInput(name=item.name.strip(), quantity=item.quantity,
                          unit=item.unit.strip().casefold() if item.unit else None) for item in parsed.items]
