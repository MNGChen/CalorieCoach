from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.database import Base
from services.memory_service import MemoryService


class MemoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)
        self.memory = MemoryService(user_id=7, session_id="test-session", session_factory=self._session)

    def _session(self):
        from contextlib import contextmanager

        @contextmanager
        def session_scope():
            session = self.sessions()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        return session_scope()

    def test_records_short_term_messages_and_a_durable_preference(self) -> None:
        saved = self.memory.record_turn("I prefer quick dairy-free dinners.", "I can help with that.")
        context = self.memory.context()
        self.assertEqual(len(context["recent_messages"]), 2)
        self.assertEqual(saved[0].category, "diet_preference")
        self.assertIn("prefer quick", context["memories"][0]["content"])

    def test_keeps_users_isolated(self) -> None:
        self.memory.add_memory("restriction", "Do not recommend peanuts.")
        another = MemoryService(user_id=8, session_id="test-session", session_factory=self._session)
        self.assertEqual(another.context()["memories"], [])

    def test_builds_summary_after_short_term_window_is_full(self) -> None:
        for number in range(5):
            self.memory.record_turn(f"Message {number}", f"Response {number}")
        context = self.memory.context()
        self.assertEqual(len(context["recent_messages"]), 8)
        self.assertIn("Message 0", context["summary"])

    def test_manual_memory_can_be_deleted(self) -> None:
        stored = self.memory.add_memory("routine", "I usually eat dinner after 8 pm.")
        self.memory.delete_memory(stored.id)
        self.assertEqual(self.memory.list_memories(), [])


if __name__ == "__main__":
    unittest.main()
