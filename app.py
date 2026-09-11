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
from services.nutrition_orchestrator import NutritionOrchestrator
from utils.helpers import render_metric_cards
from utils.ui import apply_app_shell, empty_state, page_header, section_header

st.set_page_config(page_title="CalorieCoach", page_icon="🥗", layout="wide")
apply_app_shell()
init_db()

with st.sidebar:
    st.markdown("## 🥗 CalorieCoach")
    st.caption("你的每日营养记录空间")
    st.divider()
    active_username = st.session_state.get("active_username")
    if active_username:
        st.success(f"当前用户：{active_username}")
        if st.button("切换用户", use_container_width=True):
            st.session_state.pop("active_username", None)
            st.rerun()
    else:
        username = st.text_input("用户名", placeholder="例如：ming")
        if st.button("进入我的空间", type="primary", use_container_width=True):
            candidate = username.strip().casefold()
            if not re.fullmatch(r"[a-z0-9_.-]{3,40}", candidate):
                st.error("用户名须为 3–40 个字符，可使用字母、数字、点、下划线或连字符。")
            else:
                st.session_state["active_username"] = candidate
                st.rerun()
        if st.button("加载演示数据", use_container_width=True, help="为这个新用户名创建 14 天示例饮食与体重记录。"):
            candidate = username.strip().casefold()
            if not re.fullmatch(r"[a-z0-9_.-]{3,40}", candidate):
                st.error("请先输入有效用户名，再加载演示数据。")
            else:
                demo_nutrition = NutritionService(username=candidate)
                try:
                    DemoDataService(demo_nutrition, MealService(user_id=-1)).load()
                    st.session_state["active_username"] = candidate
                    st.rerun()
                except DemoDataError as exc:
                    st.error(str(exc))
    st.divider()
    st.markdown("**使用建议**")
    st.caption("先完善资料，再记录饮食；每次 AI 估算都可在保存前核对与修改。")
    st.divider()
    st.caption("营养数据为估算值，不替代专业医疗建议。")

page_header("今天，吃得更明白", "记录每一餐、看懂营养进度，并按你的目标持续调整。", "DAILY NUTRITION")

active_username = st.session_state.get("active_username")
if not active_username:
    empty_state("👤 请先在左侧输入用户名，进入或创建你的个人营养空间。")
    st.stop()

nutrition = NutritionService(username=active_username)
profile = nutrition.get_profile()
owner_id = profile.id if profile else -1
meals = MealService(user_id=owner_id)
daily_nutrition = DailyNutritionService(nutrition)
meal_logging = MealLoggingService(daily_nutrition=daily_nutrition, user_id=owner_id)
coach = NutritionCoachService(daily_nutrition=daily_nutrition, nutrition=nutrition, meals=meals)
if not profile:
    empty_state(f"👋 欢迎，{active_username}。先完成下方的个人资料以创建你的独立营养空间。")
else:
    summary = daily_nutrition.summary(date.today())
    targets = nutrition.targets(profile)
    totals = summary["consumed"]
    render_metric_cards(
        totals["calories"], targets.calorie_goal, totals["protein_g"], totals["carbs_g"], totals["fat_g"],
        targets.protein_goal_g, targets.carbs_goal_g, targets.fat_goal_g,
    )
    st.caption(f"BMI {targets.bmi} · 基础代谢 {targets.bmr} kcal · TDEE {targets.tdee} kcal · 目标：{profile.goal}")
    today_logs = meals.logs(start=date.today(), end=date.today())
    section_header("今日记录", "一眼掌握今天已吃了什么；需要时可在下方完整编辑。")
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
        empty_state("🍽️ 今天还没有记录。可以手动添加，或用 AI 查找食物营养。")

tab_profile, tab_log, tab_coach, tab_assistant = st.tabs(["个人资料", "饮食记录", "AI 教练", "智能助手"])
with tab_profile:
    section_header("设置你的目标", "计算建议只是起点，你也可以使用专业人士给出的自定义目标。")
    st.info("CalorieCoach provides general adult nutrition estimates, not medical care. If you are pregnant, under 18, have an eating disorder, a medical condition, or take medication that affects diet, set goals with a qualified clinician.")
    with st.form("profile_form"):
        left, right = st.columns(2)
        with left:
            age = st.number_input("Age", 18, 100, value=max(18, profile.age) if profile else 30)
            gender = st.selectbox("Gender", ["Female", "Male", "Other"], index=["Female", "Male", "Other"].index(profile.gender) if profile and profile.gender in ["Female", "Male", "Other"] else 0)
            height = st.number_input("Height (cm)", 100.0, 250.0, value=profile.height_cm if profile else 170.0)
        with right:
            weight = st.number_input("Weight (kg)", 30.0, 350.0, value=profile.weight_kg if profile else 70.0)
            activity = st.selectbox("Activity level", ["Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Extra Active"], index=["Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Extra Active"].index(profile.activity_level) if profile else 0)
            goal = st.selectbox("Goal", ["Weight Loss", "Maintenance", "Muscle Gain"], index=["Weight Loss", "Maintenance", "Muscle Gain"].index(profile.goal) if profile else 0)
        use_custom_targets = st.checkbox("Use custom daily calorie and macro targets", value=bool(profile and profile.custom_calorie_goal))
        custom_targets: dict[str, float | None] = {"custom_calorie_goal": None, "custom_protein_goal_g": None,
                                                    "custom_carbs_goal_g": None, "custom_fat_goal_g": None}
        if use_custom_targets:
            st.caption("Use targets provided by a qualified professional, or targets you have deliberately chosen. All fields are required.")
            target_columns = st.columns(4)
            custom_targets = {
                "custom_calorie_goal": target_columns[0].number_input("Calories (kcal)", 800.0, 6000.0, value=float(profile.custom_calorie_goal) if profile and profile.custom_calorie_goal else 2000.0),
                "custom_protein_goal_g": target_columns[1].number_input("Protein (g)", 1.0, 500.0, value=float(profile.custom_protein_goal_g) if profile and profile.custom_protein_goal_g else 120.0),
                "custom_carbs_goal_g": target_columns[2].number_input("Carbs (g)", 1.0, 1000.0, value=float(profile.custom_carbs_goal_g) if profile and profile.custom_carbs_goal_g else 250.0),
                "custom_fat_goal_g": target_columns[3].number_input("Fat (g)", 1.0, 500.0, value=float(profile.custom_fat_goal_g) if profile and profile.custom_fat_goal_g else 65.0),
            }
        acknowledged = st.checkbox("I understand these are estimates and not medical advice.", value=bool(profile and profile.health_notice_acknowledged))
        if st.form_submit_button("Save profile", type="primary"):
            if not acknowledged:
                st.error("Please acknowledge the health and safety notice before saving a profile.")
            else:
                try:
                    saved = nutrition.save_profile(age=age, gender=gender, height_cm=height, weight_kg=weight, activity_level=activity, goal=goal,
                                                   health_notice_acknowledged=True, **custom_targets)
                    target = nutrition.targets(saved)
                    source = "custom" if use_custom_targets else "calculated"
                    st.success(f"Profile saved. Your {source} daily target is {target.calorie_goal} kcal.")
                    st.rerun()
                except (ValueError, TypeError) as exc:
                    st.error(str(exc))

with tab_log:
    section_header("记录这一餐", "手动输入适合已知营养数据；AI 查询适合快速估算。")
    manual_log_tab, ai_analysis_tab = st.tabs(["手动添加", "AI 营养查询"])
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
                if not profile:
                    st.error("请先完成个人资料，再添加饮食记录。")
                elif not name.strip(): st.error("Please enter a food or meal name.")
                else:
                    meals.add_log(food_name=name.strip(), meal_type=meal_type, calories=calories, protein_g=protein, carbs_g=carbs, fat_g=fat, log_date=log_day)
                    st.success("Meal logged."); st.rerun()
    with ai_analysis_tab:
        description = st.text_area("What did you eat?", placeholder="I ate 200g chicken breast and one egg", key="log_food_description")
        ai_columns = st.columns(2)
        ai_meal_type = ai_columns[0].selectbox("Meal type (optional)", ["Unknown", "Breakfast", "Lunch", "Dinner", "Snack"], key="ai_meal_type")
        ai_log_day = ai_columns[1].date_input("Log date", date.today(), key="ai_log_day")
        if st.button("Find nutrition", type="primary"):
            if not description.strip():
                st.error("Describe at least one food before analysing it.")
            else:
                st.session_state.pop("food_analysis_result", None)
                try:
                    with st.spinner("Checking local foods, then searching the web only if needed..."):
                        st.session_state["food_analysis_result"] = FoodAnalysisService().analyze(description)
                        st.session_state["food_analysis_request_id"] = str(uuid4())
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
                st.caption("Review estimates before saving. Changing a value marks that item as user-reviewed; original sources remain attached to the log.")
                review_rows = []
                for item in items:
                    food = item["matched_food"] or {}
                    review_rows.append({"Food": food.get("name", item["input_food"]), "Quantity": item.get("quantity"),
                                        "Unit": item.get("unit") or "", "Calories": food.get("calories"),
                                        "Protein (g)": food.get("protein_g"), "Carbs (g)": food.get("carbs_g"),
                                        "Fat (g)": food.get("fat_g"), "Source": item.get("source_type", "")})
                reviewed_rows = st.data_editor(review_rows, key="food_analysis_review", use_container_width=True,
                                               hide_index=True, disabled=["Source"], num_rows="fixed",
                                               column_config={"Calories": st.column_config.NumberColumn(min_value=0.0),
                                                              "Protein (g)": st.column_config.NumberColumn(min_value=0.0),
                                                              "Carbs (g)": st.column_config.NumberColumn(min_value=0.0),
                                                              "Fat (g)": st.column_config.NumberColumn(min_value=0.0),
                                                              "Quantity": st.column_config.NumberColumn(min_value=0.0)})
                for item in items:
                    if item["source_type"] == "web" and item["resolved"]:
                        st.caption("Web source: " + ", ".join(source["url"] for source in item["sources"]) + f" · validation: {item.get('validation_status', 'unknown')} · confidence: {item.get('confidence', 'unknown')}")
                    elif not item["resolved"]:
                        st.caption(f"{item['input_food']}: {item['reason']}")
                if st.button("Add resolved foods to today's log", type="primary"):
                    try:
                        reviewed_items = []
                        for item, original_row, row in zip(items, review_rows, reviewed_rows):
                            updated = {**item, "quantity": row["Quantity"] or None, "unit": str(row["Unit"]).strip() or None}
                            if updated["resolved"]:
                                updated["matched_food"] = {**item["matched_food"], "name": str(row["Food"]).strip(),
                                                          "calories": row["Calories"], "protein_g": row["Protein (g)"],
                                                          "carbs_g": row["Carbs (g)"], "fat_g": row["Fat (g)"]}
                                if row != original_row:
                                    updated["validation_status"] = "user_reviewed"
                                    updated["review_note"] = "Nutrition estimate reviewed or adjusted by user before saving."
                            reviewed_items.append(updated)
                        response = meal_logging.save_resolved(description, reviewed_items,
                                                              None if ai_meal_type == "Unknown" else ai_meal_type,
                                                              ai_log_day, st.session_state.get("food_analysis_request_id"))
                        del st.session_state["food_analysis_result"]
                        st.session_state.pop("food_analysis_request_id", None)
                        daily = response["daily_summary"]
                        st.success(f"Saved {len(response['meal']['items'])} food(s). Today's consumed calories: {daily['consumed']['calories']:.0f} kcal.")
                    except (TypeError, ValueError) as exc:
                        st.error(f"Could not save the estimates: {exc}")
    section_header("今日完整记录", "来源、验证状态与置信度会一直保留，方便回看。")
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
        st.subheader("编辑一条记录")
        edit_id = st.selectbox("Food to edit", [x.id for x in logs], key="edit_log_id", format_func=lambda ident: next(f"{x.food_name} ({x.calories:.0f} kcal)" for x in logs if x.id == ident))
        editing = next(x for x in logs if x.id == edit_id)
        with st.form("edit_food_log"):
            edit_columns = st.columns(3)
            edit_name = edit_columns[0].text_input("Food", editing.food_name)
            edit_meal_type = edit_columns[1].selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack", "Unknown"], index=["Breakfast", "Lunch", "Dinner", "Snack", "Unknown"].index(editing.meal_type) if editing.meal_type in ["Breakfast", "Lunch", "Dinner", "Snack", "Unknown"] else 4)
            edit_day = edit_columns[2].date_input("Date", editing.log_date)
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
        empty_state("还没有可编辑的今日记录。")

with tab_coach:
    section_header("问问 AI 教练", "建议会基于你的今日摄入和剩余目标生成。")
    question = st.text_area("Ask your nutrition coach", placeholder="What should I eat next?", key="coach_question")
    if st.button("Get coaching advice"):
        st.session_state.pop("coach_answer", None)
        try:
            with st.spinner("Reviewing today's nutrition progress..."):
                st.session_state["coach_answer"] = coach.get_nutrition_advice(question)
        except ValueError as exc:
            st.error(str(exc))
    if answer := st.session_state.get("coach_answer"):
        if not answer["available"]:
            st.info(answer["reason"])
        else:
            st.subheader("Coach's advice")
            st.write(answer["summary"])
            st.write(answer["recommendation"])
            st.caption(answer["reasoning_summary"])
            if answer["avoid_or_limit"]:
                st.write("Consider limiting: " + ", ".join(answer["avoid_or_limit"]))
            budget = answer["target_for_next_meal"]
            st.caption(f"Remaining daily budget: {budget['calories']:.0f} kcal · {budget['protein_g']:.0f}g protein · {budget['carbs_g']:.0f}g carbs · {budget['fat_g']:.0f}g fat")

with tab_assistant:
    section_header("智能营养助手", "可识别记录饮食、查看进度或推荐下一餐。")
    assistant_message = st.text_area("Ask CalorieCoach", placeholder="What should I eat for dinner?", key="v1_assistant_message")
    if st.button("Send to V1 Assistant"):
        if not assistant_message.strip(): st.error("Enter a message first.")
        else:
            try:
                with st.spinner("Routing your request..."):
                    st.session_state["v1_assistant_response"] = NutritionOrchestrator(
                        meal_logging=meal_logging, daily=daily_nutrition, coach=coach
                    ).handle(assistant_message)
            except Exception:
                st.error("The assistant is currently unavailable.")
    if response := st.session_state.get("v1_assistant_response"):
        st.write(response["message"])
        st.json(response["data"])
