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
    columns = st.columns(4)
    for col, label, consumed, target, unit in (
        (columns[0], "热量", calories, calorie_goal, "kcal"),
        (columns[1], "蛋白质", protein, protein_goal, "g"),
        (columns[2], "碳水", carbs, carbs_goal, "g"),
        (columns[3], "脂肪", fat, fat_goal, "g"),
    ):
        remaining = target - consumed
        col.metric(label, f"{consumed:.0f} / {target:.0f} {unit}", delta=f"还差 {remaining:.0f} {unit}")
    _render_goal_bar("热量", calories, calorie_goal, "🔥")
    st.subheader("三大营养素进度")
    for label, current, target, icon in (
        ("蛋白质", protein, protein_goal, "💪"),
        ("碳水", carbs, carbs_goal, "🌾"),
        ("脂肪", fat, fat_goal, "🥑"),
    ):
        _render_goal_bar(label, current, target, icon, unit="g")


def _render_goal_bar(label: str, current: float, target: float, icon: str, unit: str = "kcal") -> None:
    """Render a progress bar that turns red when its target is exceeded."""
    exceeded = target > 0 and current > target
    color = "#dc2626" if exceeded else "#16a34a"
    width = min(100, (current / target * 100) if target else 0)
    remaining = target - current
    status = " · 已超出目标" if exceeded else ""
    st.markdown(
        f"""<div style="margin:0.35rem 0 0.7rem">
        <div style="display:flex;justify-content:space-between;font-size:0.9rem">
          <span>{icon} {label}{status}</span><span>{current:.0f} / {target:.0f} {unit} · 还差 {remaining:.0f}</span>
        </div>
        <div style="background:#e5e7eb;border-radius:999px;height:0.65rem;overflow:hidden;margin-top:0.2rem">
          <div style="background:{color};width:{width:.1f}%;height:100%;border-radius:999px"></div>
        </div></div>""",
        unsafe_allow_html=True,
    )


def today() -> date:
    return date.today()
