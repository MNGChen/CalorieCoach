"""Atomic persistence of resolved food pipeline results into existing food logs."""
from __future__ import annotations

from datetime import date
import json
import logging
import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from database.database import get_session
from database.models import FoodLog
from services.daily_nutrition_service import DailyNutritionService

logger = logging.getLogger(__name__)


class MealLoggingService:
    _MEAL_TYPES = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "snack": "Snack"}

    def __init__(self, daily_nutrition: DailyNutritionService | None = None, session_factory: Any = get_session,
                 user_id: int | None = None) -> None:
        self.daily_nutrition = daily_nutrition or DailyNutritionService()
        self.session_factory = session_factory
        self.user_id = user_id

    def save_resolved(self, original_input: str, resolved_items: list[dict[str, Any]], meal_type: str | None = None,
                      log_date: date | None = None, request_id: str | None = None) -> dict[str, Any]:
        if self.user_id is not None and self.user_id < 0:
            raise ValueError("Complete a personal profile before saving food estimates.")
        day = log_date or date.today()
        resolved = [item for item in resolved_items if item.get("resolved") is True]
        if not resolved:
            raise ValueError("No resolved food items are available to save.")
        resolved_meal_type = self._meal_type(meal_type, original_input)
        idempotency_key = request_id or str(uuid4())
        with self.session_factory() as session:
            existing_query = select(FoodLog).where(FoodLog.idempotency_key == idempotency_key)
            if self.user_id is not None:
                existing_query = existing_query.where(FoodLog.user_id == self.user_id)
            existing = session.scalar(existing_query.limit(1))
            if existing is not None:
                logger.info("Duplicate meal submission ignored.")
                entries_query = select(FoodLog).where(FoodLog.meal_id == existing.meal_id)
                if self.user_id is not None:
                    entries_query = entries_query.where(FoodLog.user_id == self.user_id)
                entries = list(session.scalars(entries_query))
                return self._response(existing.meal_id or "", entries, day, duplicate=True)
            meal_id = str(uuid4())
            entries = [self._to_log(item, meal_id, original_input, resolved_meal_type, day, idempotency_key)
                       for item in resolved]
            session.add_all(entries)
            session.flush()
            for entry in entries:
                session.refresh(entry)
            logger.info("Meal saved successfully. Resolved food items: %s. Meal calories: %.0f", len(entries),
                        sum(entry.calories for entry in entries))
        return self._response(meal_id, entries, day, duplicate=False)

    def _response(self, meal_id: str, entries: list[FoodLog], day: date, duplicate: bool) -> dict[str, Any]:
        logger.info("Recalculating daily nutrition.")
        return {"meal": {"id": meal_id, "duplicate": duplicate, "items": [self._serialize(entry) for entry in entries]},
                "daily_summary": self.daily_nutrition.summary(day)}

    def _to_log(self, item: dict[str, Any], meal_id: str, original_input: str, meal_type: str, day: date,
                idempotency_key: str) -> FoodLog:
        food = item.get("matched_food")
        if not isinstance(food, dict):
            raise ValueError("Resolved food item is missing nutrition details.")
        name = str(food.get("name", "")).strip()
        nutrients = {key: food.get(key) for key in ("calories", "protein_g", "carbs_g", "fat_g")}
        if not name or any(isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
                           for value in nutrients.values()):
            raise ValueError("Resolved food has invalid nutrition data.")
        quantity = item.get("quantity")
        if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or quantity <= 0):
            raise ValueError("Resolved food has an invalid quantity.")
        sources = item.get("sources", [])
        urls = [source["url"] for source in sources if isinstance(source, dict) and isinstance(source.get("url"), str)]
        review_note = str(item.get("review_note", "")).strip()
        return FoodLog(user_id=self.user_id, meal_id=meal_id, original_input=original_input.strip(), meal_type=meal_type, food_name=name,
                       quantity=float(quantity) if quantity is not None else None, unit=item.get("unit"),
                       calories=float(nutrients["calories"]), protein_g=float(nutrients["protein_g"]),
                       carbs_g=float(nutrients["carbs_g"]), fat_g=float(nutrients["fat_g"]),
                       source_type=str(item.get("source_type", "")) or None,
                       validation_status=str(item.get("validation_status", "")) or None,
                       confidence=str(item.get("confidence", "")) or None,
                       confidence_score=float(item["confidence_score"]) if isinstance(item.get("confidence_score"), (int, float)) else None,
                       source_urls=json.dumps(urls), notes=review_note or None,
                       idempotency_key=idempotency_key, log_date=day)

    @classmethod
    def _meal_type(cls, explicit: str | None, original_input: str) -> str:
        normalized = (explicit or "").strip().casefold()
        if normalized in cls._MEAL_TYPES:
            return cls._MEAL_TYPES[normalized]
        for key, label in cls._MEAL_TYPES.items():
            if re.search(rf"\b{key}\b", original_input, re.IGNORECASE):
                return label
        return "Unknown"

    @staticmethod
    def _serialize(entry: FoodLog) -> dict[str, Any]:
        return {"id": entry.id, "food_name": entry.food_name, "quantity": entry.quantity, "unit": entry.unit,
                "calories": entry.calories, "protein_g": entry.protein_g, "carbs_g": entry.carbs_g,
                "fat_g": entry.fat_g, "source_type": entry.source_type, "validation_status": entry.validation_status,
                "confidence": entry.confidence, "confidence_score": entry.confidence_score,
                "source_urls": json.loads(entry.source_urls or "[]"), "notes": entry.notes}
