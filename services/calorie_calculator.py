"""Evidence-based calorie and macro calculations."""
from __future__ import annotations

from dataclasses import dataclass


ACTIVITY_MULTIPLIERS = {
    "Sedentary": 1.2,
    "Lightly Active": 1.375,
    "Moderately Active": 1.55,
    "Very Active": 1.725,
    "Extra Active": 1.9,
}


@dataclass(frozen=True)
class NutritionTargets:
    bmi: float
    bmr: int
    tdee: int
    calorie_goal: int
    protein_goal_g: int
    carbs_goal_g: int
    fat_goal_g: int


class CalorieCalculator:
    """Mifflin-St Jeor calculator for adult energy estimates."""

    @staticmethod
    def calculate(age: int, gender: str, height_cm: float, weight_kg: float,
                  activity_level: str, goal: str) -> NutritionTargets:
        if age < 16 or height_cm <= 0 or weight_kg <= 0:
            raise ValueError("Enter a valid adult age, height, and weight.")
        base = 10 * weight_kg + 6.25 * height_cm - 5 * age
        bmr = base + (5 if gender.lower() == "male" else -161)
        tdee = bmr * ACTIVITY_MULTIPLIERS.get(activity_level, 1.2)
        adjustment = {"Weight Loss": -500, "Maintenance": 0, "Muscle Gain": 300}.get(goal, 0)
        calorie_goal = max(1200 if gender.lower() == "female" else 1500, round(tdee + adjustment))
        protein = round(weight_kg * (2.0 if goal in {"Weight Loss", "Muscle Gain"} else 1.6))
        fat = round(calorie_goal * 0.27 / 9)
        carbs = max(0, round((calorie_goal - protein * 4 - fat * 9) / 4))
        return NutritionTargets(round(weight_kg / (height_cm / 100) ** 2, 1), round(bmr), round(tdee),
                                calorie_goal, protein, carbs, fat)
