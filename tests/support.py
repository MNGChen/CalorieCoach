"""Isolated SQLite fixtures. Tests never initialize the user's database."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from sqlalchemy.orm import sessionmaker
import database.database as database
from services.nutrition_service import NutritionService


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="caloriecoach-tests-")
        self.addCleanup(self.directory.cleanup)
        self.engine = database.create_database_engine(f"sqlite:///{Path(self.directory.name) / 'test.db'}")
        self.addCleanup(self.engine.dispose)
        self.patches = [patch.object(database, "engine", self.engine),
                        patch.object(database, "SessionLocal", sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)),
                        patch("ai.openai_client.OPENAI_API_KEY", ""),
                        patch("services.knowledge_base_service.OPENAI_API_KEY", "")]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        database.init_db()

    def profile(self, username="alice"):
        service = NutritionService(username=username)
        profile = service.save_profile(age=30, gender="Female", height_cm=165, weight_kg=60,
                                       activity_level="Lightly Active", goal="Maintenance")
        return service, profile


def resolved_food(**changes):
    item = {"input_food": "egg", "quantity": 1, "unit": "piece", "resolved": True,
            "review_confirmed": True, "source_type": "web", "validation_status": "uncertain",
            "confidence": "low", "sources": [], "matched_food": {"name": "Egg", "serving_size": "1 piece",
            "calories": 75.0, "protein_g": 6.0, "carbs_g": 1.0, "fat_g": 5.0}}
    item.update(changes)
    return item
