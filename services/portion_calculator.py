"""Deterministic nutrition scaling for compatible, measured portions."""
from __future__ import annotations

from dataclasses import dataclass
import math

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
    needs_review: bool = False
    note: str = ""


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
    _UNITS = {"gram": "g", "grams": "g", "克": "g", "kg": "kg", "kilograms": "kg",
              "milliliter": "ml", "milliliters": "ml", "毫升": "ml", "litre": "l", "liter": "l",
              "pieces": "piece", "个": "piece", "eggs": "piece", "bowls": "bowl", "碗": "bowl",
              "servings": "serving", "份": "serving", "cups": "cup", "杯": "cup"}

    @classmethod
    def normalize_unit(cls, unit: str | None) -> str | None:
        value = unit.strip().casefold() if unit else None
        return cls._UNITS.get(value, value)

    @classmethod
    def measured_quantity(cls, quantity: float, unit: str | None) -> tuple[float, str | None]:
        normalized = cls.normalize_unit(unit)
        if normalized in {"kg", "l"}:
            return quantity * 1000, {"kg": "g", "l": "ml"}[normalized]
        return quantity, normalized

    def calculate(self, food: Food, input_food: FoodInput) -> PortionNutrition:
        serving = ServingNutrition(food.serving_quantity, food.serving_unit, food.calories, food.protein_g,
                                   food.carbs_g, food.fat_g)
        return self.calculate_serving(serving, input_food)

    def calculate_serving(self, serving: ServingNutrition, input_food: FoodInput) -> PortionNutrition:
        factor = 1.0
        scaled = False
        note = ""
        quantity = input_food.quantity
        if quantity is not None:
            if isinstance(quantity, bool) or not math.isfinite(quantity) or quantity <= 0:
                raise ValueError("Quantity must be a finite positive number.")
            requested, unit = self.measured_quantity(quantity, input_food.unit)
            base, base_unit = self.measured_quantity(serving.serving_quantity or 0, serving.serving_unit)
            if unit == "serving":
                factor, scaled = quantity, True
            elif base > 0 and unit is not None and unit == base_unit:
                factor, scaled = requested / base, True
            else:
                note = (f"Cannot convert {quantity:g} {input_food.unit or '(unit missing)'} to "
                        f"{self._serving_label(serving)}. Values shown are for the reference portion; confirm or edit them.")
        else:
            note = "No portion was supplied. Confirm the reference portion or edit the nutrition values."
        serving_size = f"{quantity:g} {self.normalize_unit(input_food.unit)}" if scaled else self._serving_label(serving)
        return PortionNutrition(serving_size, round(serving.calories * factor, 2), round(serving.protein_g * factor, 2),
                                round(serving.carbs_g * factor, 2), round(serving.fat_g * factor, 2), scaled, bool(note), note)

    @staticmethod
    def _serving_label(serving: ServingNutrition) -> str:
        if serving.serving_size:
            return serving.serving_size
        if serving.serving_quantity:
            return f"{serving.serving_quantity:g} {serving.serving_unit or '(unit unverified)'}"
        return "typical serving"
