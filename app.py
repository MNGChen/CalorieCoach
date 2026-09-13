"""CalorieCoach entry point: dashboard, profile, and daily food log."""
from __future__ import annotations

from datetime import date
import re
from uuid import uuid4

import streamlit as st

from ai.nutrition_ai import AIServiceError
from database.database import init_db
from services.meal_service import MealService
from services.nutrition_service import NutritionService
from services.food_analysis_service import FoodAnalysisService
from services.meal_logging_service import MealLoggingService
from services.daily_nutrition_service import DailyNutritionService
from services.demo_data_service import DemoDataError, DemoDataService
from services.nutrition_coach_service import NutritionCoachService
from services.memory_service import MemoryService
from services.knowledge_base_service import KnowledgeBaseService
from utils.helpers import render_metric_cards
from utils.ui import apply_app_shell, empty_state, page_header, section_header
from utils.session_state import ensure_workspace, switch_workspace
from utils.food_review_ui import render_food_review
from utils.profile_ui import render_profile
from utils.assistant_ui import render_assistant
from services.food_review_service import new_draft

st.set_page_config(page_title="CalorieCoach", page_icon="🥗", layout="wide")
apply_app_shell()
init_db()
ensure_workspace(st.session_state)

with st.sidebar:
    st.markdown("## 🥗 CalorieCoach")
    st.caption("Your daily nutrition workspace")
    st.divider()
    active_username = st.session_state.get("active_username")
    if active_username:
        st.success(f"Active user: {active_username}")
        if st.button("Switch user", use_container_width=True):
            switch_workspace(st.session_state, None)
            st.rerun()
    else:
        username = st.text_input("Username", placeholder="e.g. ming")
        if st.button("Open my workspace", type="primary", use_container_width=True):
            candidate = username.strip().casefold()
            if not re.fullmatch(r"[a-z0-9_.-]{3,40}", candidate):
                st.error("Username must be 3–40 characters and may use letters, numbers, dots, underscores, or hyphens.")
            else:
                st.session_state["active_username"] = candidate
                st.rerun()
        if st.button("Load demo data", type="primary", use_container_width=True, help="Create 14 days of sample meal and weight history for this new username."):
            candidate = username.strip().casefold()
            if not re.fullmatch(r"[a-z0-9_.-]{3,40}", candidate):
                st.error("Enter a valid username before loading demo data.")
            else:
                demo_nutrition = NutritionService(username=candidate)
                try:
                    DemoDataService(demo_nutrition, MealService(user_id=-1)).load()
                    st.session_state["active_username"] = candidate
                    st.rerun()
                except DemoDataError as exc:
                    st.error(str(exc))
    st.divider()
    st.markdown("**How to use it**")
    st.caption("Complete your profile first, then log food. You can review and adjust every AI estimate before saving.")
    st.divider()
    st.caption("Nutrition values are estimates and do not replace medical advice.")

page_header("Make today's nutrition easier to understand", "Log each meal, review your progress, and make steady adjustments toward your goal.", "DAILY NUTRITION")

active_username = st.session_state.get("active_username")
if not active_username:
    empty_state("👤 Enter a username in the sidebar to open or create your personal nutrition workspace.")
    st.stop()

nutrition = NutritionService(username=active_username)
profile = nutrition.get_profile()
owner_id = profile.id if profile else -1
meals = MealService(user_id=owner_id)
daily_nutrition = DailyNutritionService(nutrition)
meal_logging = MealLoggingService(daily_nutrition=daily_nutrition, user_id=owner_id)
knowledge_base = KnowledgeBaseService()
knowledge_base.ensure_seeded()
coach = NutritionCoachService(daily_nutrition=daily_nutrition, nutrition=nutrition, meals=meals,
                              knowledge_base=knowledge_base)
memory_session_key = f"assistant_memory_session_{active_username}"
if memory_session_key not in st.session_state:
    st.session_state[memory_session_key] = str(uuid4())
assistant_memory = MemoryService(user_id=owner_id, session_id=st.session_state[memory_session_key])
if not profile:
    empty_state(f"👋 Welcome, {active_username}. Complete your profile below to create your personal nutrition workspace.")
else:
    if saved_message := st.session_state.pop("food_log_saved_message", None):
        st.success(saved_message)
    summary = daily_nutrition.summary(date.today())
    targets = nutrition.targets(profile)
    totals = summary["consumed"]
    render_metric_cards(
        totals["calories"], targets.calorie_goal, totals["protein_g"], totals["carbs_g"], totals["fat_g"],
        targets.protein_goal_g, targets.carbs_goal_g, targets.fat_goal_g,
    )
    st.caption(f"BMI {targets.bmi} · BMR {targets.bmr} kcal · TDEE {targets.tdee} kcal · Goal: {profile.goal}")
    today_logs = meals.logs(start=date.today(), end=date.today())
    section_header("Today's log", "See what you have eaten today and edit any entry below when needed.")
    if today_logs:
        st.dataframe(
            [{"Meal": item.meal_type, "Food": item.food_name, "Quantity": f"{item.quantity:g} {item.unit or ''}" if item.quantity else "",
              "Calories": item.calories,
              "Protein (g)": item.protein_g, "Carbs (g)": item.carbs_g, "Fat (g)": item.fat_g}
             for item in today_logs],
            use_container_width=True,
            hide_index=True,
        )
        with st.expander("Delete a food from today"):
            for item in today_logs:
                label, action = st.columns([5, 1])
                label.write(f"{item.meal_type}: {item.food_name} ({item.calories:.0f} kcal)")
                if action.button("Delete", key=f"home_delete_log_{item.id}"):
                    meals.delete_log(item.id)
                    st.rerun()
    else:
        empty_state("🍽️ No food logged today. Add an entry manually or use AI nutrition lookup.")

tab_assistant, tab_log, tab_profile = st.tabs(["✨ AI Assistant", "Food log", "Profile"])
with tab_profile:
    render_profile(profile, nutrition, knowledge_base, assistant_memory)

with tab_log:
    section_header("Log this meal", "Use manual entry when nutrition is known, or AI lookup for a quick estimate.")
    ai_analysis_tab, manual_log_tab = st.tabs(["✨ AI nutrition lookup", "Add manually"])
    with ai_analysis_tab:
        description = st.text_area("What did you eat?", placeholder="I ate 200g chicken breast and one egg", key="log_food_description")
        ai_columns = st.columns(2)
        ai_meal_type = ai_columns[0].selectbox("Meal type (optional)", ["Unknown", "Breakfast", "Lunch", "Dinner", "Snack"], key="ai_meal_type")
        ai_log_day = ai_columns[1].date_input("Log date", date.today(), max_value=date.today(), key="ai_log_day")
        if st.button("Find nutrition", type="primary"):
            if not profile:
                st.error("Complete your profile before preparing a food log.")
            elif not description.strip():
                st.error("Describe at least one food before analysing it.")
            else:
                st.session_state.pop("pending_food_draft", None)
                try:
                    with st.status("Starting nutrition lookup…", expanded=True) as status:
                        def show_food_status(message: str) -> None:
                            status.write(message)
                            status.update(label=message, state="running")
                        items = FoodAnalysisService().analyze(description, show_food_status)
                        st.session_state["pending_food_draft"] = {
                            **new_draft(owner_id, description, items, ai_log_day, ai_meal_type), "origin": "lookup"}
                        status.update(label="Nutrition lookup complete", state="complete")
                except (AIServiceError, ValueError) as exc:
                    st.error(str(exc))
        render_food_review(meal_logging, owner_id, "lookup")
    with manual_log_tab:
        with st.form("manual_log"):
            cols = st.columns(3)
            name = cols[0].text_input("Food / meal")
            meal_type = cols[1].selectbox("Meal type", ["Breakfast", "Lunch", "Dinner", "Snack"])
            log_day = cols[2].date_input("Date", date.today(), max_value=date.today())
            calories = cols[0].number_input("Calories", 0.0, 5000.0)
            protein = cols[1].number_input("Protein (g)", 0.0, 500.0)
            carbs = cols[2].number_input("Carbs (g)", 0.0, 1000.0)
            fat = st.number_input("Fat (g)", 0.0, 500.0)
            if st.form_submit_button("Add to log"):
                if not profile:
                    st.error("Complete your profile before adding food logs.")
                elif not name.strip(): st.error("Please enter a food or meal name.")
                else:
                    meals.add_log(food_name=name.strip(), meal_type=meal_type, calories=calories, protein_g=protein, carbs_g=carbs, fat_g=fat, log_date=log_day)
                    st.session_state["food_log_saved_message"] = "Meal logged."
                    st.rerun()
    section_header("Today's full log", "Sources, validation status, and confidence remain available for review.")
    logs = meals.logs(start=date.today(), end=date.today())
    if logs:
        st.dataframe([{"ID": x.id, "Meal": x.meal_type, "Food": x.food_name, "Quantity": f"{x.quantity:g} {x.unit or ''}" if x.quantity else "",
                       "Calories": x.calories, "Protein": x.protein_g, "Carbs": x.carbs_g, "Fat": x.fat_g,
                       "Source": x.source_type or "manual", "Validation": x.validation_status or "manual",
                       "Confidence": x.confidence or ""} for x in logs], use_container_width=True, hide_index=True)
        delete_id = st.selectbox("Delete a log", [x.id for x in logs], format_func=lambda ident: next(f"{x.food_name} ({x.calories:.0f} kcal)" for x in logs if x.id == ident))
        if st.button("Delete selected log"):
            meals.delete_log(delete_id)
            st.rerun()
        st.subheader("Edit a food log")
        edit_id = st.selectbox("Food to edit", [x.id for x in logs], key="edit_log_id", format_func=lambda ident: next(f"{x.food_name} ({x.calories:.0f} kcal)" for x in logs if x.id == ident))
        editing = next(x for x in logs if x.id == edit_id)
        with st.form("edit_food_log"):
            edit_columns = st.columns(3)
            edit_name = edit_columns[0].text_input("Food", editing.food_name)
            edit_meal_type = edit_columns[1].selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack", "Unknown"], index=["Breakfast", "Lunch", "Dinner", "Snack", "Unknown"].index(editing.meal_type) if editing.meal_type in ["Breakfast", "Lunch", "Dinner", "Snack", "Unknown"] else 4)
            edit_day = edit_columns[2].date_input("Date", editing.log_date, max_value=date.today())
            edit_quantity = edit_columns[0].number_input("Quantity", 0.0, 10000.0, value=float(editing.quantity or 0.0))
            edit_unit = edit_columns[1].text_input("Unit", editing.unit or "")
            edit_calories = edit_columns[2].number_input("Calories", 0.0, 10000.0, value=float(editing.calories))
            edit_protein = edit_columns[0].number_input("Protein (g)", 0.0, 1000.0, value=float(editing.protein_g))
            edit_carbs = edit_columns[1].number_input("Carbs (g)", 0.0, 2000.0, value=float(editing.carbs_g))
            edit_fat = edit_columns[2].number_input("Fat (g)", 0.0, 1000.0, value=float(editing.fat_g))
            if st.form_submit_button("Save changes"):
                if not edit_name.strip():
                    st.error("Food name cannot be empty.")
                else:
                    meals.update_log(edit_id, food_name=edit_name.strip(), meal_type=edit_meal_type, log_date=edit_day,
                                     quantity=edit_quantity or None, unit=edit_unit.strip() or None, calories=edit_calories,
                                     protein_g=edit_protein, carbs_g=edit_carbs, fat_g=edit_fat,
                                     validation_status="user_edited", notes="Log edited by user.")
                    st.success("Food log updated.")
                    st.rerun()
    else:
        empty_state("There are no food logs to edit today.")

with tab_assistant:
    render_assistant(owner_id, meal_logging, daily_nutrition, coach, assistant_memory)
