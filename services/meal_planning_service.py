"""Filter local candidates, propose portions, and verify the calculated meal."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from sqlalchemy import select
from database.database import get_session
from database.models import Food
from services.dietary_constraints import DietaryConstraints
from services.food_input_parser import FoodInput
from services.meal_planning_agent import MealPlanningAgent, MealPlanningAgentError
from services.portion_calculator import PortionCalculator


class RestaurantMenuUnavailable(MealPlanningAgentError):
    def __init__(self, restaurant: str) -> None:
        self.restaurant = restaurant
        super().__init__(f"No verified {restaurant} menu items are available locally.")


@dataclass(frozen=True)
class MealTargetConfig:
    calories_tolerance: float = .15
    protein_tolerance: float = .20
    carbs_tolerance: float = .25
    fat_overage: float = .20


class MealPlanningService:
    RESTAURANT_ALIASES = {
        "McDonald's": ("mcdonald's", "mcdonalds", "麦当劳"),
        "KFC": ("kfc", "kentucky fried chicken", "肯德基"),
    }

    def __init__(self, agent: MealPlanningAgent | None = None, calculator: PortionCalculator | None = None,
                 config: MealTargetConfig | None = None, session_factory: Any = get_session) -> None:
        self.agent = agent or MealPlanningAgent()
        self.calculator = calculator or PortionCalculator()
        self.config = config or MealTargetConfig()
        self.session_factory = session_factory

    def recommend(self, coach_result: dict[str, Any], recent_foods: list[str] | None = None,
                  user_request: str = "") -> dict[str, Any]:
        target = coach_result.get("target_for_next_meal")
        if not target:
            raise ValueError("A meal nutrition target is required for recommendations.")
        restaurant = self.restaurant_for_request(user_request)
        constraints = DietaryConstraints.model_validate(coach_result.get("dietary_constraints", {}))
        candidates = self.retrieve_candidates(coach_result.get("priority", ""), recent_foods or [], restaurant, constraints)
        if not candidates:
            if restaurant and self.retrieve_candidates("", [], restaurant):
                raise MealPlanningAgentError("Restaurant foods do not meet the dietary checks.")
            if restaurant:
                raise RestaurantMenuUnavailable(restaurant)
            raise MealPlanningAgentError("No local foods with sufficient dietary information are available.")
        if target.get("calories", 0) <= 0:
            raise MealPlanningAgentError("No remaining calorie budget is available for a calculated meal.")
        context = {
            "user_goal": coach_result.get("user_goal"),
            "remaining_today": coach_result.get("daily_summary", {}).get("remaining", {}),
            "target_for_next_meal": target, "strategy": coach_result.get("priority", ""),
            "recent_foods": recent_foods or [], "user_request": user_request,
            "restaurant": restaurant, "candidates": candidates, "dietary_constraints": constraints.model_dump(),
        }
        for _ in range(2):
            proposal = self.agent.plan(context)
            calculated = self._calculate(proposal, target, {item["id"] for item in candidates}, constraints)
            if calculated["within_target"]:
                return calculated
            context["previous_calculated_meal"] = calculated
        raise MealPlanningAgentError("No candidate meal meets the checked nutrition budget.")

    @classmethod
    def restaurant_for_request(cls, request: str) -> str | None:
        value = request.casefold()
        return next((restaurant for restaurant, aliases in cls.RESTAURANT_ALIASES.items()
                     if any(alias in value for alias in aliases)), None)

    def retrieve_candidates(self, strategy: str, recent_foods: list[str], restaurant: str | None = None,
                            constraints: DietaryConstraints | None = None) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            foods = list(session.scalars(select(Food)))
        if restaurant:
            aliases = self.RESTAURANT_ALIASES[restaurant]
            foods = [food for food in foods if any(alias in food.name.casefold() for alias in aliases)]
        if constraints:
            foods = [food for food in foods if constraints.permits(food)]
        recent = {name.casefold() for name in recent_foods}
        lean_first = "protein" in strategy.casefold()
        foods.sort(key=lambda food: (food.name.casefold() in recent,
                                     food.fat_g / max(food.protein_g, 1) if lean_first else 0, food.name))
        return [{"id": food.id, "name": food.name,
                 "serving_size": f"{food.serving_quantity:g} {food.serving_unit or '(unit unverified)'}" if food.serving_quantity else "typical serving",
                 "calories": food.calories, "protein_g": food.protein_g, "carbs_g": food.carbs_g, "fat_g": food.fat_g,
                 "source_quality": getattr(food, "source_quality", None) or "unverified"}
                for food in foods[:12]]

    def _calculate(self, proposal, target: dict[str, float], allowed_food_ids: set[int] | None = None,
                   constraints: DietaryConstraints | None = None) -> dict[str, Any]:
        selected = []
        with self.session_factory() as session:
            for item in proposal.foods:
                if allowed_food_ids is not None and item.food_id not in allowed_food_ids:
                    raise MealPlanningAgentError("Meal planner selected a food outside the supplied candidate list.")
                food = session.get(Food, item.food_id)
                if food is None or (constraints and not constraints.permits(food)):
                    raise MealPlanningAgentError("Selected food does not meet the catalogue and dietary checks.")
                nutrition = self.calculator.calculate(food, FoodInput(food.name, item.quantity, item.unit))
                if nutrition.needs_review:
                    raise MealPlanningAgentError("A proposed portion cannot be converted reliably.")
                selected.append({"food_id": food.id, "food_name": food.name, "quantity": item.quantity, "unit": item.unit,
                                 "calories": nutrition.calories, "protein_g": nutrition.protein_g,
                                 "carbs_g": nutrition.carbs_g, "fat_g": nutrition.fat_g,
                                 "source_quality": getattr(food, "source_quality", None) or "unverified"})
        totals = {key: round(sum(item[key] for item in selected), 2) for key in ("calories", "protein_g", "carbs_g", "fat_g")}
        return {"meal_name": proposal.meal_name, "foods": selected, "nutrition": totals, "reason": proposal.reason,
                "within_target": self._within(totals, target), "target_for_next_meal": target,
                "nutrition_status": "catalogue_estimate"}

    def _within(self, actual, target) -> bool:
        tolerances = {"calories": self.config.calories_tolerance, "protein_g": self.config.protein_tolerance,
                      "carbs_g": self.config.carbs_tolerance}
        for key, tolerance in tolerances.items():
            if abs(actual[key] - target[key]) / max(target[key], 1) > tolerance:
                return False
        return actual["fat_g"] <= target["fat_g"] * (1 + self.config.fat_overage)
