"""Deterministic serving normalization used before cross-source comparison."""
from __future__ import annotations

import re

from services.nutrition_validation_models import NormalizedNutritionSource, NutritionSource
from services.portion_calculator import PortionCalculator


class NutritionNormalizer:
    _GRAM_UNITS = {"g", "gram", "grams"}

    def normalize(self, source: NutritionSource) -> NormalizedNutritionSource:
        quantity, unit = PortionCalculator.measured_quantity(source.serving_quantity or 0, source.serving_unit)
        if unit in {"g", "ml"} and quantity:
            factor = 100 / quantity
            return NormalizedNutritionSource(source, f"measured:100{unit}", f"100 {unit}", 100, unit,
                                             self._scale(source.calories, factor), self._scale(source.protein_g, factor),
                                             self._scale(source.carbs_g, factor), self._scale(source.fat_g, factor),
                                             f"Normalized to 100 {unit}")
        key = self._named_serving_key(source.serving_size)
        return NormalizedNutritionSource(source, key, source.serving_size, source.serving_quantity, unit,
                                         source.calories, source.protein_g, source.carbs_g, source.fat_g,
                                         None if key else "Serving size cannot be compared reliably")

    @staticmethod
    def _scale(value: float | None, factor: float) -> float | None:
        return round(value * factor, 2) if value is not None else None

    @staticmethod
    def _named_serving_key(serving_size: str | None) -> str | None:
        if not serving_size:
            return None
        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", serving_size.casefold()).split())
        return f"serving:{normalized}" if normalized else None
