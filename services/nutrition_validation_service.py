"""Coordinates deterministic evidence checks with the narrowly scoped validation agent."""
from __future__ import annotations

import logging
from typing import Any

from services.nutrition_normalizer import NutritionNormalizer
from services.nutrition_statistics import NutritionStatistics, NutritionStatisticsService
from services.nutrition_validation_agent import NutritionValidationAgent, NutritionValidationAgentError
from services.nutrition_validation_models import NutritionSource, ValidationDecision

logger = logging.getLogger(__name__)


class NutritionValidationService:
    def __init__(self, normalizer: NutritionNormalizer | None = None,
                 statistics: NutritionStatisticsService | None = None,
                 agent: NutritionValidationAgent | None = None) -> None:
        self.normalizer = normalizer or NutritionNormalizer()
        self.statistics = statistics or NutritionStatisticsService()
        self.agent = agent or NutritionValidationAgent()

    def validate(self, food_name: str, sources: list[NutritionSource]) -> tuple[NutritionStatistics, ValidationDecision]:
        normalized = [self.normalizer.normalize(source) for source in sources]
        stats = self.statistics.summarize(normalized)
        logger.info("Validating nutrition for: %s. Valid comparable sources: %s. Median calories: %s. Outliers: %s",
                    food_name, len(stats.comparable_sources), stats.median_calories, len(stats.outlier_sources))
        if stats.deterministic_status == "rejected":
            return stats, ValidationDecision("rejected", "low", 0.0, stats.reason)
        evidence = self._evidence(food_name, stats)
        try:
            agent_decision = self.agent.validate(evidence)
        except NutritionValidationAgentError:
            logger.warning("Validation agent failed; retaining deterministic uncertainty.")
            return stats, ValidationDecision("uncertain", "low", min(stats.deterministic_score, 0.4),
                                             "Validation agent was unavailable; deterministic checks are incomplete.")
        decision = self._constrain(agent_decision, stats)
        logger.info("Validation result: %s. Confidence: %s", decision.status, decision.confidence)
        return stats, decision

    @staticmethod
    def _constrain(agent: ValidationDecision, stats: NutritionStatistics) -> ValidationDecision:
        if stats.deterministic_status == "uncertain" and agent.status == "accepted":
            return ValidationDecision("uncertain", "low" if stats.deterministic_confidence == "low" else "medium",
                                      min(agent.confidence_score, stats.deterministic_score), stats.reason)
        if stats.deterministic_confidence == "low" and agent.confidence == "high":
            return ValidationDecision(agent.status, "low", min(agent.confidence_score, stats.deterministic_score), agent.reason)
        return agent

    @staticmethod
    def _evidence(food_name: str, stats: NutritionStatistics) -> dict[str, Any]:
        return {"food_name": food_name, "comparable_serving": stats.comparable_sources[0].serving_size,
                "source_count": len(stats.comparable_sources), "outlier_count": len(stats.outlier_sources),
                "median": {"calories": stats.median_calories, "protein_g": stats.median_protein_g,
                           "carbs_g": stats.median_carbs_g, "fat_g": stats.median_fat_g},
                "calorie_spread": stats.calorie_spread, "deterministic_assessment": {
                    "status": stats.deterministic_status, "confidence": stats.deterministic_confidence,
                    "score": stats.deterministic_score, "reason": stats.reason},
                "sources": [{"title": item.nutrition.source.title, "url": item.nutrition.source.url,
                             "serving_size": item.serving_size, "calories": item.calories,
                             "protein_g": item.protein_g, "carbs_g": item.carbs_g, "fat_g": item.fat_g}
                            for item in stats.comparable_sources]}
