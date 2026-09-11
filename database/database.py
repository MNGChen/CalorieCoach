"""SQLAlchemy engine and session helpers."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_URL


class Base(DeclarativeBase):
    """Base class for all ORM models."""


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Create application tables when they do not already exist."""
    from database import models  # noqa: F401 - registers model metadata

    Base.metadata.create_all(bind=engine)
    _migrate_food_logs()
    _migrate_user_ownership()
    # Keep the bundled food catalogue local and queryable by backend services.
    from database.food_seed import seed_food_database

    with get_session() as session:
        seed_food_database(session)


def _migrate_food_logs() -> None:
    """Additive SQLite migration for existing local installations without Alembic."""
    required_columns = {
        "meal_id": "VARCHAR(36)", "original_input": "TEXT", "quantity": "FLOAT", "unit": "VARCHAR(20)",
        "source_type": "VARCHAR(30)", "validation_status": "VARCHAR(20)", "confidence": "VARCHAR(20)",
        "confidence_score": "FLOAT", "source_urls": "TEXT", "idempotency_key": "VARCHAR(100)",
    }
    existing = {column["name"] for column in inspect(engine).get_columns("food_logs")}
    with engine.begin() as connection:
        for name, definition in required_columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE food_logs ADD COLUMN {name} {definition}"))
    required_profile_columns = {
        "custom_calorie_goal": "FLOAT", "custom_protein_goal_g": "FLOAT",
        "custom_carbs_goal_g": "FLOAT", "custom_fat_goal_g": "FLOAT",
        "health_notice_acknowledged": "BOOLEAN DEFAULT 0",
    }
    existing_profile = {column["name"] for column in inspect(engine).get_columns("user_profiles")}
    with engine.begin() as connection:
        for name, definition in required_profile_columns.items():
            if name not in existing_profile:
                connection.execute(text(f"ALTER TABLE user_profiles ADD COLUMN {name} {definition}"))


def _migrate_user_ownership() -> None:
    """Preserve the original local profile while introducing per-profile data ownership."""
    with engine.begin() as connection:
        profile_columns = {column["name"] for column in inspect(engine).get_columns("user_profiles")}
        if "username" not in profile_columns:
            connection.execute(text("ALTER TABLE user_profiles ADD COLUMN username VARCHAR(40)"))
            connection.execute(text("UPDATE user_profiles SET username = 'legacy' "
                                    "WHERE id = (SELECT MIN(id) FROM user_profiles WHERE username IS NULL)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_user_profiles_username "
                                "ON user_profiles(username)"))
        for table in ("food_logs", "weight_entries"):
            columns = {column["name"] for column in inspect(engine).get_columns(table)}
            if "user_id" not in columns:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))
        # The existing one-person data becomes the legacy profile's data.
        connection.execute(text("UPDATE food_logs SET user_id = (SELECT id FROM user_profiles WHERE username = 'legacy' LIMIT 1) WHERE user_id IS NULL"))
        connection.execute(text("UPDATE weight_entries SET user_id = (SELECT id FROM user_profiles WHERE username = 'legacy' LIMIT 1) WHERE user_id IS NULL"))
    unique_constraints = inspect(engine).get_unique_constraints("weight_entries")
    old_global_unique = any(set(item.get("column_names") or []) == {"recorded_on"} for item in unique_constraints)
    if old_global_unique:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE weight_entries RENAME TO weight_entries_legacy"))
            Base.metadata.tables["weight_entries"].create(connection)
            connection.execute(text("INSERT INTO weight_entries (id, user_id, weight_kg, recorded_on, notes) "
                                    "SELECT id, user_id, weight_kg, recorded_on, notes FROM weight_entries_legacy"))
            connection.execute(text("DROP TABLE weight_entries_legacy"))


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional session with safe rollback on failure."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
