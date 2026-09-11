"""Meal planner page."""
import streamlit as st
from ai.nutrition_ai import AIServiceError, NutritionAI
from database.database import init_db
from services.nutrition_service import NutritionService
from utils.ui import apply_app_shell, empty_state, page_header, section_header

st.set_page_config(page_title="Meal Planner | CalorieCoach", page_icon="🍽️", layout="wide")
apply_app_shell()
init_db()
page_header("Make your next meal easier", "Generate a day of meal ideas from your calorie target and dietary preference. Suggestions are never logged automatically.", "MEAL PLANNER")
active_username = st.session_state.get("active_username")
if not active_username:
    st.warning("Return to the home page and enter a username before generating a personal meal plan.")
    st.stop()
nutrition = NutritionService(username=active_username)
profile = nutrition.get_profile()
default = nutrition.targets(profile).calorie_goal if profile else 2000
section_header("Create your meal plan", "Choose a daily calorie budget and dietary preference first.")
left, right = st.columns(2)
calories = left.number_input("Daily calorie target (kcal)", 1200, 5000, default)
preference = right.selectbox("Dietary preference", ["High protein", "Vegetarian", "Keto", "Low carb", "Budget meals", "No preference"])
if st.button("Generate daily meal plan", type="primary", use_container_width=True):
    try:
        with st.spinner("Creating your plan..."):
            result = NutritionAI().meal_plan(calories, preference)
        plan = result.data
        total = 0
        section_header("Today's meal ideas", "Generated from your choices. Add any meal you like to the food log manually.")
        cards = st.columns(4)
        meal_labels = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "snack": "Snack"}
        for label in ("breakfast", "lunch", "dinner", "snack"):
            meal = plan.get(label, {})
            if meal:
                card = cards[("breakfast", "lunch", "dinner", "snack").index(label)]
                card.markdown(f"**{meal_labels[label]}**")
                card.write(meal.get("name", "Meal"))
                card.caption(f"{meal.get('calories', 0)} kcal · Protein {meal.get('protein_g', 0)}g · Carbs {meal.get('carbs_g', 0)}g · Fat {meal.get('fat_g', 0)}g")
                total += float(meal.get("calories", 0))
        st.metric("Plan total", f"{total:.0f} kcal", delta=f"{total - calories:+.0f} kcal from target")
        if plan.get("notes"): st.info(plan["notes"])
    except AIServiceError as exc:
        st.error(str(exc))
else:
    empty_state("🍽️ Choose a preference and select “Generate daily meal plan” to see results here.")
