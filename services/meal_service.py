"""Food-log CRUD and reporting queries."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select

from database.database import get_session
from database.models import FoodLog, WeightEntry


class MealService:
    def add_log(self, **values: object) -> FoodLog:
        with get_session() as session:
            entry = FoodLog(**values)  # type: ignore[arg-type]
            session.add(entry)
            session.flush(); session.refresh(entry)
            return entry

    def update_log(self, log_id: int, **values: object) -> None:
        with get_session() as session:
            entry = session.get(FoodLog, log_id)
            if entry is None: raise ValueError("Food log not found.")
            for key, value in values.items(): setattr(entry, key, value)

    def delete_log(self, log_id: int) -> None:
        with get_session() as session:
            entry = session.get(FoodLog, log_id)
            if entry is None: raise ValueError("Food log not found.")
            session.delete(entry)

    def logs(self, start: date | None = None, end: date | None = None) -> list[FoodLog]:
        with get_session() as session:
            query = select(FoodLog).order_by(FoodLog.log_date.desc(), FoodLog.id.desc())
            if start: query = query.where(FoodLog.log_date >= start)
            if end: query = query.where(FoodLog.log_date <= end)
            return list(session.scalars(query))

    def add_weight(self, weight_kg: float, recorded_on: date, notes: str | None = None) -> None:
        with get_session() as session:
            entry = session.scalar(select(WeightEntry).where(WeightEntry.recorded_on == recorded_on))
            if entry: entry.weight_kg, entry.notes = weight_kg, notes
            else: session.add(WeightEntry(weight_kg=weight_kg, recorded_on=recorded_on, notes=notes))

    def progress_data(self, days: int = 30) -> tuple[pd.DataFrame, pd.DataFrame]:
        start = date.today() - timedelta(days=days - 1)
        logs = self.logs(start=start)
        food = pd.DataFrame([{"date": x.log_date, "Calories": x.calories, "Protein (g)": x.protein_g} for x in logs])
        if not food.empty: food = food.groupby("date", as_index=False).sum()
        with get_session() as session: weights = list(session.scalars(select(WeightEntry).where(WeightEntry.recorded_on >= start).order_by(WeightEntry.recorded_on)))
        weight = pd.DataFrame([{"date": x.recorded_on, "Weight (kg)": x.weight_kg} for x in weights])
        return food, weight
