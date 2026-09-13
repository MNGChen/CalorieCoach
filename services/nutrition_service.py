"""Profile and daily-nutrition query service."""
from __future__ import annotations

from datetime import date
from dataclasses import replace
from typing import Optional
import math

from sqlalchemy import func, select

from database.database import get_session
from database.models import FoodLog, UserProfile
from services.calorie_calculator import CalorieCalculator, NutritionTargets


class NutritionService:
    def __init__(self, session_factory: object = get_session, username: str | None = None) -> None:
        self.session_factory = session_factory
        self.username = username.strip().casefold() if username else None

    def get_profile(self) -> Optional[UserProfile]:
        if not self.username:
            return None
        with self.session_factory() as session:  # type: ignore[operator]
            query = select(UserProfile).order_by(UserProfile.id).limit(1)
            if self.username:
                query = query.where(UserProfile.username == self.username)
            return session.scalar(query)

    def save_profile(self, **values: object) -> UserProfile:
        if not self.username:
            raise ValueError("Select a user workspace before saving a profile.")
        allowed = {"age", "gender", "height_cm", "weight_kg", "activity_level", "goal",
                   "custom_calorie_goal", "custom_protein_goal_g", "custom_carbs_goal_g", "custom_fat_goal_g",
                   "health_notice_acknowledged"}
        if set(values) - allowed:
            raise ValueError("Unsupported profile field.")
        with self.session_factory() as session:  # type: ignore[operator]
            query = select(UserProfile).order_by(UserProfile.id).limit(1)
            if self.username:
                query = query.where(UserProfile.username == self.username)
            profile = session.scalar(query)
            if profile is None:
                if self.username:
                    values["username"] = self.username
                profile = UserProfile(**values)  # type: ignore[arg-type]
                session.add(profile)
            else:
                for key, value in values.items():
                    setattr(profile, key, value)
            # Validate before commit, so invalid targets cannot break subsequent page loads.
            self.targets(profile)
            session.flush()
            session.refresh(profile)
            return profile

    def targets(self, profile: UserProfile) -> NutritionTargets:
        calculated = CalorieCalculator.calculate(profile.age, profile.gender, profile.height_cm, profile.weight_kg,
                                                 profile.activity_level, profile.goal)
        overrides = {
            "calorie_goal": profile.custom_calorie_goal,
            "protein_goal_g": profile.custom_protein_goal_g,
            "carbs_goal_g": profile.custom_carbs_goal_g,
            "fat_goal_g": profile.custom_fat_goal_g,
        }
        if all(value is None for value in overrides.values()):
            return calculated
        if any(value is None or not math.isfinite(value) or value <= 0 for value in overrides.values()):
            raise ValueError("Custom daily targets must include positive calories and all three macros.")
        return replace(calculated, **{key: round(float(value)) for key, value in overrides.items()})

    def daily_totals(self, day: date) -> dict[str, float]:
        if not self.username:
            return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
        with self.session_factory() as session:  # type: ignore[operator]
            query = select(func.coalesce(func.sum(FoodLog.calories), 0),
                                         func.coalesce(func.sum(FoodLog.protein_g), 0),
                                         func.coalesce(func.sum(FoodLog.carbs_g), 0),
                                         func.coalesce(func.sum(FoodLog.fat_g), 0)).where(FoodLog.log_date == day)
            if self.username:
                profile = session.scalar(select(UserProfile).where(UserProfile.username == self.username))
                if profile is None:
                    return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
                query = query.where(FoodLog.user_id == profile.id)
            row = session.execute(query).one()
        return dict(zip(("calories", "protein_g", "carbs_g", "fat_g"), map(float, row)))
