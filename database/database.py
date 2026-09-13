"""SQLAlchemy engine and session helpers."""
from __future__ import annotations

from contextlib import contextmanager, closing
from typing import Generator
from threading import RLock
from weakref import WeakSet
from pathlib import Path
import sqlite3
from datetime import datetime

from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_URL


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def create_database_engine(url: str):
    if not url.startswith("sqlite:"):
        raise ValueError("CalorieCoach currently supports SQLite database URLs only.")
    result = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(result, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return result


engine = create_database_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
_initialized = WeakSet()
_initialization_lock = RLock()


def init_db() -> None:
    """Create application tables when they do not already exist."""
    with _initialization_lock:
        if engine in _initialized:
            return
        _initialize_database()
        _initialized.add(engine)


def _initialize_database() -> None:
    from database import models  # noqa: F401 - registers model metadata

    old_tables = inspect(engine).get_table_names()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)"))
        version = connection.scalar(text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations"))
    if version < 1 and "user_profiles" in old_tables and engine.url.database not in (None, "", ":memory:"):
        path = Path(engine.url.database)
        backup = path.with_name(f"{path.stem}.pre-v1-{datetime.now():%Y%m%d%H%M%S%f}.db")
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as destination:
            source.backup(destination)
    Base.metadata.create_all(bind=engine)
    if version < 1:
        _migrate_food_logs()
        _migrate_user_ownership()
        _migrate_reliability()
    # Keep the bundled food catalogue local and queryable by backend services.
    from database.food_seed import seed_food_database

    with get_session() as session:
        seed_food_database(session)
    with engine.begin() as connection:
        connection.execute(text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (1)"))


def _migrate_food_logs() -> None:
    """Additive SQLite migration for existing local installations without Alembic."""
    required_columns = {
        "meal_id": "VARCHAR(36)", "original_input": "TEXT", "quantity": "FLOAT", "unit": "VARCHAR(20)",
        "source_type": "VARCHAR(30)", "validation_status": "VARCHAR(20)", "confidence": "VARCHAR(20)",
        "confidence_score": "FLOAT", "source_urls": "TEXT", "idempotency_key": "VARCHAR(100)",
        "source_metadata": "TEXT",
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
            for index in inspect(connection).get_indexes("weight_entries_legacy"):
                connection.execute(text('DROP INDEX "' + index["name"].replace('"', '""') + '"'))
            Base.metadata.tables["weight_entries"].create(connection)
            connection.execute(text("INSERT INTO weight_entries (id, user_id, weight_kg, recorded_on, notes) "
                                    "SELECT id, user_id, weight_kg, recorded_on, notes FROM weight_entries_legacy"))
            connection.execute(text("DROP TABLE weight_entries_legacy"))


def _migrate_reliability() -> None:
    additions = {
        "user_memories": {"confirmed": "BOOLEAN NOT NULL DEFAULT 1"},
        "foods": {"source_label": "VARCHAR(200)", "source_version": "VARCHAR(64)",
                  "source_region": "VARCHAR(80)", "source_quality": "VARCHAR(40)", "dietary_tags": "TEXT"},
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
        connection.execute(text("UPDATE user_memories SET confirmed=0 WHERE source='conversation' AND category IN ('restriction', 'diet_preference')"))
        # Add constraints to old SQLite tables without destructive table rebuilds.
        # Existing legacy rows remain intact; every new/changed owner must exist.
        for table in ("food_logs", "weight_entries", "conversation_messages", "conversation_sessions", "user_memories"):
            for operation in ("INSERT", "UPDATE OF user_id"):
                suffix = operation.split()[0].lower()
                connection.execute(text(f"""CREATE TRIGGER IF NOT EXISTS validate_{table}_owner_{suffix}
                    BEFORE {operation} ON {table}
                    WHEN NEW.user_id IS NULL OR NOT EXISTS (SELECT 1 FROM user_profiles WHERE id=NEW.user_id)
                    BEGIN SELECT RAISE(ABORT, 'A valid user owner is required'); END"""))
            connection.execute(text(f"""CREATE TRIGGER IF NOT EXISTS retain_{table}_owner
                BEFORE DELETE ON user_profiles
                WHEN EXISTS (SELECT 1 FROM {table} WHERE user_id=OLD.id)
                BEGIN SELECT RAISE(ABORT, 'User still owns records'); END"""))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_food_logs_user_date ON food_logs(user_id, log_date)"))


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
