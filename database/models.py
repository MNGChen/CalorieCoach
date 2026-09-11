"""SQLAlchemy data models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, unique=True, index=True)
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(20))
    height_cm: Mapped[float] = mapped_column(Float)
    weight_kg: Mapped[float] = mapped_column(Float)
    activity_level: Mapped[str] = mapped_column(String(30))
    goal: Mapped[str] = mapped_column(String(30))
    # Null means the evidence-based calculator remains the source of the target.
    custom_calorie_goal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_protein_goal_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_carbs_goal_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_fat_goal_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    health_notice_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FoodLog(Base):
    __tablename__ = "food_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    meal_type: Mapped[str] = mapped_column(String(20), default="Snack")
    meal_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    original_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    food_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    calories: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    validation_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_urls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    log_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)


class WeightEntry(Base):
    __tablename__ = "weight_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    recorded_on: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_weight_entries_user_recorded_on", "user_id", "recorded_on", unique=True),)


class Food(Base):
    """A locally-seeded food record; nutrition is for one typical serving."""

    __tablename__ = "foods"

    # The workbook's stable ``No.`` value is retained as the public food id.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    normalized_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    serving_quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    serving_unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    calories: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
