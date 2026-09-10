"""LLM reliability decision over deterministic, normalized nutrition evidence."""
from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field

from ai.prompts import NUTRITION_VALIDATION_PROMPT
from config import GEMINI_API_KEY, GEMINI_MODEL
from services.nutrition_validation_models import ValidationDecision


class NutritionValidationAgentError(RuntimeError):
    pass


class ValidationAgentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "uncertain", "rejected"]
    confidence: Literal["high", "medium", "low"]
    confidence_score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)


class NutritionValidationAgent:
    """Assesses evidence quality only; it never searches or calculates nutrition facts."""

    def __init__(self, chain: Any | None = None) -> None:
        self.chain = chain or self._build_chain()

    @staticmethod
    def _build_chain() -> Any:
        if not GEMINI_API_KEY:
            raise NutritionValidationAgentError("GEMINI_API_KEY is not configured.")
        prompt = ChatPromptTemplate.from_messages([
            ("system", NUTRITION_VALIDATION_PROMPT),
            ("human", "Validation evidence:\n{evidence}"),
        ])
        llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GEMINI_API_KEY, temperature=0)
        return prompt | llm.with_structured_output(ValidationAgentSchema)

    def validate(self, evidence: dict[str, Any]) -> ValidationDecision:
        try:
            data = self.chain.invoke({"evidence": json.dumps(evidence, ensure_ascii=False)})
            parsed = data if isinstance(data, ValidationAgentSchema) else ValidationAgentSchema.model_validate(data)
        except Exception as exc:
            raise NutritionValidationAgentError("Nutrition validation agent returned an invalid result.") from exc
        return ValidationDecision(parsed.status, parsed.confidence, parsed.confidence_score, parsed.reason.strip())
