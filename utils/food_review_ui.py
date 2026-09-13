"""Shared confirmation UI for food estimates from chat and lookup."""
from datetime import date
import streamlit as st
from services.food_review_service import review_items


def render_food_review(logging_service, user_id: int, origin: str) -> None:
    draft = st.session_state.get("pending_food_draft")
    if not draft or draft.get("origin") != origin:
        return
    if draft["user_id"] != user_id:
        st.session_state.pop("pending_food_draft", None)
        return
    st.subheader("Review this food log")
    st.caption(f"Original description: {draft['original_input']}")
    prefix = draft["request_id"]
    for index, item in enumerate(draft["items"]):
        if candidates := item.get("local_candidates"):
            selected = st.selectbox(f"Choose the dish for {item['input_food']}",
                                    range(len(candidates)), key=f"{prefix}_candidate_{index}",
                                    format_func=lambda i: candidates[i]["name"])
            if st.button("Use selected dish", key=f"{prefix}_use_{index}"):
                candidate = candidates[selected]
                item.update(resolved=True, matched=True, matched_food=candidates[selected],
                            validation_status="needs_review", portion_note=candidate.get("portion_note", "Confirm the reference portion below."),
                            source_label=candidate.get("source_label"), source_version=candidate.get("source_version"),
                            nutrition_quality=candidate.get("nutrition_quality", "unverified"))
                item.pop("local_candidates", None)
                st.rerun()
        if not item.get("resolved"):
            st.warning(f"Not included: {item['input_food']} — {item.get('reason', 'No nutrition found.')}")
        elif note := item.get("portion_note"):
            st.warning(f"{item['input_food']}: {note}")
        if item.get("source_type") == "local_database" and item.get("resolved"):
            st.caption(f"{item['matched_food']['name']}: catalogue estimate; source quality {item.get('nutrition_quality', 'unverified')}; "
                       f"reference portion {item['matched_food'].get('serving_size', 'unknown')}.")
        if item.get("source_type") == "web":
            st.caption(f"Evidence assessment: {item.get('validation_status', 'unknown')}")
            for source in item.get("sources", []):
                st.markdown(f"- [{source.get('title', 'Nutrition source')}]({source['url']})")
    rows = []
    for item in draft["items"]:
        if item.get("resolved"):
            food = item["matched_food"]
            rows.append({"Food": food["name"], "Quantity": item.get("quantity"), "Unit": item.get("unit") or "",
                         "Calories": food["calories"], "Protein (g)": food["protein_g"],
                         "Carbs (g)": food["carbs_g"], "Fat (g)": food["fat_g"]})
    if not rows:
        st.info("Choose a matching dish above, try a more specific description, or add the meal manually.")
    else:
        st.caption("Confirm the reference portion and nutrition. To change quantities, run a new lookup; you can adjust nutrition totals here.")
        with st.form(f"{prefix}_review"):
            columns = st.columns(2)
            day = columns[0].date_input("Save on date", draft["day"], max_value=date.today())
            meal_types = ["Unknown", "Breakfast", "Lunch", "Dinner", "Snack"]
            meal_type = columns[1].selectbox("Save as meal", meal_types,
                                            index=meal_types.index(draft["meal_type"]))
            edited = st.data_editor(rows, key=f"{prefix}_rows_{len(rows)}", hide_index=True,
                                    num_rows="fixed", disabled=["Quantity", "Unit"],
                                    column_config={name: st.column_config.NumberColumn(min_value=0.0, required=True)
                                                   for name in ("Calories", "Protein (g)", "Carbs (g)", "Fat (g)")})
            confirmed = st.checkbox("I confirm the food, portion and nutrition values shown above.")
            partial = any(not item.get("resolved") for item in draft["items"])
            allow_partial = st.checkbox("Save only the resolved foods; I will add the missing foods separately.") if partial else True
            if st.form_submit_button("Confirm and save food", type="primary"):
                if not confirmed or not allow_partial:
                    st.error("Confirm the estimate and any missing foods before saving.")
                else:
                    try:
                        items = review_items(draft, edited, user_id)
                        response = logging_service.save_resolved(draft["original_input"], items, meal_type, day, draft["request_id"])
                        st.session_state.pop("pending_food_draft", None)
                        st.session_state.pop("assistant_response", None)
                        st.session_state.pop("progress_analysis", None)
                        st.session_state["food_log_saved_message"] = f"Saved {len(response['meal']['items'])} food(s) for {day.isoformat()}."
                        if draft.get("follow_up_request"):
                            st.session_state["assistant_follow_up"] = draft["follow_up_request"]
                        st.rerun()
                    except (ValueError, TypeError) as exc:
                        st.error(f"Could not save: {exc}")
    if st.button("Discard estimate", key=f"{prefix}_discard"):
        st.session_state.pop("pending_food_draft", None)
        st.rerun()
