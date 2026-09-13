"""SQLAlchemy data models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), nullable=False, index=True)
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
    source_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    log_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)


class MealSubmission(Base):
    """One reservation per user submission; guarantees idempotency across concurrent writers."""
    __tablename__ = "meal_submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100))
    meal_id: Mapped[str] = mapped_column(String(36))
    payload_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("user_id", "request_id", name="uq_meal_submission_request"),)


class WeightEntry(Base):
    __tablename__ = "weight_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), nullable=False, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    recorded_on: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_weight_entries_user_recorded_on", "user_id", "recorded_on", unique=True),)


class ConversationMessage(Base):
    """A user-scoped assistant message used for the short-term context window."""

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (Index("ix_conversation_messages_user_session_created", "user_id", "session_id", "created_at"),)


class ConversationSession(Base):
    """A bounded summary of messages that no longer fit in the short-term window."""

    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserMemory(Base):
    """Explicit, durable preferences and constraints for one user workspace."""

    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    content: Mapped[str] = mapped_column(Text)
    normalized_content: Mapped[str] = mapped_column(String(500))
    importance: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(30), default="conversation")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "category", "normalized_content", name="uq_user_memory_content"),)


class KnowledgeSource(Base):
    """Public, reviewable nutrition source used by the shared RAG knowledge base."""

    __tablename__ = "knowledge_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    publisher: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80), index=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeChunk(Base):
    """A citable chunk. Vectors are JSON so the local app needs no vector-database server."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("source_id", "ordinal", name="uq_knowledge_chunk_ordinal"),)


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
    source_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_region: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    source_quality: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    dietary_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    calories: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
