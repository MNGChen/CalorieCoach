"""Gemini client with validated, user-safe error handling."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

from ai.prompts import FOOD_ANALYSIS_PROMPT, MEAL_PLAN_PROMPT, SYSTEM_PROMPT
from config import GEMINI_API_KEY, GEMINI_MODEL, REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class AIResult:
    data: dict[str, Any]
    used_ai: bool
    message: str = ""


class AIServiceError(RuntimeError):
    """A safe message suitable for display when the AI provider cannot respond."""


class NutritionAI:
    """Minimal Gemini REST client; no SDK lock-in and graceful failures."""

    def _generate(self, prompt: str, expect_json: bool = True) -> str:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        generation_config: dict[str, Any] = {"temperature": 0.25}
        if expect_json:
            generation_config["responseMimeType"] = "application/json"
        payload = {"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                   "contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": generation_config}
        response = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload,
                                 timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        try:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Gemini returned an unexpected response format.") from exc

    @staticmethod
    def _json(text: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("AI response was not a JSON object.")
        return data

    def analyze_food(self, food_description: str) -> AIResult:
        try:
            return AIResult(self._json(self._generate(FOOD_ANALYSIS_PROMPT.format(food_description=food_description))), True)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            logger.warning("Food analysis request failed (%s).", type(exc).__name__)
            raise AIServiceError("Food analysis is currently unavailable. Check your Gemini API key and connection, then try again.") from exc

    def meal_plan(self, calories: int, preference: str) -> AIResult:
        try:
            return AIResult(self._json(self._generate(MEAL_PLAN_PROMPT.format(calories=calories, preference=preference))), True)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            logger.warning("Meal planning request failed (%s).", type(exc).__name__)
            raise AIServiceError("Meal planning is currently unavailable. Check your Gemini API key and connection, then try again.") from exc

    def coach(self, user_message: str, context: str = "") -> str:
        try:
            return self._generate(f"User context: {context}\nUser message: {user_message}", expect_json=False)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            logger.warning("Coaching request failed (%s).", type(exc).__name__)
            raise AIServiceError("AI coaching is currently unavailable. Check your Gemini API key and connection, then try again.") from exc
