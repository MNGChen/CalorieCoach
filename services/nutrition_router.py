"""Structured intent router with deterministic shortcuts for common nutrition requests."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from ai.openai_client import OpenAIStructuredChain, OpenAIServiceError

class RouterError(RuntimeError): pass
class IntentSchema(BaseModel):
    model_config=ConfigDict(extra="forbid")
    intent: Literal["log_food","daily_progress","nutrition_question","meal_recommendation","general_nutrition_chat"]
    confidence: float = Field(ge=0, le=1)
class NutritionRouter:
    def __init__(self, chain: Any|None=None): self.chain=chain or self._build()
    @staticmethod
    def _build():
        try:
            return OpenAIStructuredChain(
                "Classify nutrition messages into exactly one intent: log_food, daily_progress, nutrition_question, meal_recommendation, general_nutrition_chat. Return structured output.",
                "Message: {message}", IntentSchema,
            )
        except OpenAIServiceError as exc:
            raise RouterError(str(exc)) from exc
    def route(self,message:str)->IntentSchema:
        lower=message.casefold()
        if any(x in lower for x in ("what should i eat","what can i eat","recommend a meal","for dinner","for lunch", "mcdonald's", "mcdonalds", "麦当劳")): return IntentSchema(intent="meal_recommendation",confidence=1)
        if any(x in lower for x in ("how am i doing","calories left","calorie remaining","today's progress")): return IntentSchema(intent="daily_progress",confidence=1)
        if any(x in lower for x in ("do i need more protein","more carbs","more fat","protein today")): return IntentSchema(intent="nutrition_question",confidence=1)
        if any(x in lower for x in ("i ate","i had","i drank","log ")): return IntentSchema(intent="log_food",confidence=1)
        try:
            data=self.chain.invoke({"message":message}); return data if isinstance(data,IntentSchema) else IntentSchema.model_validate(data)
        except Exception as exc: raise RouterError("Unable to determine nutrition request intent.") from exc
