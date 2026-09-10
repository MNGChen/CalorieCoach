"""Profile and daily-nutrition query service."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func, select

from database.database import get_session
from database.models import FoodLog, UserProfile
from services.calorie_calculator import CalorieCalculator, NutritionTargets


class NutritionService:
    def __init__(self, session_factory: object = get_session) -> None:
        self.session_factory = session_factory

    def get_profile(self) -> Optional[UserProfile]:
        with self.session_factory() as session:  # type: ignore[operator]
            return session.scalar(select(UserProfile).order_by(UserProfile.id).limit(1))

    def save_profile(self, **values: object) -> UserProfile:
        with self.session_factory() as session:  # type: ignore[operator]
            profile = session.scalar(select(UserProfile).order_by(UserProfile.id).limit(1))
            if profile is None:
                profile = UserProfile(**values)  # type: ignore[arg-type]
                session.add(profile)
            else:
                for key, value in values.items():
                    setattr(profile, key, value)
            session.flush()
            session.refresh(profile)
            return profile

    def targets(self, profile: UserProfile) -> NutritionTargets:
        return CalorieCalculator.calculate(profile.age, profile.gender, profile.height_cm, profile.weight_kg,
                                           profile.activity_level, profile.goal)

    def daily_totals(self, day: date) -> dict[str, float]:
        with self.session_factory() as session:  # type: ignore[operator]
            row = session.execute(select(func.coalesce(func.sum(FoodLog.calories), 0),
                                         func.coalesce(func.sum(FoodLog.protein_g), 0),
                                         func.coalesce(func.sum(FoodLog.carbs_g), 0),
                                         func.coalesce(func.sum(FoodLog.fat_g), 0)).where(FoodLog.log_date == day)).one()
        return dict(zip(("calories", "protein_g", "carbs_g", "fat_g"), map(float, row)))
