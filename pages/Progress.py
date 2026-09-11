"""Progress charts and log management."""
from datetime import date, timedelta
import streamlit as st
from database.database import init_db
from services.meal_service import MealService
from services.nutrition_service import NutritionService
from utils.ui import apply_app_shell, empty_state, page_header, section_header

st.set_page_config(page_title="Progress | CalorieCoach", page_icon="📈", layout="wide")
apply_app_shell()
init_db()
active_username = st.session_state.get("active_username")
if not active_username:
    st.warning("请先返回首页并输入用户名，再查看个人进度。")
    st.stop()
profile = NutritionService(username=active_username).get_profile()
if profile is None:
    st.warning("请先在首页完成个人资料，才能开始记录进度。")
    st.stop()
page_header("进度，不只是一条曲线", "用短期趋势看见饮食习惯与体重变化，而不是被单日数字左右。", "PROGRESS")
service = MealService(user_id=profile.id)
controls, weight_action = st.columns([2, 1])
with controls:
    days = st.segmented_control("查看周期", [7, 30, 90], default=30, format_func=lambda x: f"近 {x} 天")
    if days is None:
        days = 30
with weight_action:
    st.write("")
    st.write("")
    show_weight_form = st.toggle("记录体重")
if show_weight_form:
    with st.form("weight_form"):
        weight, day = st.columns(2)
        weight_value = weight.number_input("体重（kg）", 30.0, 350.0, 70.0)
        recorded_day = day.date_input("记录日期", date.today())
        if st.form_submit_button("保存体重", type="primary"):
            service.add_weight(weight_value, recorded_day)
            st.success("体重已记录。")
food, weights = service.progress_data(days)
if food.empty and weights.empty:
    empty_state("📈 暂时还没有趋势数据。记录饮食或体重后，这里会展示你的变化。")
else:
    if not food.empty:
        section_header("饮食趋势", "每日热量与蛋白质的记录情况。")
        avg_calories, avg_protein = food["Calories"].mean(), food["Protein (g)"].mean()
        metric_a, metric_b, metric_c = st.columns(3)
        metric_a.metric("记录天数", f"{len(food)} 天")
        metric_b.metric("平均热量", f"{avg_calories:.0f} kcal")
        metric_c.metric("平均蛋白质", f"{avg_protein:.0f} g")
        st.line_chart(food.set_index("date")[["Calories", "Protein (g)"]])
    if not weights.empty:
        section_header("体重趋势", "相邻记录的变化更有参考价值，建议在相近条件下测量。")
        change = weights.iloc[-1]["Weight (kg)"] - weights.iloc[0]["Weight (kg)"] if len(weights) > 1 else 0
        current, delta = st.columns(2)
        current.metric("最新体重", f"{weights.iloc[-1]['Weight (kg)']:.1f} kg")
        delta.metric("期间变化", f"{change:+.1f} kg")
        st.line_chart(weights.set_index("date")["Weight (kg)"])
section_header("历史饮食记录", "查看所选周期内的每一条饮食记录。")
logs = service.logs(start=date.today() - timedelta(days=days - 1))
if logs:
    st.dataframe([{"日期": x.log_date, "餐次": x.meal_type, "食物": x.food_name, "热量": x.calories, "蛋白质 (g)": x.protein_g} for x in logs], use_container_width=True, hide_index=True)
else:
    empty_state("所选周期内没有饮食记录。")
