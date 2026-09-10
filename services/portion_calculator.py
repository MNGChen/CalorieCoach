"""Deterministic nutrition scaling for compatible, measured portions."""
from __future__ import annotations

from dataclasses import dataclass

from database.models import Food
from services.food_input_parser import FoodInput


@dataclass(frozen=True)
class PortionNutrition:
    serving_size: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    scaled: bool


@dataclass(frozen=True)
class ServingNutrition:
    """Nutrition facts for one declared serving, from any trusted source."""

    serving_quantity: float | None
    serving_unit: str | None
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    serving_size: str | None = None


class PortionCalculator:
    _WEIGHT_UNITS = {"g", "gram", "grams"}

    def calculate(self, food: Food, input_food: FoodInput) -> PortionNutrition:
        serving = ServingNutrition(food.serving_quantity, food.serving_unit, food.calories, food.protein_g,
                                   food.carbs_g, food.fat_g)
        return self.calculate_serving(serving, input_food)

    def calculate_serving(self, serving: ServingNutrition, input_food: FoodInput) -> PortionNutrition:
        factor = 1.0
        scaled = False
        if (input_food.quantity is not None and input_food.unit in self._WEIGHT_UNITS
                and serving.serving_quantity and serving.serving_unit == "g"):
            factor = input_food.quantity / serving.serving_quantity
            scaled = True
        serving_size = f"{input_food.quantity:g} g" if scaled else self._serving_label(serving)
        return PortionNutrition(serving_size, round(serving.calories * factor, 2), round(serving.protein_g * factor, 2),
                                round(serving.carbs_g * factor, 2), round(serving.fat_g * factor, 2), scaled)

    @staticmethod
    def _serving_label(serving: ServingNutrition) -> str:
        if serving.serving_size:
            return serving.serving_size
        return f"{serving.serving_quantity:g} {serving.serving_unit}" if serving.serving_quantity and serving.serving_unit else "typical serving"
