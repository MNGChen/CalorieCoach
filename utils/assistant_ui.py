"""Assistant interaction and response rendering."""
import streamlit as st
from services.nutrition_orchestrator import NutritionOrchestrator
from services.food_review_service import new_draft
from utils.food_review_ui import render_food_review
from utils.ui import section_header


def render_assistant(owner_id, meal_logging, daily_nutrition, coach, assistant_memory):
    section_header("Your AI nutrition assistant", "Ask about today's progress, get coaching, log a meal, or receive a next-meal suggestion based on your remaining daily budget.")
    st.info("Start here for personalised help. Recommendations use your profile and today's logged food; they are suggestions, not medical advice.")
    st.caption("What would you like help with?")
    quick_prompts = [
        ("🍽️ Log food", "I ate chicken rice and an iced coffee."),
        ("📊 Today's progress", "How many calories do I have left today?"),
        ("💪 Nutrition advice", "Do I need more protein today?"),
        ("✨ Recommend my next meal", "What should I eat for dinner?"),
    ]
    quick_columns = st.columns(4)
    for column, (label, prompt) in zip(quick_columns, quick_prompts):
        if column.button(label, key=f"quick_prompt_{label}", use_container_width=True):
            st.session_state["assistant_message"] = prompt
    assistant_message = st.text_area(
        "Ask CalorieCoach",
        placeholder="For example: I had chicken rice for lunch — what should I eat for dinner?",
        key="assistant_message",
    )
    follow_up = st.session_state.pop("assistant_follow_up", None)
    if st.button("Send message", type="primary") or follow_up:
        if follow_up:
            assistant_message = follow_up
        if not assistant_message.strip(): st.error("Enter a message first.")
        elif owner_id <= 0: st.error("Complete your profile before using the assistant.")
        else:
            try:
                with st.status("Starting your request…", expanded=True) as status:
                    def show_assistant_status(message: str) -> None:
                        status.write(message)
                        status.update(label=message, state="running")
                    st.session_state["assistant_response"] = NutritionOrchestrator(
                        meal_logging=meal_logging, daily=daily_nutrition, coach=coach,
                        memory=assistant_memory,
                        on_status=show_assistant_status,
                    ).handle(assistant_message)
                    result_data = st.session_state["assistant_response"]["data"]
                    if "pending_foods" in result_data:
                        st.session_state["pending_food_draft"] = {
                            **new_draft(owner_id, result_data["original_input"], result_data["pending_foods"],
                                        follow_up=result_data.get("follow_up_request")), "origin": "chat"}
                    status.update(label="Response ready", state="complete")
            except Exception:
                st.error("The assistant is currently unavailable.")
    if response := st.session_state.get("assistant_response"):
        st.subheader("Assistant response")
        with st.container(border=True):
            st.caption("PERSONALISED GUIDANCE")
            st.write(response["message"])
        data = response["data"]
        if warning := data.get("planning_warning"):
            st.warning(warning)
        if saved_memories := data.get("saved_memories"):
            st.caption("Saved to assistant memory: " + "; ".join(item["content"] for item in saved_memories))
        if menu := data.get("restaurant_menu"):
            st.subheader(f"Official {menu['restaurant']} menu search")
            if menu["available"]:
                st.info("These are official menu options only. Their nutrition values are not verified, so they are not compared with your daily targets and cannot be saved as a food log.")
                st.dataframe([{"Menu item": item["name"], "Why it may fit": item["reason"], "Nutrition status": "Not verified"}
                              for item in menu["items"]], use_container_width=True, hide_index=True)
            else:
                st.warning(menu["reason"])
            if menu["sources"]:
                st.caption("Official menu sources")
                for source in menu["sources"]:
                    st.markdown(f"- [{source['title']}]({source['url']})")
        advice = data.get("coach", data)
        if advice.get("available"):
            if data.get("llm_fallback"):
                st.info("AI-generated general ordering strategy — not an official restaurant menu or verified nutrition data.")
            if (recommendation := advice.get("recommendation")) and recommendation != response["message"]:
                st.write(recommendation)
            if advice.get("avoid_or_limit"):
                st.caption("Consider limiting: " + ", ".join(advice["avoid_or_limit"]))
            if budget := advice.get("target_for_next_meal"):
                st.caption(f"Suggested budget for this meal: {budget['calories']:.0f} kcal · {budget['protein_g']:.0f}g protein · {budget['carbs_g']:.0f}g carbs · {budget['fat_g']:.0f}g fat")
            if sources := advice.get("knowledge_sources"):
                st.caption("Knowledge sources used")
                for source in sources:
                    st.markdown(f"- [{source['publisher']}: {source['title']}]({source['url']})")
        if meal_plan := data.get("meal_plan"):
            st.caption("Suggested foods")
            st.caption("Nutrition is a catalogue estimate. The calculated meal passed the portion and budget checks.")
            st.dataframe(meal_plan.get("foods", []), use_container_width=True, hide_index=True)
        if summary := data.get("daily_summary"):
            with st.expander("View daily nutrition summary"):
                st.json(summary)
        with st.expander("View response details"):
            st.json(data)

    render_food_review(meal_logging, owner_id, "chat")
