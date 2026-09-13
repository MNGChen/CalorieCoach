from pathlib import Path
from contextlib import closing
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import sessionmaker
import database.database as database
from database.models import FoodLog, WeightEntry, UserProfile


class MigrationTests(unittest.TestCase):
    def test_single_user_upgrade_preserves_data_and_is_repeatable(self):
        with TemporaryDirectory(prefix="caloriecoach-migration-") as directory:
            path = Path(directory) / "old.db"
            with closing(sqlite3.connect(path)) as connection:
                connection.executescript("""
                    CREATE TABLE user_profiles (id INTEGER PRIMARY KEY, age INTEGER, gender TEXT, height_cm FLOAT,
                        weight_kg FLOAT, activity_level TEXT, goal TEXT, created_at DATETIME, updated_at DATETIME);
                    INSERT INTO user_profiles VALUES (1,30,'Female',165,60,'Sedentary','Maintenance',NULL,NULL);
                    CREATE TABLE food_logs (id INTEGER PRIMARY KEY, meal_type TEXT, food_name TEXT, calories FLOAT,
                        protein_g FLOAT, carbs_g FLOAT, fat_g FLOAT, notes TEXT, logged_at DATETIME, log_date DATE);
                    INSERT INTO food_logs VALUES (5,'Lunch','Original meal',450,20,50,15,'Keep me',NULL,'2026-09-10');
                    CREATE TABLE weight_entries (id INTEGER PRIMARY KEY, weight_kg FLOAT, recorded_on DATE UNIQUE, notes TEXT);
                    CREATE INDEX ix_weight_entries_recorded_on ON weight_entries(recorded_on);
                    INSERT INTO weight_entries VALUES (9,60,'2026-09-10','Original weight');
                """)
            engine = database.create_database_engine(f"sqlite:///{path}")
            sessions = sessionmaker(bind=engine, expire_on_commit=False)
            try:
                with patch.object(database, "engine", engine), patch.object(database, "SessionLocal", sessions):
                    database.init_db()
                    database._initialized.discard(engine)
                    database.init_db()
                    with database.get_session() as session:
                        self.assertEqual(session.get(UserProfile, 1).username, "legacy")
                        log = session.get(FoodLog, 5)
                        self.assertEqual((log.user_id, log.calories, log.notes), (1, 450, "Keep me"))
                        self.assertEqual(session.get(WeightEntry, 9).user_id, 1)
                        self.assertEqual(session.scalar(text("SELECT MAX(version) FROM schema_migrations")), 1)
                    self.assertEqual(len(list(Path(directory).glob("*.pre-v1-*.db"))), 1)
            finally:
                engine.dispose()
