"""Deterministic constraints shared by coaching and meal selection."""
import re
import json
from pydantic import BaseModel, Field


class DietaryConstraints(BaseModel):
    diets: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    allergies: bool = False
    requires_confirmation: bool = False
    unknown_restriction: bool = False
    statements: list[str] = Field(default_factory=list)

    @classmethod
    def from_context(cls, memory: dict, request: str = ""):
        entries = [item for item in memory.get("memories", []) if item["category"] in {"restriction", "diet_preference"}]
        combined = " ".join([item["content"] for item in entries] + [request]).casefold()
        patterns = {"vegan": r"\bvegan\b|纯素", "vegetarian": r"\bvegetarian\b|素食",
                    "dairy_free": r"dairy[- ]free|no dairy|不吃奶|乳糖不耐", "gluten_free": r"gluten[- ]free|无麸质"}
        diets = [name for name, pattern in patterns.items() if re.search(pattern, combined)]
        avoid = re.findall(r"(?:\bavoid\b|\bno\b|do not recommend|allergic to|不吃|不要推荐|对)\s*([^.,;!?，。；！？]{1,80})", combined)
        allergies = bool(re.search(r"allerg|intoleran|过敏|不耐", combined))
        unknown = any(item["category"] == "restriction" and not re.search(
            "|".join(patterns.values()) + r"|avoid|\bno\b|do not recommend|allerg|intoleran|过敏|不耐|不吃|不要推荐", item["content"], re.I)
            for item in entries)
        return cls(diets=diets, avoid=avoid, allergies=allergies, unknown_restriction=unknown,
                   requires_confirmation=any(item.get("confirmed") is False for item in entries),
                   statements=[item["content"] for item in entries] + ([request] if diets or avoid or allergies else []))

    def permits(self, food) -> bool:
        if self.requires_confirmation or self.unknown_restriction:
            return False
        if any(term and term in food.name.casefold() for term in self.avoid):
            return False
        # Names cannot prove absence of allergens or ingredients. The current
        # catalogue lacks reviewed ingredient lists, so these requests need review.
        if self.allergies or self.avoid:
            return False
        try:
            tags = json.loads(getattr(food, "dietary_tags", None) or "[]")
        except (ValueError, TypeError):
            tags = []
        return all(diet in tags for diet in self.diets)
