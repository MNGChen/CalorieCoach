"""Route completed meals separately from questions and future meal requests."""
from __future__ import annotations

import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from ai.openai_client import OpenAIStructuredChain


class RouterError(RuntimeError):
    pass


class IntentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["log_food", "daily_progress", "nutrition_question", "meal_recommendation", "general_nutrition_chat"]
    confidence: float = Field(ge=0, le=1)
    follow_up_request: str | None = None


class NutritionRouter:
    def __init__(self, chain: Any | None = None):
        self.chain = chain

    def route(self, message: str) -> IntentSchema:
        lower = message.casefold().strip()
        eaten = bool(re.search(r"\b(?:i ate|i had|i drank|log\s+(?:my|this|a|an|the))\b|(?:我|今天|午餐|晚餐|早餐).{0,12}(?:吃了|喝了)|记录.{0,8}(?:吃|餐)", lower))
        recommendation = re.search(r"what (?:should|can) i eat|recommend (?:a |my |some )?(?:meal|lunch|dinner|breakfast)|(?:午餐|晚餐|早餐|下一餐|我).{0,8}(?:吃什么|吃点什么)|推荐.{0,8}(?:吃|餐)", lower)
        if eaten and not re.match(r"(?:if\b|what if\b|did\b|have\b|假如|如果)", lower):
            return IntentSchema(intent="log_food", confidence=1,
                                follow_up_request=message[recommendation.start():] if recommendation else None)
        if recommendation or re.search(r"\b(?:i want|i would like|suggest).*(?:kfc|mcdonald)|我想吃", lower):
            return IntentSchema(intent="meal_recommendation", confidence=1)
        if any(term in lower for term in ("how am i doing", "calories left", "calories do i have left", "calorie remaining", "today's progress", "还剩多少", "今日进度")):
            return IntentSchema(intent="daily_progress", confidence=1)
        if any(term in lower for term in ("do i need more protein", "more carbs", "more fat", "protein today", "蛋白质够", "需要补充")):
            return IntentSchema(intent="nutrition_question", confidence=1)
        try:
            chain = self.chain or OpenAIStructuredChain(
                "Classify the request. log_food means food actually consumed or an explicit request to record it. "
                "Hypothetical, negated and future meals are not consumed meals. Restaurant names and meal times "
                "alone do not imply a recommendation. For completed food plus a next-meal question, choose log_food "
                "and retain only the question in follow_up_request. Otherwise follow_up_request is null.",
                "Message: {message}", IntentSchema,
            )
            result = chain.invoke({"message": message})
            return result if isinstance(result, IntentSchema) else IntentSchema.model_validate(result)
        except Exception as exc:
            raise RouterError("Unable to determine nutrition request intent.") from exc
