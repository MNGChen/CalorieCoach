"""Read-only nutrition tools shared by the CalorieCoach MCP server."""
from __future__ import annotations

from typing import Any

from database.database import get_session, init_db
from database.models import Food
from services.food_search_service import FoodSearchService
from services.food_input_parser import FoodInput
from services.portion_calculator import PortionCalculator


class NutritionCatalogTools:
    """Expose the shared local food catalogue without accessing personal user data."""

    def __init__(self, search: FoodSearchService | None = None,
                 calculator: PortionCalculator | None = None) -> None:
        self.search = search or FoodSearchService()
        self.calculator = calculator or PortionCalculator()

    def search_local_food(self, query: str) -> dict[str, Any]:
        """Find the best local-catalogue match for a food description."""
        if not query.strip():
            raise ValueError("Provide a food name to search.")
        init_db()
        with get_session() as session:
            food = self.search.search(session, query)
            if food is None:
                return {"found": False, "query": query.strip(), "source": "caloriecoach_local_catalogue"}
            return {"found": True, "query": query.strip(), "source": "caloriecoach_local_catalogue",
                    "food": self._food_summary(food)}

    def get_food_nutrition(self, food_id: int, quantity: float | None = None,
                           unit: str | None = None) -> dict[str, Any]:
        """Return local-catalogue nutrition for a typical serving or a measured portion."""
        if quantity is not None and quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        init_db()
        with get_session() as session:
            food = session.get(Food, food_id)
            if food is None:
                raise ValueError("Food ID was not found in the local catalogue.")
            nutrition = self.calculator.calculate(food, FoodInput(food.name, quantity, unit.casefold() if unit else None))
        return {"source": "caloriecoach_local_catalogue", "food_id": food.id, "food_name": food.name,
                "category": getattr(food, "category", None), "serving_size": nutrition.serving_size,
                "calories": nutrition.calories, "protein_g": nutrition.protein_g,
                "carbs_g": nutrition.carbs_g, "fat_g": nutrition.fat_g,
                "portion_scaled": nutrition.scaled, "requires_review": nutrition.needs_review, "portion_note": nutrition.note}

    def lookup_food_nutrition(self, query: str, quantity: float | None = None,
                              unit: str | None = None) -> dict[str, Any]:
        """Match a food name and return nutrition in one tool call for an agent."""
        if not query.strip():
            raise ValueError("Provide a food name to search.")
        if quantity is not None and quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        init_db()
        with get_session() as session:
            food = self.search.search(session, query)
            if food is None:
                return {"found": False, "query": query.strip(), "source": "caloriecoach_local_catalogue"}
            nutrition = self.calculator.calculate(
                food, FoodInput(food.name, quantity, unit.casefold() if unit else None)
            )
            return {"found": True, "query": query.strip(), "matched_food": self._food_summary(food),
                    "source": "caloriecoach_local_catalogue", "serving_size": nutrition.serving_size,
                    "calories": nutrition.calories, "protein_g": nutrition.protein_g,
                    "carbs_g": nutrition.carbs_g, "fat_g": nutrition.fat_g,
                    "portion_scaled": nutrition.scaled, "requires_review": nutrition.needs_review, "portion_note": nutrition.note}

    @staticmethod
    def _food_summary(food: Food) -> dict[str, Any]:
        serving_size = (f"{food.serving_quantity:g} {food.serving_unit}"
                        if food.serving_quantity and food.serving_unit else "typical serving")
        return {"id": food.id, "name": food.name, "category": getattr(food, "category", None),
                "typical_serving": serving_size, "calories": food.calories,
                "protein_g": food.protein_g, "carbs_g": food.carbs_g, "fat_g": food.fat_g}
