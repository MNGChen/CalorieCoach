from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base
from database.models import FoodLog
from services.daily_nutrition_service import DailyNutritionService
from services.meal_logging_service import MealLoggingService
from services.meal_service import MealService
from services.nutrition_service import NutritionService


class MealLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.engine = engine
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)

        @contextmanager
        def session_factory():
            session = sessions()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        self.session_factory = session_factory
        self.nutrition = NutritionService(session_factory)
        self.nutrition.save_profile(age=30, gender="Male", height_cm=180, weight_kg=80,
                                    activity_level="Moderately Active", goal="Maintenance")
        self.daily = DailyNutritionService(self.nutrition)
        self.logger = MealLoggingService(self.daily, session_factory)
        self.meals = MealService(session_factory)
        self.day = date(2026, 9, 11)

    def tearDown(self) -> None:
        self.engine.dispose()

    @staticmethod
    def resolved(name: str = "Egg", calories: float = 75, protein: float = 6, carbs: float = 1, fat: float = 5,
                 source_type: str = "local_database", confidence: str = "high") -> dict:
        return {"input_food": name, "quantity": 1, "unit": "piece", "resolved": True,
                "source_type": source_type, "validation_status": "accepted", "confidence": confidence,
                "confidence_score": 0.9, "sources": [{"url": "https://example.com/facts"}],
                "matched_food": {"name": name, "calories": calories, "protein_g": protein,
                                 "carbs_g": carbs, "fat_g": fat, "serving_size": "1 piece"}}

    def _count(self) -> int:
        with self.session_factory() as session:
            return int(session.scalar(select(func.count(FoodLog.id))) or 0)

    def test_save_one_resolved_food_and_provenance(self) -> None:
        response = self.logger.save_resolved("I ate one egg for breakfast", [self.resolved()], log_date=self.day)
        item = response["meal"]["items"][0]
        self.assertEqual(self._count(), 1)
        self.assertEqual(item["source_type"], "local_database")
        self.assertEqual(item["source_urls"], ["https://example.com/facts"])
        self.assertEqual(self.meals.logs(self.day, self.day)[0].meal_type, "Breakfast")

    def test_save_multiple_foods_and_daily_aggregation(self) -> None:
        response = self.logger.save_resolved("Lunch", [self.resolved("Chicken", 330, 62, 0, 7),
                                                          self.resolved("Egg")], "Lunch", self.day)
        self.assertEqual(len(response["meal"]["items"]), 2)
        self.assertEqual(response["daily_summary"]["consumed"],
                         {"calories": 405.0, "protein_g": 68.0, "carbs_g": 1.0, "fat_g": 12.0})

    def test_remaining_allows_exceeded_targets(self) -> None:
        self.logger.save_resolved("Large meal", [self.resolved("Large", 10000, 100, 100, 100)], "Dinner", self.day)
        summary = self.daily.summary(self.day)
        self.assertLess(summary["remaining"]["calories"], 0)

    def test_web_and_low_confidence_metadata_are_preserved(self) -> None:
        item = self.resolved("Ramen", 500, 20, 60, 15, "web", "low")
        item["validation_status"] = "uncertain"
        response = self.logger.save_resolved("Ramen", [item], log_date=self.day)
        saved = response["meal"]["items"][0]
        self.assertEqual((saved["source_type"], saved["validation_status"], saved["confidence"]),
                         ("web", "uncertain", "low"))

    def test_unresolved_or_invalid_batch_is_not_stored(self) -> None:
        with self.assertRaises(ValueError):
            self.logger.save_resolved("Unknown", [{"resolved": False}], log_date=self.day)
        invalid = self.resolved("Invalid", -1)
        with self.assertRaises(ValueError):
            self.logger.save_resolved("Mixed", [self.resolved(), invalid], log_date=self.day)
        self.assertEqual(self._count(), 0)

    def test_duplicate_request_is_idempotent(self) -> None:
        first = self.logger.save_resolved("Egg", [self.resolved()], log_date=self.day, request_id="request-1")
        duplicate = self.logger.save_resolved("Egg", [self.resolved()], log_date=self.day, request_id="request-1")
        self.assertFalse(first["meal"]["duplicate"])
        self.assertTrue(duplicate["meal"]["duplicate"])
        self.assertEqual(self._count(), 1)

    def test_delete_updates_daily_totals_and_dates_are_local_days(self) -> None:
        first = self.logger.save_resolved("Egg", [self.resolved()], log_date=self.day)
        next_day = self.day + timedelta(days=1)
        self.logger.save_resolved("Egg", [self.resolved("Egg", 100)], log_date=next_day)
        self.assertEqual(self.daily.summary(self.day)["consumed"]["calories"], 75.0)
        self.assertEqual(self.daily.summary(next_day)["consumed"]["calories"], 100.0)
        first_log_id = first["meal"]["items"][0]["id"]
        self.meals.update_log(first_log_id, calories=80)
        self.assertEqual(self.daily.summary(self.day)["consumed"]["calories"], 80.0)
        self.meals.delete_log(first_log_id)
        self.assertEqual(self.daily.summary(self.day)["consumed"]["calories"], 0.0)


if __name__ == "__main__":
    unittest.main()
