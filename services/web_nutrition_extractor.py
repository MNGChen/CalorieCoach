"""Schema-validated, per-source nutrition extraction from web search evidence."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai.prompts import WEB_NUTRITION_EXTRACTION_PROMPT
from ai.openai_client import OpenAIStructuredChain, OpenAIServiceError
from services.nutrition_validation_models import NutritionSource
from services.web_search import WebSearchResult
from services.source_identity import canonical_url


class WebNutritionExtractionError(RuntimeError):
    """Search results could not be converted to structured source evidence."""


class WebNutritionSourceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str = Field(min_length=1)
    serving_size: str | None = None
    serving_quantity: float | None = Field(default=None, gt=0)
    serving_unit: str | None = None
    calories: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)


class WebNutritionExtractionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food_name: str = Field(min_length=1)
    sources: list[WebNutritionSourceSchema] = Field(min_length=1, max_length=5)


class WebNutritionExtractor:
    """Uses OpenAI only to extract supported facts, retaining each cited source."""

    def __init__(self, chain: Any | None = None) -> None:
        self.chain = chain or self._build_chain()

    @staticmethod
    def _build_chain() -> Any:
        try:
            return OpenAIStructuredChain(WEB_NUTRITION_EXTRACTION_PROMPT,
                                         "Food: {food_name}\n\nSearch results:\n{search_results}",
                                         WebNutritionExtractionSchema)
        except OpenAIServiceError as exc:
            raise WebNutritionExtractionError(str(exc)) from exc

    def extract(self, food_name: str, results: list[WebSearchResult]) -> list[NutritionSource]:
        if not results:
            raise WebNutritionExtractionError("Web search returned no results.")
        if any(result.nutrition_extracted for result in results):
            return [NutritionSource(result, result.serving_size, result.serving_quantity, result.serving_unit,
                                    result.calories, result.protein_g, result.carbs_g, result.fat_g)
                    for result in results if result.nutrition_extracted]
        search_text = "\n\n".join(
            f"Title: {result.title}\nSnippet: {result.snippet}\nURL: {result.url}" for result in results
        )
        try:
            data = self.chain.invoke({"food_name": food_name, "search_results": search_text})
            parsed = data if isinstance(data, WebNutritionExtractionSchema) else WebNutritionExtractionSchema.model_validate(data)
        except Exception as exc:
            raise WebNutritionExtractionError("Unable to extract valid nutrition information from web results.") from exc
        result_by_url = {result.url: result for result in results}
        sources: list[NutritionSource] = []
        seen = set()
        for item in parsed.sources:
            result = result_by_url.get(item.source_url)
            if result is None:
                raise WebNutritionExtractionError("The nutrition extraction cited an unknown source.")
            identity = canonical_url(item.source_url)
            if identity in seen:
                continue
            seen.add(identity)
            sources.append(NutritionSource(result, item.serving_size.strip() if item.serving_size else None,
                                           item.serving_quantity, item.serving_unit.strip().casefold() if item.serving_unit else None,
                                           item.calories, item.protein_g, item.carbs_g, item.fat_g))
        return sources
