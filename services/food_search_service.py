"""Deterministic local lookup for foods in the SQLite catalogue."""
from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.food_seed import normalize_food_name
from database.models import Food


class FoodSearchService:
    MIN_FUZZY_SCORE = 0.62
    COOKING_STYLE_TERMS = {
        "steamed": {"steam", "steamed", "poached"},
        "roasted": {"roast", "roasted", "baked"},
        "fried": {"fried", "fry", "deepfried", "deep", "panfried"},
        "grilled": {"grilled", "grill", "chargrilled"},
    }
    QUERY_TOKEN_ALIASES = {"chick": "chicken", "veg": "vegetable", "veggie": "vegetable"}

    def search(self, session: Session, input_name: str) -> Food | None:
        foods = list(session.scalars(select(Food)))
        return self.search_foods(foods, input_name)

    def search_foods(self, foods: list[Food], input_name: str) -> Food | None:
        """Search an in-memory catalogue; kept public for focused, database-free tests."""
        normalized = self._normalize_query(input_name)
        if not normalized:
            return None
        exact = next((food for food in foods if food.normalized_name == normalized), None)
        if exact:
            return exact

        query_tokens = set(normalized.split())
        candidates = [food for food in self.candidate_foods(foods, input_name)
                      if query_tokens <= set(food.normalized_name.split())]
        if candidates:
            return min(candidates, key=lambda food: len(food.normalized_name))

        scored = [(self._score(normalized, food.normalized_name), food)
                  for food in self.candidate_foods(foods, input_name)]
        score, food = max(scored, default=(0.0, None), key=lambda pair: pair[0])
        return food if score >= self.MIN_FUZZY_SCORE else None

    def exact_match(self, foods: list[Food], input_name: str) -> Food | None:
        normalized = self._normalize_query(input_name)
        return next((food for food in foods if food.normalized_name == normalized), None)

    def candidate_foods(self, foods: list[Food], input_name: str, limit: int = 8) -> list[Food]:
        """Return plausible candidates; explicit cooking methods are hard constraints."""
        normalized = self._normalize_query(input_name)
        if not normalized:
            return []
        required_styles = self._cooking_styles(normalized)
        eligible = [food for food in foods if not required_styles or required_styles <= self._cooking_styles(food.normalized_name)]
        scored = [(self._score(normalized, food.normalized_name), food) for food in eligible]
        return [food for score, food in sorted(scored, key=lambda item: item[0], reverse=True)
                if score >= self.MIN_FUZZY_SCORE][:limit]

    @classmethod
    def _cooking_styles(cls, text: str) -> set[str]:
        tokens = set(text.split())
        return {style for style, terms in cls.COOKING_STYLE_TERMS.items() if tokens & terms}

    @classmethod
    def _normalize_query(cls, value: str) -> str:
        return " ".join(cls.QUERY_TOKEN_ALIASES.get(token, token) for token in normalize_food_name(value).split())

    @staticmethod
    def _score(query: str, candidate: str) -> float:
        sequence = SequenceMatcher(None, query, candidate).ratio()
        query_tokens, candidate_tokens = set(query.split()), set(candidate.split())
        overlap = len(query_tokens & candidate_tokens) / len(query_tokens | candidate_tokens)
        return 0.55 * sequence + 0.45 * overlap
