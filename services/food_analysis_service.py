"""Food pipeline: local database first, then an isolated web nutrition fallback."""
from __future__ import annotations

import logging
from typing import Any

from database.database import get_session
from services.food_input_parser import FoodInputParser
from services.food_search_service import FoodSearchService
from services.portion_calculator import PortionCalculator, ServingNutrition
from services.web_nutrition_extractor import WebNutritionExtractionError, WebNutritionExtractor
from services.web_search import DuckDuckGoFoodSearchProvider, WebSearchError, WebSearchProvider
from services.nutrition_validation_service import NutritionValidationService

logger = logging.getLogger(__name__)


class FoodAnalysisService:
    def __init__(self, parser: FoodInputParser | None = None, search: FoodSearchService | None = None,
                 calculator: PortionCalculator | None = None, web_search: WebSearchProvider | None = None,
                 web_extractor: WebNutritionExtractor | None = None,
                 validator: NutritionValidationService | None = None, session_factory: Any = get_session) -> None:
        self.parser = parser or FoodInputParser()
        self.search = search or FoodSearchService()
        self.calculator = calculator or PortionCalculator()
        self.web_search = web_search or DuckDuckGoFoodSearchProvider()
        self.web_extractor = web_extractor or WebNutritionExtractor()
        self.validator = validator or NutritionValidationService()
        self.session_factory = session_factory

    def analyze(self, message: str) -> list[dict[str, Any]]:
        inputs = self.parser.parse(message)
        results: list[dict[str, Any]] = []
        with self.session_factory() as session:
            for input_food in inputs:
                logger.info("Food detected: %s", input_food.name)
                food = self.search.search(session, input_food.name)
                if food is None:
                    logger.info("Local DB search: no reliable match. Using web fallback.")
                    results.append(self._resolve_web(input_food))
                    continue
                nutrition = self.calculator.calculate(food, input_food)
                logger.info("Local DB search: matched %s", food.name)
                results.append({"input_food": input_food.name, "matched": True, "resolved": True,
                                "source_type": "local_database", "validation_status": "accepted",
                                "confidence": "high", "confidence_score": 1.0, "sources": [], "matched_food": {
                    "id": food.id, "name": food.name, "serving_size": nutrition.serving_size,
                    "calories": nutrition.calories, "protein_g": nutrition.protein_g,
                    "carbs_g": nutrition.carbs_g, "fat_g": nutrition.fat_g,
                }})
        return results

    def _resolve_web(self, input_food: Any) -> dict[str, Any]:
        try:
            results = self.web_search.search_food_web(input_food.name)
            logger.info("Web results retrieved: %s", len(results))
        except WebSearchError:
            logger.warning("Web search provider failed for a food lookup.")
            return self._unresolved(input_food.name, "Web search is currently unavailable.")
        if not results:
            return self._unresolved(input_food.name, "Unable to find nutrition search results.")

        try:
            extracted_sources = self.web_extractor.extract(input_food.name, results)
        except WebNutritionExtractionError as exc:
            logger.info("Web nutrition extraction did not resolve the food.")
            return self._unresolved(input_food.name, str(exc))

        stats, decision = self.validator.validate(input_food.name, extracted_sources)
        source_details = self._source_details(extracted_sources, stats)
        values = (stats.median_calories, stats.median_protein_g, stats.median_carbs_g, stats.median_fat_g)
        if decision.status == "rejected" or any(value is None for value in values):
            reason = decision.reason if decision.status == "rejected" else "Comparable sources have incomplete macro nutrition data."
            return {"input_food": input_food.name, "matched": False, "resolved": False, "source_type": "web",
                    "validation_status": "rejected" if decision.status == "rejected" else "uncertain",
                    "confidence": decision.confidence, "confidence_score": decision.confidence_score,
                    "matched_food": None, "sources": source_details, "reason": reason}
        base = stats.comparable_sources[0]
        serving = ServingNutrition(base.serving_quantity, base.serving_unit, float(stats.median_calories),
                                   float(stats.median_protein_g), float(stats.median_carbs_g), float(stats.median_fat_g),
                                   base.serving_size)
        nutrition = self.calculator.calculate_serving(serving, input_food)
        logger.info("Nutrition extracted and validated. Source: web")
        return {"input_food": input_food.name, "matched": False, "resolved": True, "source_type": "web",
                "validation_status": decision.status, "confidence": decision.confidence,
                "confidence_score": decision.confidence_score, "sources": source_details,
                "matched_food": {"name": input_food.name, "serving_size": nutrition.serving_size,
                                 "calories": nutrition.calories, "protein_g": nutrition.protein_g,
                                 "carbs_g": nutrition.carbs_g, "fat_g": nutrition.fat_g}}

    @staticmethod
    def _source_details(extracted_sources: list[Any], stats: Any) -> list[dict[str, Any]]:
        used_urls = {source.nutrition.source.url for source in stats.comparable_sources}
        outlier_urls = {source.nutrition.source.url for source in stats.outlier_sources}
        return [{"title": source.source.title, "url": source.source.url, "domain": source.source.domain,
                 "used": source.source.url in used_urls, "outlier": source.source.url in outlier_urls,
                 "serving_size": source.serving_size, "calories": source.calories,
                 "protein_g": source.protein_g, "carbs_g": source.carbs_g, "fat_g": source.fat_g}
                for source in extracted_sources]

    @staticmethod
    def _unresolved(input_food: str, reason: str) -> dict[str, Any]:
        return {"input_food": input_food, "matched": False, "resolved": False, "source_type": "web",
                "matched_food": None, "sources": [], "reason": reason}
