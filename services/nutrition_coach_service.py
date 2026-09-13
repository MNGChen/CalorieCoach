"""Loads deterministic nutrition state and delegates only interpretation to the coach agent."""
from __future__ import annotations

from datetime import date
import logging
from typing import Any

from services.daily_nutrition_service import DailyNutritionService
from services.meal_service import MealService
from services.nutrition_coach_agent import NutritionCoachAgent, NutritionCoachAgentError
from services.nutrition_service import NutritionService

logger = logging.getLogger(__name__)


class NutritionCoachService:
    def __init__(self, daily_nutrition: DailyNutritionService | None = None,
                 nutrition: NutritionService | None = None, meals: MealService | None = None,
                 agent: NutritionCoachAgent | None = None, knowledge_base: Any | None = None) -> None:
        self.nutrition = nutrition or NutritionService()
        self.daily_nutrition = daily_nutrition or DailyNutritionService(self.nutrition)
        self.meals = meals or MealService()
        self.agent = agent or NutritionCoachAgent()
        self.knowledge_base = knowledge_base

    def get_nutrition_advice(self, question: str, day: date | None = None,
                             memory_context: dict[str, Any] | None = None) -> dict[str, Any]:
        if not question.strip():
            raise ValueError("Please enter a nutrition question.")
        selected_day = day or date.today()
        profile = self.nutrition.get_profile()
        summary = self.daily_nutrition.summary(selected_day)
        if profile is None or summary["target"] is None:
            return {"available": False, "reason": "Set up your profile to receive daily nutrition guidance.",
                    "daily_summary": summary}
        context = self._context(question, profile.goal, summary, selected_day, memory_context)
        if self.knowledge_base:
            context["knowledge_sources"] = self.knowledge_base.retrieve(question)
        logger.info("Coach request received. Goal: %s. Calorie progress: %.0f%%. Protein progress: %.0f%%.",
                    profile.goal, context["progress"]["calories"] * 100, context["progress"]["protein_g"] * 100)
        try:
            advice = self.agent.advise(context)
        except NutritionCoachAgentError:
            # The UI remains deliberately generic, while application logs retain
            # the chained provider/parsing exception for support diagnostics.
            logger.warning("Nutrition coach agent failed to provide valid guidance.", exc_info=True)
            return {"available": False, "reason": "Nutrition coaching is currently unavailable.",
                    "daily_summary": summary}
        logger.info("Coach response validated.")
        return {"available": True, "summary": advice.summary, "priority": advice.priority,
                "recommendation": advice.recommendation, "avoid_or_limit": advice.avoid_or_limit,
                "reasoning_summary": advice.reasoning_summary,
                "knowledge_sources": context.get("knowledge_sources", []),
                # This is a deterministic remaining budget, not an LLM-generated meal prescription.
                "target_for_next_meal": {key: max(0, value) for key, value in summary["remaining"].items()},
                "daily_summary": summary}

    def _context(self, question: str, goal: str, summary: dict[str, Any], selected_day: date,
                 memory_context: dict[str, Any] | None = None) -> dict[str, Any]:
        target, consumed = summary["target"], summary["consumed"]
        progress = {key: round(consumed[key] / target[key], 3) if target[key] else 0.0 for key in target}
        recent = self.meals.logs(start=selected_day, end=selected_day)[:3]
        return {"user_goal": goal, "daily_target": target, "consumed": consumed, "remaining": summary["remaining"],
                "progress": progress, "recent_meals": [{"food": item.food_name, "meal_type": item.meal_type,
                                                          "calories": item.calories} for item in recent],
                "user_question": question.strip(), "conversation_memory": memory_context or {}}
