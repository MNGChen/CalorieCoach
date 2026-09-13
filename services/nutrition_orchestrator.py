"""Workflow: chat prepares food drafts; only the review form saves them."""
from __future__ import annotations

from datetime import date
import logging
from collections.abc import Callable
from typing import Any, TypedDict
from langgraph.graph import START, END, StateGraph
from services.daily_nutrition_service import DailyNutritionService
from services.food_analysis_service import FoodAnalysisService
from services.meal_planning_service import MealPlanningService, RestaurantMenuUnavailable
from services.nutrition_coach_service import NutritionCoachService
from services.nutrition_router import NutritionRouter, RouterError
from services.memory_service import MemoryService
from services.restaurant_menu_search_service import RestaurantMenuSearchService

logger = logging.getLogger(__name__)


class NutritionAgentState(TypedDict, total=False):
    message: str
    intent: str
    trace: list[str]
    response: dict[str, Any]
    memory_context: dict[str, Any]
    follow_up_request: str | None


class NutritionOrchestrator:
    def __init__(self, router=None, food_analysis=None, meal_logging=None, daily=None, coach=None,
                 planner=None, restaurant_search=None, memory: MemoryService | None = None,
                 on_status: Callable[[str], None] | None = None):
        self.router = router or NutritionRouter()
        self.food = food_analysis or FoodAnalysisService()
        self.daily = daily or DailyNutritionService()
        self.coach = coach or NutritionCoachService(daily_nutrition=self.daily)
        self.planner = planner or MealPlanningService()
        self.restaurant_search = restaurant_search or RestaurantMenuSearchService()
        self.memory, self.on_status = memory, on_status
        self.graph = self._build()

    def _build(self):
        graph = StateGraph(NutritionAgentState)
        graph.add_node("router", self._router)
        handlers = {"log_food": self._log, "daily_progress": self._progress, "nutrition_question": self._coach,
                    "meal_recommendation": self._recommend, "general_nutrition_chat": self._general}
        for name, handler in handlers.items():
            graph.add_node(name, handler)
            graph.add_edge(name, END)
        graph.add_edge(START, "router")
        graph.add_conditional_edges("router", lambda state: state["intent"], {name: name for name in handlers})
        return graph.compile()

    def handle(self, message: str) -> dict[str, Any]:
        if not message.strip():
            raise ValueError("Enter a message first.")
        memory_context = self.memory.context() if self.memory else {}
        response = self.graph.invoke({"message": message, "trace": [], "memory_context": memory_context})["response"]
        if self.memory:
            try:
                saved = self.memory.record_turn(message, response["message"])
                response["data"]["saved_memories"] = [{"category": item.category, "content": item.content} for item in saved]
            except Exception:
                logger.warning("Assistant memory could not be saved.", exc_info=True)
        return response

    def _router(self, state):
        self._notify("Understanding your request…")
        try:
            result = self.router.route(state["message"])
            return {"intent": result.intent, "follow_up_request": getattr(result, "follow_up_request", None),
                    "trace": state["trace"] + ["router"]}
        except RouterError:
            return {"intent": "general_nutrition_chat", "trace": state["trace"] + ["router_error"]}

    def _log(self, state):
        try:
            self._notify("Finding nutrition information for review…")
            foods = self.food.analyze(state["message"])
            return self._response(state, "Review the food estimates below before saving. Nothing has been logged yet.",
                                  {"pending_foods": foods, "original_input": state["message"],
                                   "follow_up_request": state.get("follow_up_request")}, ["food_analysis", "awaiting_confirmation"])
        except Exception:
            logger.warning("Food preparation failed.", exc_info=True)
            return self._response(state, "Food lookup is unavailable. You can add food manually.", {}, ["error"])

    def _progress(self, state):
        return self._response(state, "Here is your nutrition progress for today.",
                              {"daily_summary": self.daily.summary(date.today())}, ["daily_tracking"])

    def _coach(self, state):
        advice = self.coach.get_nutrition_advice(state["message"], memory_context=state.get("memory_context"))
        return self._response(state, advice.get("summary", advice.get("reason", "Your daily summary is available.")),
                              advice, ["daily_tracking", "coach_agent"])

    def _recommend(self, state):
        self._notify("Reviewing your remaining nutrition and dietary constraints…")
        advice = self.coach.get_nutrition_advice(state["message"], memory_context=state.get("memory_context"))
        if not advice.get("available"):
            return self._response(state, advice["reason"], advice, ["daily_tracking"])
        try:
            plan = self.planner.recommend(advice, recent_foods=advice.get("recent_foods", []), user_request=state["message"])
            return self._response(state, f"Suggested: {plan['meal_name']}", {"coach": advice, "meal_plan": plan},
                                  ["coach_agent", "meal_planning_agent", "portion_calculator"])
        except RestaurantMenuUnavailable as exc:
            menu = self.restaurant_search.search_menu(exc.restaurant, state["message"])
            return self._response(state, "Official menu information only; nutrition and dietary suitability require verification.",
                                  {"coach": advice, "restaurant_menu": menu, "llm_fallback": not menu["available"]},
                                  ["official_restaurant_menu_search"])
        except Exception as exc:
            logger.warning("Meal planning did not produce a verified plan (%s).", type(exc).__name__)
            return self._response(state, advice["recommendation"], {"coach": advice,
                                  "planning_warning": "No meal meeting the portion, budget and dietary checks was found. General guidance is shown."},
                                  ["meal_planner_fallback"])

    def _general(self, state):
        return self._response(state, "I can help review today's progress. For AI food lookup and coaching, configure an API key. You can always log food manually.", {}, ["general_response"])

    @staticmethod
    def _response(state, message, data, trace):
        return {"response": {"intent": state["intent"], "message": message, "data": data, "trace": state["trace"] + trace}}

    def _notify(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)
