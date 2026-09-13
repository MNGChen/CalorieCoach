from __future__ import annotations

import unittest
from unittest.mock import patch
from contextlib import contextmanager

from services.food_analysis_service import FoodAnalysisService
from services.food_input_parser import FoodInput, FoodInputParser
from services.food_match_agent import FoodMatchAgent, FoodMatchAgentError, FoodMatchSchema
from services.food_search_service import FoodSearchService
from services.nutrition_normalizer import NutritionNormalizer
from services.nutrition_statistics import NutritionStatisticsService
from services.nutrition_validation_agent import NutritionValidationAgent, NutritionValidationAgentError
from services.nutrition_validation_models import NutritionSource, ValidationDecision
from services.nutrition_validation_service import NutritionValidationService
from services.portion_calculator import PortionCalculator
from services.nutrition_mcp_tools import NutritionCatalogTools
from services.web_nutrition_extractor import WebNutritionExtractionError, WebNutritionExtractor
from services.web_search import WebSearchError, WebSearchResult


class Food:
    def __init__(self, id: int, name: str, normalized_name: str, calories: float = 165, protein_g: float = 31,
                 carbs_g: float = 0, fat_g: float = 3.6, serving_quantity: float = 100, serving_unit: str = "g"):
        self.id, self.name, self.normalized_name = id, name, normalized_name
        self.calories, self.protein_g, self.carbs_g, self.fat_g = calories, protein_g, carbs_g, fat_g
        self.serving_quantity, self.serving_unit = serving_quantity, serving_unit


def nutrition_source(calories: float | None, protein: float | None, carbs: float | None, fat: float | None,
                     serving_size: str = "1 bowl", quantity: float | None = 1, unit: str | None = "bowl",
                     suffix: str = "a") -> NutritionSource:
    result = WebSearchResult(f"Source {suffix}", "Nutrition facts", f"https://source-{suffix}.test/facts", f"source-{suffix}.test")
    return NutritionSource(result, serving_size, quantity, unit, calories, protein, carbs, fat)


class FoodParserTests(unittest.TestCase):
    def test_multiple_foods_in_message(self) -> None:
        class StubChain:
            def invoke(self, values: dict) -> dict:
                self.message = values["food_description"]
                return {"items": [{"name": "chicken breast", "quantity": 200, "unit": "g"},
                                  {"name": "egg", "quantity": 1, "unit": "piece"}]}

        chain = StubChain()
        self.assertEqual(FoodInputParser(chain).parse("I ate 200g chicken breast and one egg"),
                         [FoodInput("chicken breast", 200.0, "g"), FoodInput("egg", 1.0, "piece")])
        self.assertEqual(chain.message, "I ate 200g chicken breast and one egg")

    def test_missing_quantity(self) -> None:
        self.assertEqual(FoodInputParser.validate({"items": [{"name": "egg", "quantity": None, "unit": None}]}),
                         [FoodInput("egg", None, None)])


class FoodSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FoodSearchService()
        self.foods = [Food(1, "Hainanese chicken rice", "hainanese chicken rice"), Food(2, "Chicken breast", "chicken breast")]

    def test_exact_case_and_partial_matches(self) -> None:
        self.assertEqual(self.service.search_foods(self.foods, "chicken breast").name, "Chicken breast")
        self.assertEqual(self.service.search_foods(self.foods, "CHICKEN RICE").name, "Hainanese chicken rice")
        self.assertEqual(self.service.search_foods(self.foods, "chicken rice").name, "Hainanese chicken rice")

    def test_food_not_found(self) -> None:
        self.assertIsNone(self.service.search_foods(self.foods, "unknown food"))

    def test_explicit_cooking_method_rejects_conflicting_candidate(self) -> None:
        foods = [Food(1, "Roasted chicken rice", "roasted chicken rice")]
        self.assertEqual(self.service.candidate_foods(foods, "steamed chicken rice"), [])
        self.assertIsNone(self.service.search_foods(foods, "steamed chicken rice"))


class FoodMatchAgentTests(unittest.TestCase):
    def test_rejects_a_food_id_outside_the_retrieved_candidates(self) -> None:
        class InvalidChain:
            def invoke(self, _values): return {"food_id": 99, "confidence": "high", "reason": "Looks right."}
        with self.assertRaises(FoodMatchAgentError):
            FoodMatchAgent(InvalidChain()).choose("chicken rice", [{"id": 1, "name": "Chicken rice"}])


class NutritionMcpToolTests(unittest.TestCase):
    def test_food_summary_contains_only_catalogue_fields(self) -> None:
        food = Food(1, "Chicken breast", "chicken breast")
        result = NutritionCatalogTools._food_summary(food)
        self.assertEqual(result["name"], "Chicken breast")
        self.assertEqual(result["typical_serving"], "100 g")
        self.assertNotIn("user_id", result)

    def test_lookup_food_nutrition_returns_no_match_without_a_food_id(self) -> None:
        class NoMatchSearch:
            def search(self, _session, _query): return None
        tools = NutritionCatalogTools(search=NoMatchSearch())
        # The empty local session is not used because the search stub returns immediately.
        with patch("services.nutrition_mcp_tools.init_db"), patch("services.nutrition_mcp_tools.get_session"):
            self.assertEqual(tools.lookup_food_nutrition("unknown food")["found"], False)


class NutritionStatisticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.normalizer, self.statistics = NutritionNormalizer(), NutritionStatisticsService()

    def _summarize(self, sources: list[NutritionSource]):
        return self.statistics.summarize([self.normalizer.normalize(source) for source in sources])

    def test_three_closely_matching_sources_are_high_confidence(self) -> None:
        stats = self._summarize([nutrition_source(620, 24, 68, 28, suffix="a"), nutrition_source(640, 25, 69, 29, suffix="b"), nutrition_source(650, 26, 70, 30, suffix="c")])
        self.assertEqual((stats.deterministic_status, stats.deterministic_confidence, stats.median_calories), ("accepted", "high", 640.0))

    def test_clear_outlier_is_excluded(self) -> None:
        stats = self._summarize([nutrition_source(580, 20, 55, 31, suffix="a"), nutrition_source(600, 20, 60, 31, suffix="b"), nutrition_source(590, 20, 58, 31, suffix="c"), nutrition_source(1200, 40, 120, 62, suffix="d")])
        self.assertEqual(len(stats.outlier_sources), 1)
        self.assertEqual(stats.median_calories, 590.0)

    def test_strong_disagreement_remains_uncertain(self) -> None:
        stats = self._summarize([nutrition_source(350, 20, 50, 7.8, suffix="a"), nutrition_source(750, 30, 100, 25.6, suffix="b"), nutrition_source(1100, 40, 140, 42.2, suffix="c")])
        self.assertEqual((stats.deterministic_status, stats.deterministic_confidence), ("uncertain", "low"))

    def test_different_serving_sizes_are_not_compared(self) -> None:
        stats = self._summarize([nutrition_source(220, 10, 20, 11.1, "100 g", 100, "g", "a"), nutrition_source(650, 25, 70, 30, "1 bowl", 1, "bowl", "b")])
        self.assertEqual(len(stats.comparable_sources), 1)
        self.assertEqual(stats.deterministic_status, "uncertain")

    def test_missing_macros_are_preserved_but_incomplete(self) -> None:
        stats = self._summarize([nutrition_source(600, 25, None, None)])
        self.assertEqual(stats.deterministic_status, "uncertain")
        self.assertIsNone(stats.median_carbs_g)

    def test_negative_and_macro_inconsistent_sources_are_rejected(self) -> None:
        negative = self.normalizer.normalize(nutrition_source(-1, 1, 1, 1))
        impossible = self.normalizer.normalize(nutrition_source(1000, 10, 10, 10))
        self.assertFalse(self.statistics.check_source(negative).valid)
        self.assertFalse(self.statistics.check_source(impossible).valid)

    def test_one_source_and_no_valid_sources(self) -> None:
        one = self._summarize([nutrition_source(600, 25, 70, 24.4)])
        none = self._summarize([nutrition_source(None, 25, 70, 24.4)])
        self.assertEqual((one.deterministic_status, one.deterministic_confidence), ("uncertain", "medium"))
        self.assertEqual(none.deterministic_status, "rejected")

    def test_duplicate_urls_do_not_create_independent_evidence(self) -> None:
        source = nutrition_source(600, 25, 70, 24.4)
        stats = self._summarize([source, source, source])
        self.assertEqual(len(stats.comparable_sources), 1)
        self.assertEqual(stats.deterministic_status, "uncertain")

    def test_multiple_pages_on_one_website_cannot_claim_high_confidence(self) -> None:
        from dataclasses import replace
        sources = [nutrition_source(600, 25, 70, 24.4, suffix=suffix) for suffix in ("a", "b", "c")]
        sources = [replace(source, source=replace(source.source, url=f"https://same.test/{index}"))
                   for index, source in enumerate(sources)]
        self.assertEqual(self._summarize(sources).deterministic_status, "uncertain")


class _StubParser:
    def __init__(self, items: list[FoodInput]) -> None: self.items = items
    def parse(self, _message: str) -> list[FoodInput]: return self.items


class _StubSearch:
    def __init__(self, matches: dict[str, Food]) -> None: self.matches = matches
    def search(self, _session: object, food_name: str) -> Food | None: return self.matches.get(food_name)


class _StubWebSearch:
    def __init__(self, results: list[WebSearchResult] | None = None, fail: bool = False) -> None:
        self.results, self.fail, self.calls = results or [], fail, []
    def search_food_web(self, food_name: str) -> list[WebSearchResult]:
        self.calls.append(food_name)
        if self.fail: raise WebSearchError("provider unavailable")
        return self.results


class _StubExtractor:
    def __init__(self, sources: list[NutritionSource] | None = None) -> None: self.sources, self.calls = sources, []
    def extract(self, food_name: str, results: list[WebSearchResult]) -> list[NutritionSource]:
        self.calls.append((food_name, results))
        if self.sources is None: raise WebNutritionExtractionError("invalid nutrition")
        return self.sources


class _StubAgent:
    def __init__(self, decision: ValidationDecision) -> None: self.decision, self.calls = decision, []
    def validate(self, evidence: dict) -> ValidationDecision:
        self.calls.append(evidence)
        return self.decision


@contextmanager
def _test_session(): yield object()


class FoodAnalysisValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = nutrition_source(250, 10, 30, 8, "100 g", 100, "g")
        self.web_result = self.source.source
        self.validator = NutritionValidationService(agent=_StubAgent(ValidationDecision("accepted", "high", 0.9, "Sources agree.")))

    def _service(self, items: list[FoodInput], matches: dict[str, Food], web: _StubWebSearch, extractor: _StubExtractor) -> FoodAnalysisService:
        return FoodAnalysisService(_StubParser(items), _StubSearch(matches), PortionCalculator(), web, extractor,
                                   validator=self.validator, session_factory=_test_session)

    def test_local_database_result_bypasses_web_validation(self) -> None:
        web = _StubWebSearch([self.web_result])
        result = self._service([FoodInput("chicken breast", 200, "g")], {"chicken breast": Food(1, "Chicken breast", "chicken breast")}, web, _StubExtractor([self.source])).analyze("ignored")
        self.assertEqual(web.calls, [])
        self.assertEqual((result[0]["source_type"], result[0]["validation_status"]), ("local_database", "accepted"))

    def test_web_validation_and_portion_scaling(self) -> None:
        result = self._service([FoodInput("ramen", 200, "g")], {}, _StubWebSearch([self.web_result]), _StubExtractor([self.source])).analyze("ignored")
        self.assertTrue(result[0]["resolved"])
        self.assertEqual(result[0]["matched_food"]["calories"], 500)
        self.assertEqual(result[0]["validation_status"], "uncertain")

    def test_three_web_sources_can_be_accepted(self) -> None:
        sources = [self.source, nutrition_source(260, 10, 33, 10, "100 g", 100, "g", "b"),
                   nutrition_source(245, 9, 30, 10, "100 g", 100, "g", "c")]
        result = self._service([FoodInput("ramen", 100, "g")], {}, _StubWebSearch([source.source for source in sources]),
                               _StubExtractor(sources)).analyze("ignored")
        self.assertEqual((result[0]["validation_status"], result[0]["confidence"]), ("accepted", "high"))

    def test_invalid_llm_extraction_schema_is_rejected(self) -> None:
        class InvalidChain:
            def invoke(self, _values: dict) -> dict: return {"food_name": "ramen", "sources": [{"calories": 650}]}
        with self.assertRaises(WebNutritionExtractionError):
            WebNutritionExtractor(InvalidChain()).extract("ramen", [self.web_result])

    def test_web_search_failure_is_unresolved(self) -> None:
        result = self._service([FoodInput("ramen", None, None)], {}, _StubWebSearch(fail=True), _StubExtractor([self.source])).analyze("ignored")
        self.assertFalse(result[0]["resolved"])

    def test_local_match_uses_only_a_high_confidence_candidate_id(self) -> None:
        class CandidateSession:
            def __init__(self, foods): self.foods = foods
            def scalars(self, _query): return self.foods
        class Matcher:
            def choose(self, _query, candidates):
                return FoodMatchSchema(food_id=candidates[0]["id"], confidence="high", reason="Exact dish candidate.")
        food = Food(7, "Steamed chicken rice", "steamed chicken rice")
        service = FoodAnalysisService(matcher=Matcher())
        matched, candidates = service._local_match(CandidateSession([food]), FoodInput("steam chicken rice", None, None))
        self.assertEqual(matched.id, 7)
        self.assertEqual(candidates, [])

    def test_ambiguous_local_match_returns_candidates_for_user_confirmation(self) -> None:
        class CandidateSession:
            def __init__(self, foods): self.foods = foods
            def scalars(self, _query): return self.foods
        class Matcher:
            def choose(self, _query, _candidates):
                return FoodMatchSchema(food_id=None, confidence="low", reason="Ambiguous dish.")
        food = Food(7, "Steamed chicken rice", "steamed chicken rice")
        service = FoodAnalysisService(matcher=Matcher())
        matched, candidates = service._local_match(CandidateSession([food]), FoodInput("steam chicken rice", None, None))
        self.assertIsNone(matched)
        self.assertEqual(candidates[0]["name"], "Steamed chicken rice")


class ValidationAgentSchemaTests(unittest.TestCase):
    def test_invalid_validation_agent_output_is_rejected(self) -> None:
        class InvalidChain:
            def invoke(self, _values: dict) -> dict: return {"status": "accepted"}
        with self.assertRaises(NutritionValidationAgentError):
            NutritionValidationAgent(InvalidChain()).validate({"food_name": "ramen"})


if __name__ == "__main__": unittest.main()
