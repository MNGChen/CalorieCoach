"""Progress charts and log management."""
from datetime import date, timedelta
import streamlit as st
from database.database import init_db
from services.meal_service import MealService
from services.nutrition_service import NutritionService
from services.progress_analysis_service import ProgressAnalysisError, ProgressAnalysisService
from utils.ui import apply_app_shell, empty_state, page_header, section_header
from utils.session_state import ensure_workspace

st.set_page_config(page_title="Progress | CalorieCoach", page_icon="📈", layout="wide")
apply_app_shell()
init_db()
ensure_workspace(st.session_state)
active_username = st.session_state.get("active_username")
if not active_username:
    st.warning("Return to the home page and enter a username before viewing personal progress.")
    st.stop()
profile = NutritionService(username=active_username).get_profile()
if profile is None:
    st.warning("Complete your profile on the home page before tracking progress.")
    st.stop()
page_header("Progress is more than a line", "Use short-term trends to understand food habits and weight changes instead of focusing on one day.", "PROGRESS")
service = MealService(user_id=profile.id)
controls, weight_action = st.columns([2, 1])
with controls:
    days = st.segmented_control("Period", [7, 30, 90], default=30, format_func=lambda x: f"Last {x} days")
    if days is None:
        days = 30
with weight_action:
    st.write("")
    st.write("")
    show_weight_form = st.toggle("Record weight")
if show_weight_form:
    with st.form("weight_form"):
        weight, day = st.columns(2)
        weight_value = weight.number_input("Weight (kg)", 30.0, 350.0, 70.0)
        recorded_day = day.date_input("Date", date.today(), max_value=date.today())
        if st.form_submit_button("Save weight", type="primary"):
            service.add_weight(weight_value, recorded_day)
            st.session_state.pop("progress_analysis", None)
            st.success("Weight saved.")
food, weights = service.progress_data(days)
analysis_key = (profile.id, days, str(profile.updated_at), food.to_json(date_format="iso"), weights.to_json(date_format="iso"))
if food.empty and weights.empty:
    empty_state("📈 No trend data yet. Log food or weight to see your changes here.")
else:
    section_header("AI trend analysis", "Get a practical interpretation of the selected period's nutrition and weight data.")
    if st.button("✨ Analyze this period", type="primary", use_container_width=True):
        try:
            target = NutritionService(username=active_username).targets(profile)
            with st.spinner("Reviewing your trend..."):
                st.session_state["progress_analysis"] = ProgressAnalysisService().analyze(
                    food, weights, {"calories": float(target.calorie_goal), "protein_g": float(target.protein_goal_g),
                                    "carbs_g": float(target.carbs_goal_g), "fat_g": float(target.fat_goal_g)},
                    profile.goal, days,
                )
                st.session_state["progress_analysis_key"] = analysis_key
        except (ProgressAnalysisError, ValueError):
            st.error("AI trend analysis is currently unavailable. Check your OpenAI API key and try again.")
    analysis = st.session_state.get("progress_analysis")
    if analysis and st.session_state.get("progress_analysis_key") == analysis_key:
        st.info(analysis.summary)
        insight, next_step = st.columns(2)
        with insight:
            st.caption("Key insight")
            st.write(analysis.insight)
        with next_step:
            st.caption("Next step")
            st.write(analysis.next_step)
        st.caption(f"Watch out: {analysis.watch_out}")
    if not food.empty:
        section_header("Nutrition trends", "Your daily calorie and protein history.")
        avg_calories, avg_protein = food["Calories"].mean(), food["Protein (g)"].mean()
        metric_a, metric_b, metric_c = st.columns(3)
        metric_a.metric("Days logged", f"{len(food)} days")
        metric_b.metric("Average calories", f"{avg_calories:.0f} kcal")
        metric_c.metric("Average protein", f"{avg_protein:.0f} g")
        st.line_chart(food.set_index("date")[["Calories"]])
        st.line_chart(food.set_index("date")[["Protein (g)"]])
    if not weights.empty:
        section_header("Weight trend", "Changes between comparable measurements are more meaningful.")
        change = weights.iloc[-1]["Weight (kg)"] - weights.iloc[0]["Weight (kg)"] if len(weights) > 1 else 0
        current, delta = st.columns(2)
        current.metric("Latest weight", f"{weights.iloc[-1]['Weight (kg)']:.1f} kg")
        delta.metric("Change in period", f"{change:+.1f} kg")
        st.line_chart(weights.set_index("date")["Weight (kg)"])
section_header("Food-log history", "Review each food entry in the selected period.")
logs = service.logs(start=date.today() - timedelta(days=days - 1), end=date.today())
if logs:
    st.dataframe([{"Date": x.log_date, "Meal": x.meal_type, "Food": x.food_name, "Calories": x.calories, "Protein (g)": x.protein_g} for x in logs], use_container_width=True, hide_index=True)
else:
    empty_state("No food logs in the selected period.")
