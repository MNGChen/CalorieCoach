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
from services.demo_data_service import DemoDataError, DemoDataService
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
        self.nutrition = NutritionService(session_factory, username="test-user")
        profile = self.nutrition.save_profile(age=30, gender="Male", height_cm=180, weight_kg=80,
                                    activity_level="Moderately Active", goal="Maintenance")
        self.daily = DailyNutritionService(self.nutrition)
        self.logger = MealLoggingService(self.daily, session_factory, user_id=profile.id)
        self.meals = MealService(session_factory, user_id=profile.id)
        self.day = date(2026, 9, 11)

    def tearDown(self) -> None:
        self.engine.dispose()

    @staticmethod
    def resolved(name: str = "Egg", calories: float = 75, protein: float = 6, carbs: float = 1, fat: float = 5,
                 source_type: str = "local_database", confidence: str = "high") -> dict:
        return {"input_food": name, "quantity": 1, "unit": "piece", "resolved": True, "review_confirmed": True,
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

    def test_custom_targets_override_calculated_targets(self) -> None:
        profile = self.nutrition.save_profile(custom_calorie_goal=2100, custom_protein_goal_g=150,
                                               custom_carbs_goal_g=225, custom_fat_goal_g=70)
        targets = self.nutrition.targets(profile)
        self.assertEqual((targets.calorie_goal, targets.protein_goal_g, targets.carbs_goal_g, targets.fat_goal_g),
                         (2100, 150, 225, 70))

    def test_review_note_is_retained_with_source_provenance(self) -> None:
        item = self.resolved()
        item["validation_status"] = "user_reviewed"
        item["review_note"] = "Nutrition estimate reviewed or adjusted by user before saving."
        response = self.logger.save_resolved("Egg", [item], log_date=self.day)
        saved = response["meal"]["items"][0]
        self.assertEqual(saved["validation_status"], "user_reviewed")
        self.assertEqual(saved["notes"], item["review_note"])
        self.assertEqual(saved["source_urls"], ["https://example.com/facts"])

    def test_username_scopes_profiles_and_food_logs(self) -> None:
        alice_nutrition = NutritionService(self.session_factory, username="alice")
        bob_nutrition = NutritionService(self.session_factory, username="bob")
        alice = alice_nutrition.save_profile(age=30, gender="Female", height_cm=165, weight_kg=60,
                                             activity_level="Lightly Active", goal="Maintenance")
        bob = bob_nutrition.save_profile(age=31, gender="Male", height_cm=180, weight_kg=82,
                                         activity_level="Moderately Active", goal="Muscle Gain")
        alice_meals = MealService(self.session_factory, user_id=alice.id)
        bob_meals = MealService(self.session_factory, user_id=bob.id)
        alice_meals.add_log(food_name="Alice meal", meal_type="Lunch", calories=400, protein_g=20,
                            carbs_g=40, fat_g=10, log_date=self.day)
        bob_meals.add_log(food_name="Bob meal", meal_type="Dinner", calories=800, protein_g=50,
                          carbs_g=70, fat_g=25, log_date=self.day)
        self.assertEqual([item.food_name for item in alice_meals.logs(self.day, self.day)], ["Alice meal"])
        self.assertEqual([item.food_name for item in bob_meals.logs(self.day, self.day)], ["Bob meal"])
        self.assertEqual(alice_nutrition.daily_totals(self.day)["calories"], 400.0)
        self.assertEqual(bob_nutrition.daily_totals(self.day)["calories"], 800.0)

    def test_demo_data_creates_a_two_week_history_only_for_empty_username(self) -> None:
        nutrition = NutritionService(self.session_factory, username="demo-user")
        response = DemoDataService(nutrition, MealService(self.session_factory, user_id=-1)).load()
        profile = nutrition.get_profile()
        self.assertIsNotNone(profile)
        self.assertEqual((response["meals_added"], response["weights_added"]), (42, 5))
        self.assertEqual(len(MealService(self.session_factory, user_id=profile.id).logs()), 42)  # type: ignore[union-attr]
        with self.assertRaises(DemoDataError):
            DemoDataService(nutrition, MealService(self.session_factory, user_id=profile.id)).load()  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
