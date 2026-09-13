from __future__ import annotations

import unittest

from services.restaurant_menu_search_service import RestaurantMenuSearchService
from services.web_search import WebSearchResult


class _Search:
    def __init__(self, results): self.results = results; self.queries = []
    def search_web(self, query): self.queries.append(query); return self.results


class _Chain:
    def invoke(self, _values):
        return {"items": [{"name": "Loaded Salad Bowl", "source_url": "https://www.kfc.com.sg/menu/bowls",
                           "reason": "Named in the official menu snippet."}]}


class RestaurantMenuSearchTests(unittest.TestCase):
    def test_extracts_only_an_official_menu_option_and_never_nutrition(self) -> None:
        official = WebSearchResult("KFC Bowls", "Loaded Salad Bowl", "https://www.kfc.com.sg/menu/bowls", "www.kfc.com.sg")
        result = RestaurantMenuSearchService(_Search([official]), _Chain()).search_menu("KFC", "KFC dinner")
        self.assertTrue(result["available"])
        self.assertEqual(result["items"][0]["name"], "Loaded Salad Bowl")
        self.assertEqual(result["items"][0]["nutrition_status"], "official_menu_only")
        self.assertNotIn("calories", result["items"][0])

    def test_rejects_non_official_results(self) -> None:
        result = RestaurantMenuSearchService(
            _Search([WebSearchResult("Unofficial", "KFC item", "https://example.com/kfc", "example.com")]), _Chain()
        ).search_menu("KFC", "KFC dinner")
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "No official menu pages were found.")


if __name__ == "__main__":
    unittest.main()
