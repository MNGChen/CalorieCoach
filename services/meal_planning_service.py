"""Retrieve local candidates, ask planner for portions, then calculate nutrition deterministically."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from sqlalchemy import select
from database.database import get_session
from database.models import Food
from services.food_input_parser import FoodInput
from services.meal_planning_agent import MealPlanningAgent, MealPlanningAgentError
from services.portion_calculator import PortionCalculator


class RestaurantMenuUnavailable(MealPlanningAgentError):
    """The request names a restaurant that is absent from the verified local catalogue."""

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
    }
    def __init__(self, agent: MealPlanningAgent | None = None, calculator: PortionCalculator | None = None,
                 config: MealTargetConfig | None = None, session_factory: Any = get_session) -> None:
        self.agent, self.calculator, self.config, self.session_factory = agent or MealPlanningAgent(), calculator or PortionCalculator(), config or MealTargetConfig(), session_factory
    def recommend(self, coach_result: dict[str, Any], recent_foods: list[str] | None = None,
                  user_request: str = "") -> dict[str, Any]:
        target = coach_result.get("target_for_next_meal")
        if not target: raise ValueError("A daily nutrition target is required for meal recommendations.")
        restaurant = self.restaurant_for_request(user_request)
        candidates = self.retrieve_candidates(coach_result.get("priority", ""), recent_foods or [], restaurant)
        if restaurant and not candidates:
            raise RestaurantMenuUnavailable(restaurant)
        if not candidates: raise MealPlanningAgentError("No suitable local food candidates are available.")
        context = {"user_goal": coach_result.get("user_goal"), "remaining_today": coach_result.get("daily_summary", {}).get("remaining", {}), "target_for_next_meal": target, "strategy": coach_result.get("priority", ""), "recent_foods": recent_foods or [], "user_request": user_request, "restaurant": restaurant, "candidates": candidates}
        last: dict[str, Any] | None = None
        for attempt in range(2):
            if last: context["previous_calculated_meal"] = last
            proposal = self.agent.plan(context)
            calculated = self._calculate(proposal, target)
            if calculated["within_target"] or attempt == 1: return calculated
            last = calculated
        return last or {}
    @classmethod
    def restaurant_for_request(cls, request: str) -> str | None:
        value = request.casefold()
        for restaurant, aliases in cls.RESTAURANT_ALIASES.items():
            if any(alias in value for alias in aliases):
                return restaurant
        return None

    def retrieve_candidates(self, strategy: str, recent_foods: list[str], restaurant: str | None = None) -> list[dict[str, Any]]:
        with self.session_factory() as session: foods = list(session.scalars(select(Food)))
        if restaurant:
            aliases = self.RESTAURANT_ALIASES[restaurant]
            foods = [food for food in foods if any(alias in food.name.casefold() for alias in aliases)]
        recent = {name.casefold() for name in recent_foods}
        lean_first = "protein" in strategy.casefold()
        foods.sort(key=lambda food: ((food.fat_g / max(food.protein_g, 1)) if lean_first else 0, food.name.casefold() in recent, food.name))
        return [{"id": food.id, "name": food.name, "serving_size": f"{food.serving_quantity:g} {food.serving_unit}" if food.serving_quantity else "typical serving", "calories": food.calories, "protein_g": food.protein_g, "carbs_g": food.carbs_g, "fat_g": food.fat_g} for food in foods[:12]]
    def _calculate(self, proposal, target: dict[str, float]) -> dict[str, Any]:
        with self.session_factory() as session:
            selected = []
            for item in proposal.foods:
                food = session.get(Food, item.food_id)
                if food is None: raise MealPlanningAgentError("Meal planner selected a food outside the candidate database.")
                nutrition = self.calculator.calculate(food, FoodInput(food.name, item.quantity, item.unit.casefold()))
                selected.append({"food_id": food.id, "food_name": food.name, "quantity": item.quantity, "unit": item.unit, "calories": nutrition.calories, "protein_g": nutrition.protein_g, "carbs_g": nutrition.carbs_g, "fat_g": nutrition.fat_g})
        totals = {key: round(sum(item[key] for item in selected), 2) for key in ("calories", "protein_g", "carbs_g", "fat_g")}
        within = self._within(totals, target)
        return {"meal_name": proposal.meal_name, "foods": selected, "nutrition": totals, "reason": proposal.reason, "within_target": within, "target_for_next_meal": target}
    def _within(self, actual, target) -> bool:
        return (abs(actual["calories"]-target["calories"])/max(target["calories"],1) <= self.config.calories_tolerance and abs(actual["protein_g"]-target["protein_g"])/max(target["protein_g"],1) <= self.config.protein_tolerance and abs(actual["carbs_g"]-target["carbs_g"])/max(target["carbs_g"],1) <= self.config.carbs_tolerance and actual["fat_g"] <= target["fat_g"]*(1+self.config.fat_overage))
