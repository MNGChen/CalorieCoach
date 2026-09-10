from __future__ import annotations

from types import SimpleNamespace
import unittest

from services.nutrition_coach_agent import CoachAdviceSchema, NutritionCoachAgent, NutritionCoachAgentError
from services.nutrition_coach_service import NutritionCoachService


class _Daily:
    def __init__(self, summary: dict) -> None: self.value = summary
    def summary(self, _day): return self.value


class _Nutrition:
    def __init__(self, goal: str | None) -> None: self.profile = SimpleNamespace(goal=goal) if goal else None
    def get_profile(self): return self.profile


class _Meals:
    def __init__(self, meals=None) -> None: self.value = meals or []
    def logs(self, start, end): return self.value


class _Agent:
    def __init__(self) -> None: self.contexts = []
    def advise(self, context):
        self.contexts.append(context)
        return CoachAdviceSchema(summary="Progress reviewed.", priority="lean_protein", recommendation="Prioritize lean protein.",
                                 avoid_or_limit=["fried foods"], reasoning_summary="Uses the supplied remaining values.")


def summary(consumed: dict | None = None, remaining: dict | None = None) -> dict:
    target = {"calories": 2200.0, "protein_g": 150.0, "carbs_g": 230.0, "fat_g": 65.0}
    consumed = consumed or {"calories": 1600.0, "protein_g": 85.0, "carbs_g": 175.0, "fat_g": 58.0}
    remaining = remaining or {key: target[key] - consumed[key] for key in target}
    return {"date": "2026-09-11", "target": target, "consumed": consumed, "remaining": remaining}


class NutritionCoachServiceTests(unittest.TestCase):
    def _service(self, state: dict, goal: str | None = "Weight Loss", meals=None):
        agent = _Agent()
        return NutritionCoachService(_Daily(state), _Nutrition(goal), _Meals(meals), agent), agent

    def test_high_protein_deficit_context(self) -> None:
        service, agent = self._service(summary())
        response = service.get_nutrition_advice("What should I eat next?")
        self.assertTrue(response["available"])
        self.assertEqual(agent.contexts[0]["remaining"]["protein_g"], 65.0)
        self.assertEqual(agent.contexts[0]["progress"]["protein_g"], 0.567)

    def test_high_fat_intake_and_exceeded_macro_are_preserved(self) -> None:
        state = summary(remaining={"calories": 350.0, "protein_g": 30.0, "carbs_g": 40.0, "fat_g": -12.0})
        service, agent = self._service(state)
        response = service.get_nutrition_advice("What should I eat next?")
        self.assertEqual(agent.contexts[0]["remaining"]["fat_g"], -12.0)
        self.assertEqual(response["target_for_next_meal"]["fat_g"], 0)

    def test_calories_almost_consumed_and_all_targets_met(self) -> None:
        state = summary({"calories": 2150.0, "protein_g": 155.0, "carbs_g": 225.0, "fat_g": 63.0},
                        {"calories": 50.0, "protein_g": -5.0, "carbs_g": 5.0, "fat_g": 2.0})
        service, agent = self._service(state)
        service.get_nutrition_advice("How am I doing today?")
        self.assertEqual(agent.contexts[0]["progress"]["calories"], 0.977)
        self.assertEqual(agent.contexts[0]["remaining"]["protein_g"], -5.0)

    def test_muscle_gain_and_fat_loss_goals_are_supplied(self) -> None:
        muscle_service, muscle_agent = self._service(summary(), "Muscle Gain")
        fat_service, fat_agent = self._service(summary(), "Weight Loss")
        muscle_service.get_nutrition_advice("Do I need more protein?")
        fat_service.get_nutrition_advice("Do I need more protein?")
        self.assertEqual(muscle_agent.contexts[0]["user_goal"], "Muscle Gain")
        self.assertEqual(fat_agent.contexts[0]["user_goal"], "Weight Loss")

    def test_protein_specific_and_general_questions_are_preserved(self) -> None:
        service, agent = self._service(summary())
        service.get_nutrition_advice("Do I need more protein?")
        service.get_nutrition_advice("How am I doing today?")
        self.assertEqual([context["user_question"] for context in agent.contexts],
                         ["Do I need more protein?", "How am I doing today?"])

    def test_missing_target_returns_without_calling_agent(self) -> None:
        state = {"date": "2026-09-11", "target": None, "consumed": {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}, "remaining": None}
        service, agent = self._service(state, goal=None)
        response = service.get_nutrition_advice("What should I eat next?")
        self.assertFalse(response["available"])
        self.assertEqual(agent.contexts, [])

    def test_no_meals_logged_sends_empty_recent_meals(self) -> None:
        service, agent = self._service(summary({"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}), meals=[])
        service.get_nutrition_advice("How am I doing today?")
        self.assertEqual(agent.contexts[0]["recent_meals"], [])

    def test_invalid_llm_output_is_rejected(self) -> None:
        class InvalidChain:
            def invoke(self, _values): return {"summary": "missing required fields"}
        with self.assertRaises(NutritionCoachAgentError):
            NutritionCoachAgent(InvalidChain()).advise({"user_question": "test"})


if __name__ == "__main__": unittest.main()
