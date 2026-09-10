"""Schema-validated, per-source nutrition extraction from web search evidence."""
from __future__ import annotations

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field

from ai.prompts import WEB_NUTRITION_EXTRACTION_PROMPT
from config import GEMINI_API_KEY, GEMINI_MODEL
from services.nutrition_validation_models import NutritionSource
from services.web_search import WebSearchResult


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
    """Uses Gemini only to extract supported facts, retaining each cited source."""

    def __init__(self, chain: Any | None = None) -> None:
        self.chain = chain or self._build_chain()

    @staticmethod
    def _build_chain() -> Any:
        if not GEMINI_API_KEY:
            raise WebNutritionExtractionError("GEMINI_API_KEY is not configured.")
        prompt = ChatPromptTemplate.from_messages([
            ("system", WEB_NUTRITION_EXTRACTION_PROMPT),
            ("human", "Food: {food_name}\n\nSearch results:\n{search_results}"),
        ])
        llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GEMINI_API_KEY, temperature=0)
        return prompt | llm.with_structured_output(WebNutritionExtractionSchema)

    def extract(self, food_name: str, results: list[WebSearchResult]) -> list[NutritionSource]:
        if not results:
            raise WebNutritionExtractionError("Web search returned no results.")
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
        for item in parsed.sources:
            result = result_by_url.get(item.source_url)
            if result is None:
                raise WebNutritionExtractionError("The nutrition extraction cited an unknown source.")
            sources.append(NutritionSource(result, item.serving_size.strip() if item.serving_size else None,
                                           item.serving_quantity, item.serving_unit.strip().casefold() if item.serving_unit else None,
                                           item.calories, item.protein_g, item.carbs_g, item.fat_g))
        return sources
