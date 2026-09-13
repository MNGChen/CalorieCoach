"""Explainable deterministic checks and source statistics for nutrition validation."""
from __future__ import annotations

from dataclasses import dataclass
import statistics
import math
from services.source_identity import canonical_url, source_host

from services.nutrition_validation_models import NormalizedNutritionSource


@dataclass(frozen=True)
class ValidationConfig:
    max_calories: float = 5000
    max_macro_grams: float = 1000
    macro_calorie_tolerance: float = 0.45
    outlier_relative_threshold: float = 0.35
    close_spread_threshold: float = 0.10
    moderate_spread_threshold: float = 0.25


@dataclass(frozen=True)
class SourceCheck:
    source: NormalizedNutritionSource
    valid: bool
    reason: str | None


@dataclass(frozen=True)
class NutritionStatistics:
    comparable_sources: list[NormalizedNutritionSource]
    outlier_sources: list[NormalizedNutritionSource]
    median_calories: float | None
    median_protein_g: float | None
    median_carbs_g: float | None
    median_fat_g: float | None
    calorie_spread: float | None
    deterministic_status: str
    deterministic_confidence: str
    deterministic_score: float
    reason: str


class NutritionStatisticsService:
    def __init__(self, config: ValidationConfig | None = None) -> None:
        self.config = config or ValidationConfig()

    def check_source(self, source: NormalizedNutritionSource) -> SourceCheck:
        values = (source.calories, source.protein_g, source.carbs_g, source.fat_g)
        if source.calories is None:
            return SourceCheck(source, False, "Calories are missing.")
        if any(value is not None and (not math.isfinite(value) or value < 0) for value in values):
            return SourceCheck(source, False, "Nutrition values cannot be negative.")
        if source.calories > self.config.max_calories or any(
            value is not None and value > self.config.max_macro_grams for value in values[1:]
        ):
            return SourceCheck(source, False, "Nutrition values exceed plausible serving limits.")
        if all(value is not None for value in values):
            macro_calories = source.protein_g * 4 + source.carbs_g * 4 + source.fat_g * 9  # type: ignore[operator]
            difference = abs(source.calories - macro_calories) / max(source.calories, 1)
            if difference > self.config.macro_calorie_tolerance:
                return SourceCheck(source, False, "Reported calories conflict with macro calories.")
        return SourceCheck(source, True, None)

    def summarize(self, sources: list[NormalizedNutritionSource]) -> NutritionStatistics:
        sources = list({canonical_url(source.nutrition.source.url): source for source in sources}.values())
        valid = [check.source for check in map(self.check_source, sources) if check.valid and check.source.comparison_key]
        if not valid:
            return self._result([], [], "rejected", "low", 0.0, "No valid sources with a comparable serving size.")
        groups: dict[str, list[NormalizedNutritionSource]] = {}
        for source in valid:
            groups.setdefault(source.comparison_key or "", []).append(source)
        comparable = max(groups.values(), key=len)
        outliers = self._outliers(comparable)
        # Do not discard the majority in a three-way conflict: it is evidence of disagreement, not two outliers.
        retained = comparable if len(outliers) * 2 >= len(comparable) else [x for x in comparable if x not in outliers]
        median_calories = self._median(retained, "calories")
        median_protein = self._median(retained, "protein_g")
        median_carbs = self._median(retained, "carbs_g")
        median_fat = self._median(retained, "fat_g")
        spread = self._spread(retained, "calories", median_calories)
        independent_hosts = {source_host(item.nutrition.source.url) for item in retained}
        if len(independent_hosts) >= 3 and spread is not None and spread <= self.config.close_spread_threshold:
            status, confidence, score, reason = "accepted", "high", 0.90, "Multiple comparable sources closely agree."
        elif len(independent_hosts) >= 2 and spread is not None and spread <= self.config.moderate_spread_threshold:
            status, confidence, score, reason = "accepted", "medium", 0.70, "Comparable sources show moderate agreement."
        elif len(independent_hosts) == 1 and (spread is None or spread <= self.config.moderate_spread_threshold):
            status, confidence, score, reason = "uncertain", "medium", 0.45, "Only one independent nutrition website is available."
        else:
            status, confidence, score, reason = "uncertain", "low", 0.25, "Comparable sources report significantly different values."
        if any(value is None for value in (median_protein, median_carbs, median_fat)):
            status, confidence, score, reason = "uncertain", "low", min(score, 0.35), "Comparable sources have incomplete macro nutrition data."
        return NutritionStatistics(retained, outliers, median_calories, median_protein, median_carbs, median_fat, spread,
                                   status, confidence, score, reason)

    def _outliers(self, sources: list[NormalizedNutritionSource]) -> list[NormalizedNutritionSource]:
        if len(sources) < 3:
            return []
        median = self._median(sources, "calories")
        if not median:
            return []
        return [source for source in sources if source.calories is not None
                and abs(source.calories - median) / median > self.config.outlier_relative_threshold]

    @staticmethod
    def _median(sources: list[NormalizedNutritionSource], field: str) -> float | None:
        values = [getattr(source, field) for source in sources if getattr(source, field) is not None]
        return round(float(statistics.median(values)), 2) if values else None

    @staticmethod
    def _spread(sources: list[NormalizedNutritionSource], field: str, median: float | None) -> float | None:
        values = [getattr(source, field) for source in sources if getattr(source, field) is not None]
        return round((max(values) - min(values)) / median, 4) if values and median else None

    def _result(self, comparable: list[NormalizedNutritionSource], outliers: list[NormalizedNutritionSource],
                status: str, confidence: str, score: float, reason: str) -> NutritionStatistics:
        return NutritionStatistics(comparable, outliers, None, None, None, None, None, status, confidence, score, reason)
