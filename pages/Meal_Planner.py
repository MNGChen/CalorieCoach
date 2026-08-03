"""Meal planner page."""
import streamlit as st
from ai.nutrition_ai import AIServiceError, NutritionAI
from database.database import init_db
from services.nutrition_service import NutritionService

st.set_page_config(page_title="Meal Planner | CalorieCoach", page_icon="🍽️", layout="wide")
init_db(); st.title("🍽️ Meal Planner")
profile = NutritionService().get_profile()
default = NutritionService().targets(profile).calorie_goal if profile else 2000
calories = st.number_input("Daily calorie target", 1200, 5000, default)
preference = st.selectbox("Dietary preference", ["High protein", "Vegetarian", "Keto", "Low carb", "Budget meals", "No preference"])
if st.button("Generate plan", type="primary"):
    try:
        with st.spinner("Creating your plan..."):
            result = NutritionAI().meal_plan(calories, preference)
        plan = result.data
        total = 0
        for label in ("breakfast", "lunch", "dinner", "snack"):
            meal = plan.get(label, {})
            if meal:
                st.subheader(label.title())
                st.write(meal.get("name", "Meal"))
                st.caption(f"{meal.get('calories', 0)} kcal · Protein {meal.get('protein_g', 0)}g · Carbs {meal.get('carbs_g', 0)}g · Fat {meal.get('fat_g', 0)}g")
                total += float(meal.get("calories", 0))
        st.metric("Total calories", f"{total:.0f} kcal")
        if plan.get("notes"): st.info(plan["notes"])
    except AIServiceError as exc:
        st.error(str(exc))
