"""Structured meal-combination agent; it never supplies final nutrition values."""
from __future__ import annotations
import json
from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field
from ai.prompts import MEAL_PLANNING_PROMPT
from config import GEMINI_API_KEY, GEMINI_MODEL

class MealPlanningAgentError(RuntimeError): pass
class PlannedFood(BaseModel):
    model_config = ConfigDict(extra="forbid")
    food_id: int
    quantity: float = Field(gt=0, le=2000)
    unit: str = Field(min_length=1, max_length=20)
class MealPlanSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meal_name: str = Field(min_length=1, max_length=100)
    foods: list[PlannedFood] = Field(min_length=1, max_length=6)
    reason: str = Field(min_length=1, max_length=300)
class MealPlanningAgent:
    def __init__(self, chain: Any | None = None) -> None: self.chain = chain or self._build_chain()
    @staticmethod
    def _build_chain() -> Any:
        if not GEMINI_API_KEY: raise MealPlanningAgentError("GEMINI_API_KEY is not configured.")
        prompt = ChatPromptTemplate.from_messages([("system", MEAL_PLANNING_PROMPT), ("human", "Planning context:\n{context}")])
        llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GEMINI_API_KEY, temperature=0.2)
        return prompt | llm.with_structured_output(MealPlanSchema)
    def plan(self, context: dict[str, Any]) -> MealPlanSchema:
        try:
            data = self.chain.invoke({"context": json.dumps(context, ensure_ascii=False)})
            return data if isinstance(data, MealPlanSchema) else MealPlanSchema.model_validate(data)
        except Exception as exc: raise MealPlanningAgentError("Meal planner returned an invalid response.") from exc
