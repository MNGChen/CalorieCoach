"""Structured LLM agent that interprets already-calculated nutrition progress."""
from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field

from ai.prompts import NUTRITION_COACH_PROMPT
from config import GEMINI_API_KEY, GEMINI_MODEL


class NutritionCoachAgentError(RuntimeError):
    pass


class CoachAdviceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=400)
    priority: str = Field(min_length=1, max_length=80)
    recommendation: str = Field(min_length=1, max_length=400)
    avoid_or_limit: list[str] = Field(default_factory=list, max_length=5)
    reasoning_summary: str = Field(min_length=1, max_length=400)


class NutritionCoachAgent:
    """Provides strategy-level guidance from a compact deterministic context."""

    def __init__(self, chain: Any | None = None) -> None:
        self.chain = chain or self._build_chain()

    @staticmethod
    def _build_chain() -> Any:
        if not GEMINI_API_KEY:
            raise NutritionCoachAgentError("GEMINI_API_KEY is not configured.")
        prompt = ChatPromptTemplate.from_messages([
            ("system", NUTRITION_COACH_PROMPT),
            ("human", "Coach context:\n{context}"),
        ])
        llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GEMINI_API_KEY, temperature=0.2)
        return prompt | llm.with_structured_output(CoachAdviceSchema)

    def advise(self, context: dict[str, Any]) -> CoachAdviceSchema:
        try:
            data = self.chain.invoke({"context": json.dumps(context, ensure_ascii=False)})
            return data if isinstance(data, CoachAdviceSchema) else CoachAdviceSchema.model_validate(data)
        except Exception as exc:
            raise NutritionCoachAgentError("Nutrition coach returned an invalid response.") from exc
