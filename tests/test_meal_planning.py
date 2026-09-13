from __future__ import annotations

import unittest

from services.meal_planning_agent import MealPlanningAgentError
from services.meal_planning_service import MealPlanningService, RestaurantMenuUnavailable


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


if __name__ == "__main__":
    unittest.main()
