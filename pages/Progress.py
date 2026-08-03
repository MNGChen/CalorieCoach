"""Progress charts and log management."""
from datetime import date, timedelta
import matplotlib.pyplot as plt
import streamlit as st
from database.database import init_db
from services.meal_service import MealService

st.set_page_config(page_title="Progress | CalorieCoach", page_icon="📈", layout="wide")
init_db(); st.title("📈 Progress")
service = MealService()
with st.expander("Record weight", expanded=False):
    with st.form("weight_form"):
        weight = st.number_input("Weight (kg)", 30.0, 350.0, 70.0); day = st.date_input("Date", date.today())
        if st.form_submit_button("Save weight"): service.add_weight(weight, day); st.success("Weight recorded.")
days = st.selectbox("Period", [7, 30, 90], index=1, format_func=lambda x: f"Last {x} days")
food, weights = service.progress_data(days)
if food.empty and weights.empty: st.info("Log food or record weight to see your progress.")
else:
    if not food.empty:
        st.subheader("Calorie and protein intake")
        st.line_chart(food.set_index("date")[["Calories", "Protein (g)"]])
        start = date.today() - timedelta(days=days - 1)
        avg_calories, avg_protein = food["Calories"].mean(), food["Protein (g)"].mean()
        a, b = st.columns(2); a.metric("Average daily calories", f"{avg_calories:.0f} kcal"); b.metric("Average protein", f"{avg_protein:.0f} g")
    if not weights.empty:
        st.subheader("Weight trend")
        st.line_chart(weights.set_index("date")["Weight (kg)"])
st.subheader("Food log history")
logs = service.logs(start=date.today() - timedelta(days=days - 1))
if logs: st.dataframe([{"Date": x.log_date, "Meal": x.meal_type, "Food": x.food_name, "Calories": x.calories, "Protein (g)": x.protein_g} for x in logs], use_container_width=True, hide_index=True)
