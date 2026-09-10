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
