from __future__ import annotations

import unittest
from types import SimpleNamespace

from services.meal_planning_agent import MealPlanningAgentError
from services.meal_planning_service import MealPlanningService, RestaurantMenuUnavailable
from services.nutrition_orchestrator import NutritionOrchestrator


class _Session:
    def __init__(self, foods) -> None: self.foods = foods
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def scalars(self, _query): return self.foods


class MealPlanningServiceTests(unittest.TestCase):
    def _service(self, foods=()):
        return MealPlanningService(agent=object(), session_factory=lambda: _Session(foods))

    def test_detects_mcdonalds_aliases(self) -> None:
        service = self._service()
        self.assertEqual(service.restaurant_for_request("I want McDonald's"), "McDonald's")
        self.assertEqual(service.restaurant_for_request("我想吃麦当劳"), "McDonald's")
        self.assertIsNone(service.restaurant_for_request("Recommend lunch"))

    def test_detects_kfc_aliases(self) -> None:
        service = self._service()
        self.assertEqual(service.restaurant_for_request("I want KFC"), "KFC")
        self.assertEqual(service.restaurant_for_request("Recommend Kentucky Fried Chicken"), "KFC")
        self.assertEqual(service.restaurant_for_request("我想吃肯德基"), "KFC")

    def test_does_not_substitute_unrelated_local_food_for_restaurant_request(self) -> None:
        service = self._service()
        with self.assertRaises(RestaurantMenuUnavailable):
            service.recommend({"target_for_next_meal": {"calories": 500.0}, "priority": "protein"},
                              user_request="I want to eat McDonald's")

    def test_does_not_substitute_unrelated_local_food_for_kfc_request(self) -> None:
        service = self._service()
        with self.assertRaises(RestaurantMenuUnavailable):
            service.recommend({"target_for_next_meal": {"calories": 500.0}, "priority": "protein"},
                              user_request="I want KFC, any suggestion?")

    def test_fallback_labels_the_llm_meal_idea_as_unverified(self) -> None:
        advice = {"available": True, "recommendation": "Try tofu with steamed greens and brown rice.",
                  "recent_foods": [], "dietary_constraints": {}}

        class Router:
            def route(self, _message): return SimpleNamespace(intent="meal_recommendation", follow_up_request=None)
        class Coach:
            def get_nutrition_advice(self, *_args, **_kwargs): return advice
        class Planner:
            def recommend(self, *_args, **_kwargs): raise MealPlanningAgentError("No checked meal.")

        response = NutritionOrchestrator(router=Router(), coach=Coach(), planner=Planner()).handle("What for dinner?")

        self.assertEqual(response["message"], advice["recommendation"])
        self.assertIn("nutrition has not been verified", response["data"]["planning_warning"])


if __name__ == "__main__":
    unittest.main()
