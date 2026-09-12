"""OpenAI text client with validated, user-safe error handling."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from ai.prompts import FOOD_ANALYSIS_PROMPT, MEAL_PLAN_PROMPT, SYSTEM_PROMPT
from config import OPENAI_API_KEY, OPENAI_MODEL, REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class AIResult:
    data: dict[str, Any]
    used_ai: bool
    message: str = ""


class AIServiceError(RuntimeError):
    """A safe message suitable for display when the AI provider cannot respond."""


class NutritionAI:
    """Minimal OpenAI Responses client for legacy call sites."""

    def _generate(self, prompt: str, expect_json: bool = True) -> str:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        suffix = " Return valid JSON only." if expect_json else ""
        response = OpenAI(api_key=OPENAI_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS).responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT + suffix,
            input=prompt,
            store=False,
        )
        if not response.output_text:
            raise ValueError("OpenAI returned an empty response.")
        return response.output_text

    @staticmethod
    def _json(text: str) -> dict[str, Any]:
        data = json.loads(text.strip())
        if not isinstance(data, dict):
            raise ValueError("AI response was not a JSON object.")
        return data

    def analyze_food(self, food_description: str) -> AIResult:
        try:
            return AIResult(self._json(self._generate(FOOD_ANALYSIS_PROMPT.format(food_description=food_description))), True)
        except Exception as exc:
            logger.warning("Food analysis request failed (%s).", type(exc).__name__)
            raise AIServiceError("Food analysis is currently unavailable. Check your OpenAI API key and connection, then try again.") from exc

    def meal_plan(self, calories: int, preference: str) -> AIResult:
        try:
            return AIResult(self._json(self._generate(MEAL_PLAN_PROMPT.format(calories=calories, preference=preference))), True)
        except Exception as exc:
            logger.warning("Meal planning request failed (%s).", type(exc).__name__)
            raise AIServiceError("Meal planning is currently unavailable. Check your OpenAI API key and connection, then try again.") from exc

    def coach(self, user_message: str, context: str = "") -> str:
        try:
            return self._generate(f"User context: {context}\nUser message: {user_message}", expect_json=False)
        except Exception as exc:
            logger.warning("Coaching request failed (%s).", type(exc).__name__)
            raise AIServiceError("AI coaching is currently unavailable. Check your OpenAI API key and connection, then try again.") from exc
