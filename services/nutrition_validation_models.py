"""Data contracts shared by web extraction, normalization, and validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from services.web_search import WebSearchResult


@dataclass(frozen=True)
class NutritionSource:
    source: WebSearchResult
    serving_size: str | None
    serving_quantity: float | None
    serving_unit: str | None
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None


@dataclass(frozen=True)
class NormalizedNutritionSource:
    nutrition: NutritionSource
    comparison_key: str | None
    serving_size: str | None
    serving_quantity: float | None
    serving_unit: str | None
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    normalization_note: str | None = None


@dataclass(frozen=True)
class ValidationDecision:
    status: Literal["accepted", "uncertain", "rejected"]
    confidence: Literal["high", "medium", "low"]
    confidence_score: float
    reason: str
