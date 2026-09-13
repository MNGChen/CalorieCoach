from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from database.database import get_session
from database.models import FoodLog, Food, KnowledgeChunk, UserProfile
from services.daily_nutrition_service import DailyNutritionService
from services.dietary_constraints import DietaryConstraints
from services.food_review_service import new_draft, review_items
from services.knowledge_base_service import KnowledgeBaseService
from services.meal_budget_service import next_meal_budget
from services.meal_logging_service import MealLoggingService
from services.meal_planning_service import MealPlanningService
from services.meal_planning_agent import MealPlanningAgentError, MealPlanSchema
from services.meal_service import MealService
from services.memory_service import MemoryService
from services.nutrition_orchestrator import NutritionOrchestrator
from services.nutrition_router import NutritionRouter
from services.nutrition_service import NutritionService
from services.portion_calculator import PortionCalculator, ServingNutrition
from services.food_input_parser import FoodInput
from tests.support import DatabaseTest, resolved_food


class PortionAndRoutingTests(unittest.TestCase):
    def test_counts_volume_and_weight_scale_in_compatible_units(self):
        calculator = PortionCalculator()
        examples = [(1, "piece", 3, "pieces", 225), (250, "ml", .5, "l", 150),
                    (100, "g", .2, "kg", 150), (300, None, 2, "serving", 150)]
        for base, unit, quantity, requested, expected in examples:
            with self.subTest(unit=requested):
                actual = calculator.calculate_serving(ServingNutrition(base, unit, 75, 6, 1, 5), FoodInput("food", quantity, requested))
                self.assertEqual(actual.calories, expected)
                self.assertFalse(actual.needs_review)

    def test_unknown_conversion_never_claims_measured_portion(self):
        result = PortionCalculator().calculate_serving(ServingNutrition(100, "g", 75, 6, 1, 5), FoodInput("egg", 3, "piece"))
        self.assertFalse(result.scaled)
        self.assertTrue(result.needs_review)
        self.assertIn("Cannot convert", result.note)

    def test_completed_meals_are_not_restaurant_recommendations(self):
        router = NutritionRouter()
        for message in ("I ate chicken rice for lunch", "I ate KFC", "I had two eggs for dinner", "我午餐吃了鸡饭"):
            self.assertEqual(router.route(message).intent, "log_food")
        mixed = router.route("I had chicken rice for lunch — what should I eat for dinner?")
        self.assertEqual(mixed.intent, "log_food")
        self.assertEqual(mixed.follow_up_request, "what should I eat for dinner?")

    def test_hypothetical_food_is_not_automatically_logged(self):
        chain = Mock()
        chain.invoke.return_value = {"intent": "nutrition_question", "confidence": .9}
        self.assertEqual(NutritionRouter(chain).route("What if I ate KFC for dinner?").intent, "nutrition_question")
        chain.invoke.assert_called_once()

    def test_meal_budget_does_not_consume_all_remaining_daily_calories(self):
        summary = {"target": {"calories": 2000, "protein_g": 120, "carbs_g": 250, "fat_g": 60},
                   "remaining": {"calories": 1600, "protein_g": 100, "carbs_g": 200, "fat_g": 45}}
        budget = next_meal_budget(summary, [{"meal_type": "Breakfast"}], "What should I eat next?")
        self.assertEqual(budget["calories"], 700)
        self.assertLess(budget["calories"], summary["remaining"]["calories"])


class PersistenceTests(DatabaseTest):
    def logger(self):
        nutrition, profile = self.profile()
        return MealLoggingService(DailyNutritionService(nutrition), user_id=profile.id), profile

    def test_chat_prepares_all_foods_without_saving_uncertain_or_partial_results(self):
        logger, profile = self.logger()
        food = Mock()
        food.analyze.return_value = [resolved_food(review_confirmed=False), {"resolved": False, "input_food": "unknown"}]
        response = NutritionOrchestrator(food_analysis=food, meal_logging=logger).handle("I ate eggs and unknown food")
        self.assertEqual(len(response["data"]["pending_foods"]), 2)
        self.assertEqual(MealService(user_id=profile.id).logs(), [])

    def test_unreviewed_and_partial_batches_are_rejected_atomically(self):
        logger, profile = self.logger()
        for items in ([resolved_food(review_confirmed=False)], [resolved_food(), {"resolved": False}]):
            with self.assertRaises(ValueError):
                logger.save_resolved("meal", items)
        self.assertEqual(MealService(user_id=profile.id).logs(), [])

    def test_concurrent_retry_saves_a_meal_once(self):
        logger, profile = self.logger()
        def submit(_):
            return logger.save_resolved("egg", [resolved_food()], request_id="same-submission")
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(submit, range(2)))
        self.assertEqual(len(MealService(user_id=profile.id).logs()), 1)
        self.assertEqual(sorted(result["meal"]["duplicate"] for result in responses), [False, True])

    def test_reused_submission_id_rejects_changed_payload(self):
        logger, _ = self.logger()
        logger.save_resolved("egg", [resolved_food()], request_id="same")
        with self.assertRaises(ValueError):
            logger.save_resolved("different meal", [resolved_food()], request_id="same")

    def test_default_summary_is_bound_to_saved_food_owner(self):
        _, alice = self.profile("alice")
        _, bob = self.profile("bob")
        MealService(user_id=bob.id).add_log(food_name="Bob meal", calories=900)
        result = MealLoggingService(user_id=alice.id).save_resolved("egg", [resolved_food()])
        self.assertEqual(result["daily_summary"]["consumed"]["calories"], 75)

    def test_missing_owner_cannot_read_or_mutate_another_users_records(self):
        logger, profile = self.logger()
        result = logger.save_resolved("egg", [resolved_food()])
        self.assertEqual(MealService().logs(), [])
        self.assertIsNone(NutritionService().get_profile())
        self.assertEqual(NutritionService().daily_totals(date.today())["calories"], 0)
        with self.assertRaises(ValueError):
            MealService().delete_log(result["meal"]["items"][0]["id"])
        with self.assertRaises(ValueError):
            MealService(user_id=profile.id).update_log(result["meal"]["items"][0]["id"], user_id=999)

    def test_database_rejects_invalid_owner_even_without_service_validation(self):
        with self.assertRaises(IntegrityError), get_session() as session:
            session.add(FoodLog(user_id=999, food_name="orphan", calories=10))

    def test_review_cannot_be_submitted_from_another_workspace(self):
        draft = new_draft(1, "egg", [resolved_food()])
        with self.assertRaises(ValueError):
            review_items(draft, [], 2)

    def test_nonfinite_nutrition_is_not_saved(self):
        logger, _ = self.logger()
        item = resolved_food()
        item["matched_food"]["calories"] = float("inf")
        with self.assertRaises(ValueError):
            logger.save_resolved("egg", [item])

    def test_invalid_profile_targets_rollback(self):
        nutrition, profile = self.profile()
        with self.assertRaises(ValueError):
            nutrition.save_profile(custom_calorie_goal=-1)
        self.assertIsNone(nutrition.get_profile().custom_calorie_goal)

    def test_existing_catalogue_does_not_claim_mixed_units_are_grams(self):
        with get_session() as session:
            food = session.get(Food, 1)
            self.assertIsNone(food.serving_unit)
            self.assertEqual(food.source_quality, "unverified_catalogue")
            self.assertEqual(len(food.source_version), 64)


class MemoryAndRetrievalTests(DatabaseTest):
    def test_allergy_object_is_retained_and_confirmation_required(self):
        _, profile = self.profile()
        memory = MemoryService(profile.id, "session")
        detected = memory.record_turn("I am allergic to peanuts.", "Review the saved restriction.")
        self.assertEqual(detected[0].content, "I am allergic to peanuts")
        self.assertFalse(detected[0].confirmed)
        for number in range(8):
            memory.add_memory("routine", f"Routine {number}")
        constraints = DietaryConstraints.from_context(memory.context())
        self.assertTrue(constraints.allergies)
        self.assertTrue(constraints.requires_confirmation)
        memory.confirm_memory(detected[0].id)
        self.assertFalse(DietaryConstraints.from_context(memory.context()).requires_confirmation)

    def test_diet_constraints_require_reviewed_catalogue_tags(self):
        constraints = DietaryConstraints.from_context({"memories": [{"category": "diet_preference", "content": "I prefer vegetarian food", "confirmed": True}]})
        self.assertFalse(constraints.permits(SimpleNamespace(name="Chicken", dietary_tags=None)))
        self.assertTrue(constraints.permits(SimpleNamespace(name="Lentils", dietary_tags='["vegetarian"]')))
        allergy = DietaryConstraints.from_context({}, "I am allergic to peanuts")
        self.assertFalse(allergy.permits(SimpleNamespace(name="Lentils", dietary_tags='["vegetarian"]')))

    def test_seed_never_calls_embedding_provider(self):
        with patch.object(KnowledgeBaseService, "_embed") as embed:
            KnowledgeBaseService().ensure_seeded()
        embed.assert_not_called()

    def test_embedding_failure_falls_back_to_lexical_retrieval(self):
        knowledge = KnowledgeBaseService()
        knowledge.ensure_seeded()
        with get_session() as session:
            chunk = session.scalar(select(KnowledgeChunk))
            chunk.embedding, chunk.embedding_model = "[1, 0]", "text-embedding-3-small"
        with patch("services.knowledge_base_service.OPENAI_API_KEY", "fake"), patch.object(knowledge, "_embed", return_value=[]):
            results = knowledge.retrieve("healthy diet")
        self.assertTrue(results)
        self.assertTrue(all(result["url"].startswith("https://") for result in results))

    def test_planner_does_not_return_a_failed_second_attempt(self):
        with get_session() as session:
            session.add(Food(id=1001, name="Test meal", normalized_name="test meal", serving_quantity=100,
                             serving_unit="g", calories=100, protein_g=10, carbs_g=10, fat_g=2))
        agent = Mock()
        agent.plan.return_value = MealPlanSchema(meal_name="Too much", foods=[{"food_id":1001,"quantity":1000,"unit":"g"}], reason="test")
        planner = MealPlanningService(agent=agent)
        with patch.object(planner, "retrieve_candidates", return_value=[{"id":1001}]):
            with self.assertRaises(MealPlanningAgentError):
                planner.recommend({"target_for_next_meal":{"calories":100,"protein_g":10,"carbs_g":10,"fat_g":2}})
        self.assertEqual(agent.plan.call_count, 2)
