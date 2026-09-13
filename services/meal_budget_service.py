"""Allocate a planning budget; fractions are product heuristics, not prescriptions."""
import re


def next_meal_budget(summary: dict, recent_meals: list[dict], question: str) -> dict[str, float]:
    target, remaining = summary["target"], summary["remaining"]
    meal = next((name for name, pattern in {"Breakfast": r"breakfast|早餐", "Lunch": r"lunch|午餐",
                 "Dinner": r"dinner|晚餐", "Snack": r"snack|加餐"}.items() if re.search(pattern, question, re.I)), None)
    eaten = {entry.get("meal_type") for entry in recent_meals}
    if meal is None:
        meal = next((name for name in ("Breakfast", "Lunch", "Dinner") if name not in eaten), "Snack")
    fraction = {"Breakfast": .25, "Lunch": .35, "Dinner": .35, "Snack": .10}[meal]
    return {key: round(min(max(0.0, remaining[key]), max(0.0, target[key]) * fraction), 2) for key in target}
