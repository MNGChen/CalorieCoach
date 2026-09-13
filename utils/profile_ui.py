"""Profile, knowledge sources and reviewable assistant memory."""
import streamlit as st
from services.knowledge_base_service import AUTHORITATIVE_SOURCES
from utils.ui import section_header


def render_profile(profile, nutrition, knowledge_base, assistant_memory):
    section_header("Set your targets", "Calculated recommendations are a starting point; you may also use targets from a qualified professional.")
    st.info("CalorieCoach provides general adult nutrition estimates, not medical care. If you are pregnant, under 18, have an eating disorder, a medical condition, or take medication that affects diet, set goals with a qualified clinician.")
    use_custom_targets = st.checkbox("Use custom daily calorie and macro targets", value=bool(profile and profile.custom_calorie_goal))
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
    if profile:
        with st.expander("Nutrition knowledge base", expanded=False):
            stats = knowledge_base.stats()
            st.caption(f"{stats['sources']} curated public-health sources · {stats['chunks']} searchable chunks. "
                       "The starter set is local; refresh downloads the current text from the listed sources.")
            if st.button("Refresh authoritative web sources", key="refresh_knowledge_base"):
                with st.spinner("Refreshing and indexing public nutrition sources…"):
                    result = knowledge_base.refresh_authoritative_sources()
                if result["updated"]:
                    st.success(f"Updated {result['updated']} source(s).")
                if result["failed"]:
                    st.warning(f"{result['failed']} source(s) could not be refreshed; existing indexed content was kept.")
                if result.get("skipped"):
                    st.caption(f"{result['skipped']} source(s) retain their reviewed starter content because their publisher blocks automated refreshes.")
                if not result["updated"] and not result["failed"] and not result.get("skipped"):
                    st.info("Sources are already current.")
            for source in AUTHORITATIVE_SOURCES:
                st.markdown(f"- [{source.publisher}: {source.title}]({source.url})")
        with st.expander("Assistant memory", expanded=False):
            st.caption("The assistant only uses these saved preferences and constraints alongside your current nutrition data. You can edit or remove them at any time.")
            stored_memories = assistant_memory.list_memories()
            if stored_memories:
                for memory in stored_memories:
                    left, right = st.columns([6, 1])
                    left.write(f"**{memory.category.replace('_', ' ').title()}** — {memory.content}")
                    if not memory.confirmed:
                        left.caption("Pending confirmation — review this dietary preference or restriction.")
                        if left.button("Confirm memory", key=f"confirm_memory_{memory.id}"):
                            assistant_memory.confirm_memory(memory.id)
                            st.rerun()
                    if right.button("Remove", key=f"delete_memory_{memory.id}"):
                        assistant_memory.delete_memory(memory.id)
                        st.rerun()
            else:
                st.caption("No long-term assistant memories saved yet.")
            with st.form("add_assistant_memory", clear_on_submit=True):
                memory_category = st.selectbox("Memory type", ["diet_preference", "restriction", "routine", "goal_context", "communication_style"],
                                               format_func=lambda value: value.replace("_", " ").title())
                memory_content = st.text_input("Add a preference or constraint", placeholder="e.g. I prefer quick, dairy-free dinners.")
                if st.form_submit_button("Save memory"):
                    try:
                        assistant_memory.add_memory(memory_category, memory_content)
                        st.success("Assistant memory saved.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
