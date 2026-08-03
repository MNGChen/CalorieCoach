"""Shared non-business-logic helpers."""
from __future__ import annotations

from datetime import date

import streamlit as st


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def render_metric_cards(
    calories: float,
    calorie_goal: float,
    protein: float,
    carbs: float,
    fat: float,
    protein_goal: float = 0,
    carbs_goal: float = 0,
    fat_goal: float = 0,
) -> None:
    """Render consistent daily summary metrics."""
    remaining = max(0, calorie_goal - calories)
    columns = st.columns(5)
    for col, label, value in zip(columns, ["Target", "Consumed", "Remaining", "Protein", "Carbs / Fat"],
                                 [f"{calorie_goal:.0f} kcal", f"{calories:.0f} kcal", f"{remaining:.0f} kcal",
                                  f"{protein:.0f} g", f"{carbs:.0f} / {fat:.0f} g"]):
        col.metric(label, value)
    _render_goal_bar("Calories", calories, calorie_goal, "🔥")
    st.subheader("Macro progress")
    for label, current, target, icon in (
        ("Protein", protein, protein_goal, "💪"),
        ("Carbohydrates", carbs, carbs_goal, "🌾"),
        ("Fat", fat, fat_goal, "🥑"),
    ):
        _render_goal_bar(label, current, target, icon, unit="g")


def _render_goal_bar(label: str, current: float, target: float, icon: str, unit: str = "kcal") -> None:
    """Render a progress bar that turns red when its target is exceeded."""
    exceeded = target > 0 and current > target
    color = "#dc2626" if exceeded else "#16a34a"
    width = min(100, (current / target * 100) if target else 0)
    status = " — over target" if exceeded else ""
    st.markdown(
        f"""<div style="margin:0.35rem 0 0.7rem">
        <div style="display:flex;justify-content:space-between;font-size:0.9rem">
          <span>{icon} {label}{status}</span><span>{current:.0f} / {target:.0f} {unit}</span>
        </div>
        <div style="background:#e5e7eb;border-radius:999px;height:0.65rem;overflow:hidden;margin-top:0.2rem">
          <div style="background:{color};width:{width:.1f}%;height:100%;border-radius:999px"></div>
        </div></div>""",
        unsafe_allow_html=True,
    )


def today() -> date:
    return date.today()
