"""Deterministic local lookup for foods in the SQLite catalogue."""
from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.food_seed import normalize_food_name
from database.models import Food


class FoodSearchService:
    MIN_FUZZY_SCORE = 0.62

    def search(self, session: Session, input_name: str) -> Food | None:
        foods = list(session.scalars(select(Food)))
        return self.search_foods(foods, input_name)

    def search_foods(self, foods: list[Food], input_name: str) -> Food | None:
        """Search an in-memory catalogue; kept public for focused, database-free tests."""
        normalized = normalize_food_name(input_name)
        if not normalized:
            return None
        exact = next((food for food in foods if food.normalized_name == normalized), None)
        if exact:
            return exact

        query_tokens = set(normalized.split())
        candidates = [food for food in foods if query_tokens <= set(food.normalized_name.split())]
        if candidates:
            return min(candidates, key=lambda food: len(food.normalized_name))

        scored = [(self._score(normalized, food.normalized_name), food) for food in foods]
        score, food = max(scored, default=(0.0, None), key=lambda pair: pair[0])
        return food if score >= self.MIN_FUZZY_SCORE else None

    @staticmethod
    def _score(query: str, candidate: str) -> float:
        sequence = SequenceMatcher(None, query, candidate).ratio()
        query_tokens, candidate_tokens = set(query.split()), set(candidate.split())
        overlap = len(query_tokens & candidate_tokens) / len(query_tokens | candidate_tokens)
        return 0.55 * sequence + 0.45 * overlap
