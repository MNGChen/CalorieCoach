"""Deterministic daily target, consumed, and remaining nutrition summaries."""
from __future__ import annotations

from datetime import date
from typing import Any

from services.nutrition_service import NutritionService


class DailyNutritionService:
    def __init__(self, nutrition: NutritionService | None = None) -> None:
        self.nutrition = nutrition or NutritionService()

    def summary(self, day: date) -> dict[str, Any]:
        consumed = self.nutrition.daily_totals(day)
        profile = self.nutrition.get_profile()
        if profile is None:
            return {"date": day.isoformat(), "target": None, "consumed": consumed, "remaining": None}
        targets = self.nutrition.targets(profile)
        target = {"calories": float(targets.calorie_goal), "protein_g": float(targets.protein_goal_g),
                  "carbs_g": float(targets.carbs_goal_g), "fat_g": float(targets.fat_goal_g)}
        remaining = {key: round(target[key] - consumed[key], 2) for key in target}
        return {"date": day.isoformat(), "target": target, "consumed": consumed, "remaining": remaining}
