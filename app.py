"""CalorieCoach entry point: dashboard, profile, and daily food log."""
from __future__ import annotations

from datetime import date

import streamlit as st

from ai.nutrition_ai import AIServiceError, NutritionAI
from database.database import init_db
from services.meal_service import MealService
from services.nutrition_service import NutritionService
from services.food_analysis_service import FoodAnalysisService
from utils.helpers import render_metric_cards

st.set_page_config(page_title="CalorieCoach", page_icon="🥗", layout="wide")
init_db()
nutrition, meals = NutritionService(), MealService()

st.title("🥗 CalorieCoach")
st.caption("Build sustainable nutrition habits, one meal at a time.")

profile = nutrition.get_profile()
if not profile:
    st.info("Start by saving your profile below. Your calorie target is then calculated automatically.")
else:
    targets = nutrition.targets(profile)
    totals = nutrition.daily_totals(date.today())
    render_metric_cards(
        totals["calories"], targets.calorie_goal, totals["protein_g"], totals["carbs_g"], totals["fat_g"],
        targets.protein_goal_g, targets.carbs_goal_g, targets.fat_goal_g,
    )
    st.caption(f"BMI {targets.bmi} · BMR {targets.bmr} kcal · TDEE {targets.tdee} kcal · Goal: {profile.goal}")
    today_logs = meals.logs(start=date.today(), end=date.today())
    st.subheader("Today's food")
    if today_logs:
        st.dataframe(
            [{"Meal": item.meal_type, "Food": item.food_name, "Calories": item.calories,
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
        st.caption("No food logged today yet. Add a meal below or use AI Food Analysis.")

tab_profile, tab_log, tab_coach = st.tabs(["Profile", "Daily food log", "AI Coach"])
with tab_profile:
    with st.form("profile_form"):
        left, right = st.columns(2)
        with left:
            age = st.number_input("Age", 16, 100, value=profile.age if profile else 30)
            gender = st.selectbox("Gender", ["Female", "Male", "Other"], index=["Female", "Male", "Other"].index(profile.gender) if profile and profile.gender in ["Female", "Male", "Other"] else 0)
            height = st.number_input("Height (cm)", 100.0, 250.0, value=profile.height_cm if profile else 170.0)
        with right:
            weight = st.number_input("Weight (kg)", 30.0, 350.0, value=profile.weight_kg if profile else 70.0)
            activity = st.selectbox("Activity level", ["Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Extra Active"], index=["Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Extra Active"].index(profile.activity_level) if profile else 0)
            goal = st.selectbox("Goal", ["Weight Loss", "Maintenance", "Muscle Gain"], index=["Weight Loss", "Maintenance", "Muscle Gain"].index(profile.goal) if profile else 0)
        if st.form_submit_button("Save profile", type="primary"):
            try:
                saved = nutrition.save_profile(age=age, gender=gender, height_cm=height, weight_kg=weight, activity_level=activity, goal=goal)
                target = nutrition.targets(saved)
                st.success(f"Profile saved. Your daily target is {target.calorie_goal} kcal.")
            except (ValueError, TypeError) as exc: st.error(str(exc))

with tab_log:
    manual_log_tab, ai_analysis_tab = st.tabs(["Add manually", "Food lookup"])
    with manual_log_tab:
        with st.form("manual_log"):
            cols = st.columns(3)
            name = cols[0].text_input("Food / meal")
            meal_type = cols[1].selectbox("Meal type", ["Breakfast", "Lunch", "Dinner", "Snack"])
            log_day = cols[2].date_input("Date", date.today())
            calories = cols[0].number_input("Calories", 0.0, 5000.0)
            protein = cols[1].number_input("Protein (g)", 0.0, 500.0)
            carbs = cols[2].number_input("Carbs (g)", 0.0, 1000.0)
            fat = st.number_input("Fat (g)", 0.0, 500.0)
            if st.form_submit_button("Add to log"):
                if not name.strip(): st.error("Please enter a food or meal name.")
                else:
                    meals.add_log(food_name=name.strip(), meal_type=meal_type, calories=calories, protein_g=protein, carbs_g=carbs, fat_g=fat, log_date=log_day)
                    st.success("Meal logged."); st.rerun()
    with ai_analysis_tab:
        description = st.text_area("What did you eat?", placeholder="I ate 200g chicken breast and one egg", key="log_food_description")
        ai_columns = st.columns(2)
        ai_meal_type = ai_columns[0].selectbox("Meal type for these estimates", ["Breakfast", "Lunch", "Dinner", "Snack"], key="ai_meal_type")
        ai_log_day = ai_columns[1].date_input("Log date", date.today(), key="ai_log_day")
        if st.button("Find nutrition", type="primary"):
            if not description.strip():
                st.error("Describe at least one food before analysing it.")
            else:
                st.session_state.pop("food_analysis_result", None)
                try:
                    with st.spinner("Checking local foods, then searching the web only if needed..."):
                        st.session_state["food_analysis_result"] = FoodAnalysisService().analyze(description)
                except (AIServiceError, ValueError) as exc:
                    st.error(str(exc))
        result = st.session_state.get("food_analysis_result")
        if result:
            items = result
            if not items:
                st.error("No food items were returned. Try a more specific description.")
            else:
                display_items = [{"Input food": item["input_food"], "Source": item["source_type"],
                                  "Resolved": item["resolved"],
                                  "Food": item["matched_food"]["name"] if item["resolved"] else "Not found",
                                  "Serving": item["matched_food"]["serving_size"] if item["resolved"] else "",
                                  "Calories": item["matched_food"]["calories"] if item["resolved"] else "",
                                  "Protein (g)": item["matched_food"]["protein_g"] if item["resolved"] else "",
                                  "Carbs (g)": item["matched_food"]["carbs_g"] if item["resolved"] else "",
                                  "Fat (g)": item["matched_food"]["fat_g"] if item["resolved"] else ""} for item in items]
                st.dataframe(display_items, use_container_width=True, hide_index=True)
                for item in items:
                    if item["source_type"] == "web" and item["resolved"]:
                        st.caption("Web source: " + ", ".join(source["url"] for source in item["sources"]))
                    elif not item["resolved"]:
                        st.caption(f"{item['input_food']}: {item['reason']}")
                if st.button("Add resolved foods to today's log", type="primary"):
                    try:
                        for item in items:
                            if not item["resolved"]:
                                continue
                            food = item["matched_food"]
                            meals.add_log(food_name=str(food["name"]), meal_type=ai_meal_type, calories=float(food["calories"]), protein_g=float(food["protein_g"]), carbs_g=float(food["carbs_g"]), fat_g=float(food["fat_g"]), log_date=ai_log_day, notes="Local food database match")
                        del st.session_state["food_analysis_result"]
                        st.success(f"Added {sum(item['resolved'] for item in items)} resolved food(s) to today's food log.")
                    except (TypeError, ValueError) as exc:
                        st.error(f"Could not save the estimates: {exc}")
    st.subheader("Today's food log")
    logs = meals.logs(start=date.today(), end=date.today())
    if logs:
        st.dataframe([{"ID": x.id, "Meal": x.meal_type, "Food": x.food_name, "Calories": x.calories, "Protein": x.protein_g, "Carbs": x.carbs_g, "Fat": x.fat_g} for x in logs], use_container_width=True, hide_index=True)
        delete_id = st.selectbox("Delete a log", [x.id for x in logs], format_func=lambda ident: next(f"{x.food_name} ({x.calories:.0f} kcal)" for x in logs if x.id == ident))
        if st.button("Delete selected log"):
            meals.delete_log(delete_id)
            st.rerun()
    else:
        st.caption("No food logged today yet.")

with tab_coach:
    question = st.text_area("Ask your nutrition coach", placeholder="How can I increase protein without increasing calories too much?")
    attach_intake = st.checkbox("Attach today's intake", help="Includes today's food, calories, and macros in your question.")
    attach_target = st.checkbox("Attach today's target", help="Includes your calorie and macro goals in your question.")
    if st.button("Get coaching advice"):
        if not question.strip():
            st.error("Please enter a question for your coach.")
        else:
            context_parts = [f"User goal: {profile.goal if profile else 'not set'}."]
            if attach_intake:
                intake = nutrition.daily_totals(date.today())
                foods = meals.logs(start=date.today(), end=date.today())
                food_names = ", ".join(item.food_name for item in foods) or "No foods logged"
                context_parts.append(f"Today's intake: {intake['calories']:.0f} kcal, {intake['protein_g']:.0f}g protein, {intake['carbs_g']:.0f}g carbs, {intake['fat_g']:.0f}g fat. Foods: {food_names}.")
            if attach_target:
                if profile:
                    target = nutrition.targets(profile)
                    context_parts.append(f"Today's targets: {target.calorie_goal} kcal, {target.protein_goal_g}g protein, {target.carbs_goal_g}g carbs, {target.fat_goal_g}g fat.")
                else:
                    context_parts.append("Today's targets are unavailable because the profile is not set.")
            context = " ".join(context_parts)
            st.session_state.pop("coach_answer", None)
            try:
                with st.spinner("Thinking..."):
                    st.session_state["coach_answer"] = NutritionAI().coach(question, context)
            except AIServiceError as exc:
                st.error(str(exc))
    if answer := st.session_state.get("coach_answer"):
        st.subheader("Coach's advice")
        st.write(answer)
