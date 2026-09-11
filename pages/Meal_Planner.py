"""Meal planner page."""
import streamlit as st
from ai.nutrition_ai import AIServiceError, NutritionAI
from database.database import init_db
from services.nutrition_service import NutritionService
from utils.ui import apply_app_shell, empty_state, page_header, section_header

st.set_page_config(page_title="Meal Planner | CalorieCoach", page_icon="🍽️", layout="wide")
apply_app_shell()
init_db()
page_header("把下一餐，安排得更轻松", "以你的热量目标与饮食偏好生成一天的灵感菜单；建议不会自动写入记录。", "MEAL PLANNER")
active_username = st.session_state.get("active_username")
if not active_username:
    st.warning("请先返回首页并输入用户名，再生成个人菜单。")
    st.stop()
nutrition = NutritionService(username=active_username)
profile = nutrition.get_profile()
default = nutrition.targets(profile).calorie_goal if profile else 2000
section_header("生成你的菜单", "先选择一天的热量预算与饮食偏好。")
left, right = st.columns(2)
calories = left.number_input("每日热量目标（kcal）", 1200, 5000, default)
preference = right.selectbox("饮食偏好", ["High protein", "Vegetarian", "Keto", "Low carb", "Budget meals", "No preference"], format_func={"High protein":"高蛋白", "Vegetarian":"素食", "Keto":"生酮", "Low carb":"低碳", "Budget meals":"经济实惠", "No preference":"无特别偏好"}.get)
if st.button("生成一日菜单", type="primary", use_container_width=True):
    try:
        with st.spinner("Creating your plan..."):
            result = NutritionAI().meal_plan(calories, preference)
        plan = result.data
        total = 0
        section_header("今日菜单建议", "根据你的选择生成；可将喜欢的餐食手动记录到饮食日志。")
        cards = st.columns(4)
        meal_labels = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}
        for label in ("breakfast", "lunch", "dinner", "snack"):
            meal = plan.get(label, {})
            if meal:
                card = cards[("breakfast", "lunch", "dinner", "snack").index(label)]
                card.markdown(f"**{meal_labels[label]}**")
                card.write(meal.get("name", "餐食"))
                card.caption(f"{meal.get('calories', 0)} kcal · 蛋白 {meal.get('protein_g', 0)}g · 碳水 {meal.get('carbs_g', 0)}g · 脂肪 {meal.get('fat_g', 0)}g")
                total += float(meal.get("calories", 0))
        st.metric("菜单总热量", f"{total:.0f} kcal", delta=f"距目标 {total - calories:+.0f} kcal")
        if plan.get("notes"): st.info(plan["notes"])
    except AIServiceError as exc:
        st.error(str(exc))
else:
    empty_state("🍽️ 选择偏好后点击“生成一日菜单”，结果会显示在这里。")
