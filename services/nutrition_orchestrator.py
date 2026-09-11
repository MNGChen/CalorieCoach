"""LangGraph V1 orchestrator; nodes use narrow agents and deterministic services."""
from __future__ import annotations
from datetime import date
import logging
from collections.abc import Callable
from typing import Any, TypedDict
from langgraph.graph import START, END, StateGraph
from services.daily_nutrition_service import DailyNutritionService
from services.food_analysis_service import FoodAnalysisService
from services.meal_logging_service import MealLoggingService
from services.meal_planning_service import MealPlanningService
from services.nutrition_coach_service import NutritionCoachService
from services.nutrition_router import NutritionRouter, RouterError

logger=logging.getLogger(__name__)
class NutritionAgentState(TypedDict, total=False):
    message:str; intent:str; trace:list[str]; response:dict[str,Any]; resolved_foods:list[dict[str,Any]]; errors:list[str]
class NutritionOrchestrator:
    def __init__(self, router=None, food_analysis=None, meal_logging=None, daily=None, coach=None, planner=None,
                 on_status: Callable[[str], None] | None = None):
        self.router=router or NutritionRouter(); self.food=food_analysis or FoodAnalysisService(); self.logging=meal_logging or MealLoggingService(); self.daily=daily or DailyNutritionService(); self.coach=coach or NutritionCoachService(daily_nutrition=self.daily); self.planner=planner or MealPlanningService(); self.graph=self._build()
        self.on_status = on_status
    def _build(self):
        graph=StateGraph(NutritionAgentState); graph.add_node("router",self._router); graph.add_node("log_food",self._log); graph.add_node("daily_progress",self._progress); graph.add_node("nutrition_question",self._coach); graph.add_node("meal_recommendation",self._recommend); graph.add_node("general_nutrition_chat",self._general); graph.add_edge(START,"router"); graph.add_conditional_edges("router",lambda s:s["intent"],{x:x for x in ("log_food","daily_progress","nutrition_question","meal_recommendation","general_nutrition_chat")}); [graph.add_edge(node,END) for node in ("log_food","daily_progress","nutrition_question","meal_recommendation","general_nutrition_chat")]; return graph.compile()
    def handle(self,message:str)->dict[str,Any]:
        state=self.graph.invoke({"message":message,"trace":[],"errors":[]}); return state["response"]
    def _router(self,s):
        self._notify("Understanding your request…")
        try:
            result=self.router.route(s["message"])
            self._notify({"log_food":"Preparing to log your food…", "daily_progress":"Checking today's nutrition totals…",
                          "nutrition_question":"Reviewing your targets and today's food log…",
                          "meal_recommendation":"Reviewing your remaining nutrition budget…"}.get(result.intent, "Preparing a helpful response…"))
            return {"intent":result.intent,"trace":s["trace"]+["router"]}
        except RouterError: return {"intent":"general_nutrition_chat","trace":s["trace"]+["router_error"]}
    def _log(self,s):
        try:
            self._notify("Finding nutrition information for the foods you mentioned…")
            foods=self.food.analyze(s["message"])
            self._notify("Saving the foods and updating today's totals…")
            saved=self.logging.save_resolved(s["message"],foods)
            self._notify("Today's nutrition totals are updated.")
            return {"response":{"intent":"log_food","message":f"Logged {len(saved['meal']['items'])} food item(s).","data":saved,"trace":s["trace"]+["food_analysis","meal_logging","daily_tracking"]}}
        except Exception as exc: return self._error("log_food","I couldn't log reliable nutrition information for that food.",s,exc)
    def _progress(self,s):
        self._notify("Calculating today's consumed and remaining nutrition…")
        summary=self.daily.summary(date.today()); return {"response":{"intent":"daily_progress","message":"Here is your nutrition progress for today.","data":{"daily_summary":summary},"trace":s["trace"]+["daily_tracking"]}}
    def _coach(self,s):
        self._notify("Getting personalised coaching from your current nutrition data…")
        advice=self.coach.get_nutrition_advice(s["message"]); return {"response":{"intent":"nutrition_question","message":advice.get("summary",advice.get("reason","Your daily summary is available.")),"data":advice,"trace":s["trace"]+["daily_tracking","coach_agent"]}}
    def _recommend(self,s):
        self._notify("Getting guidance from your current nutrition data…")
        advice=self.coach.get_nutrition_advice(s["message"])
        if not advice.get("available"): return {"response":{"intent":"meal_recommendation","message":advice["reason"],"data":advice,"trace":s["trace"]+["daily_tracking"]}}
        try:
            self._notify("Choosing foods that fit your remaining budget…")
            plan=self.planner.recommend(advice); return {"response":{"intent":"meal_recommendation","message":f"Suggested: {plan['meal_name']}","data":{"coach":advice,"meal_plan":plan},"trace":s["trace"]+["daily_tracking","coach_agent","meal_planning_agent","portion_calculator"]}}
        except Exception: return {"response":{"intent":"meal_recommendation","message":advice["recommendation"],"data":{"coach":advice},"trace":s["trace"]+["daily_tracking","coach_agent","meal_planner_fallback"]}}
    def _general(self,s): return {"response":{"intent":"general_nutrition_chat","message":"I can help log food, review today’s nutrition, or suggest a meal based on your remaining targets.","data":{},"trace":s["trace"]+["general_response"]}}
    @staticmethod
    def _error(intent,message,s,exc): logger.warning("Workflow node failed: %s",type(exc).__name__); return {"response":{"intent":intent,"message":message,"data":{},"trace":s["trace"]+["error"]}}
    def _notify(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)
