"""AI interpretation of deterministic nutrition and weight trend summaries."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field

from ai.prompts import PROGRESS_ANALYSIS_PROMPT
from config import GEMINI_API_KEY, GEMINI_MODEL


class ProgressAnalysisError(RuntimeError):
    pass


class ProgressAnalysisSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=400)
    insight: str = Field(min_length=1, max_length=400)
    next_step: str = Field(min_length=1, max_length=400)
    watch_out: str = Field(min_length=1, max_length=300)


class ProgressAnalysisService:
    """Builds a compact, deterministic trend context before requesting interpretation."""

    def __init__(self, chain: Any | None = None) -> None:
        self.chain = chain

    def analyze(self, food: pd.DataFrame, weights: pd.DataFrame, target: dict[str, float],
                goal: str, days: int) -> ProgressAnalysisSchema:
        context = self._context(food, weights, target, goal, days)
        try:
            chain = self.chain or self._build_chain()
            result = chain.invoke({"context": json.dumps(context, ensure_ascii=False)})
            return result if isinstance(result, ProgressAnalysisSchema) else ProgressAnalysisSchema.model_validate(result)
        except Exception as exc:
            raise ProgressAnalysisError("Progress analysis is currently unavailable.") from exc

    @staticmethod
    def _build_chain() -> Any:
        if not GEMINI_API_KEY:
            raise ProgressAnalysisError("GEMINI_API_KEY is not configured.")
        prompt = ChatPromptTemplate.from_messages([
            ("system", PROGRESS_ANALYSIS_PROMPT),
            ("human", "Trend context:\n{context}"),
        ])
        llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GEMINI_API_KEY, temperature=0.2)
        return prompt | llm.with_structured_output(ProgressAnalysisSchema)

    @staticmethod
    def _context(food: pd.DataFrame, weights: pd.DataFrame, target: dict[str, float], goal: str,
                 days: int) -> dict[str, Any]:
        nutrition: dict[str, Any] = {"days_logged": 0, "average_calories": None, "average_protein_g": None,
                                     "days_within_calorie_target": 0}
        if not food.empty:
            nutrition = {
                "days_logged": int(len(food)),
                "average_calories": round(float(food["Calories"].mean()), 1),
                "average_protein_g": round(float(food["Protein (g)"].mean()), 1),
                "days_within_calorie_target": int((food["Calories"] <= target["calories"]).sum()),
            }
        weight: dict[str, Any] = {"measurements": 0, "first_kg": None, "latest_kg": None, "change_kg": None}
        if not weights.empty:
            first, latest = float(weights.iloc[0]["Weight (kg)"]), float(weights.iloc[-1]["Weight (kg)"])
            weight = {"measurements": int(len(weights)), "first_kg": first, "latest_kg": latest,
                      "change_kg": round(latest - first, 1)}
        return {"period_days": days, "user_goal": goal, "daily_target": target,
                "nutrition_trend": nutrition, "weight_trend": weight}
