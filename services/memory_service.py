"""User-scoped short- and long-term memory for the nutrition assistant.

Nutrition logs and profile fields remain the source of truth.  This service stores
only conversational context and explicit preferences/constraints, so it can be
reviewed and removed without touching health or food-log records.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select

from database.database import get_session
from database.models import ConversationMessage, ConversationSession, UserMemory


class MemoryService:
    RECENT_MESSAGE_LIMIT = 8
    SUMMARY_MESSAGE_LIMIT = 12
    MEMORY_LIMIT = 5
    _VALID_CATEGORIES = {"diet_preference", "restriction", "routine", "goal_context", "communication_style"}

    def __init__(self, user_id: int | None, session_id: str, session_factory: object = get_session) -> None:
        self.user_id = user_id if user_id is not None and user_id > 0 else None
        self.session_id = session_id
        self.session_factory = session_factory

    @property
    def enabled(self) -> bool:
        return self.user_id is not None

    def context(self) -> dict[str, Any]:
        """Return a small, prompt-ready context without exposing another user's data."""
        if not self.enabled:
            return {"summary": "", "recent_messages": [], "memories": []}
        with self.session_factory() as session:  # type: ignore[operator]
            summary_row = session.scalar(select(ConversationSession).where(
                ConversationSession.user_id == self.user_id,
                ConversationSession.session_id == self.session_id,
            ))
            messages = list(session.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.user_id == self.user_id,
                    ConversationMessage.session_id == self.session_id,
                ).order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc()).limit(self.RECENT_MESSAGE_LIMIT)
            ))
            memories = list(session.scalars(
                select(UserMemory).where(UserMemory.user_id == self.user_id).order_by(
                    UserMemory.importance.desc(), UserMemory.updated_at.desc(), UserMemory.id.desc()
                )
            ))
            # Restrictions are never evicted by a newer preference.
            restrictions = [item for item in memories if item.category in {"restriction", "diet_preference"}]
            memories = restrictions + [item for item in memories if item not in restrictions][:self.MEMORY_LIMIT]
            now = datetime.utcnow()
            for memory in memories:
                memory.last_used_at = now
            return {
                "summary": summary_row.summary if summary_row else "",
                "recent_messages": [{"role": item.role, "content": item.content} for item in reversed(messages)],
                "memories": [{"id": item.id, "category": item.category, "content": item.content,
                              "confirmed": item.confirmed} for item in memories],
            }

    def record_turn(self, user_message: str, assistant_message: str) -> list[UserMemory]:
        """Persist a turn and promote only clear, durable statements to long-term memory."""
        if not self.enabled:
            return []
        cleaned_user = self._clean_text(user_message)
        cleaned_assistant = self._clean_text(assistant_message)
        if not cleaned_user:
            return []
        with self.session_factory() as session:  # type: ignore[operator]
            session.add_all([
                ConversationMessage(user_id=self.user_id, session_id=self.session_id, role="user", content=cleaned_user),
                ConversationMessage(user_id=self.user_id, session_id=self.session_id, role="assistant", content=cleaned_assistant or "No response."),
            ])
            saved = self._upsert_detected_memories(session, cleaned_user)
            session.flush()
            self._refresh_summary(session)
            return saved

    def list_memories(self) -> list[UserMemory]:
        if not self.enabled:
            return []
        with self.session_factory() as session:  # type: ignore[operator]
            return list(session.scalars(select(UserMemory).where(UserMemory.user_id == self.user_id).order_by(
                UserMemory.category, UserMemory.updated_at.desc()
            )))

    def add_memory(self, category: str, content: str, importance: int = 2, source: str = "manual") -> UserMemory:
        if not self.enabled:
            raise ValueError("Complete a profile before saving assistant memory.")
        if category not in self._VALID_CATEGORIES:
            raise ValueError("Unsupported memory category.")
        cleaned = self._clean_text(content)
        if not cleaned:
            raise ValueError("Memory cannot be empty.")
        with self.session_factory() as session:  # type: ignore[operator]
            return self._upsert_memory(session, category, cleaned, importance, source)

    def delete_memory(self, memory_id: int) -> None:
        if not self.enabled:
            raise ValueError("No active assistant memory.")
        with self.session_factory() as session:  # type: ignore[operator]
            memory = session.get(UserMemory, memory_id)
            if memory is None or memory.user_id != self.user_id:
                raise ValueError("Memory not found.")
            session.delete(memory)

    def confirm_memory(self, memory_id: int) -> None:
        with self.session_factory() as session:
            memory = session.get(UserMemory, memory_id)
            if memory is None or memory.user_id != self.user_id:
                raise ValueError("Memory not found.")
            memory.confirmed = True

    def _refresh_summary(self, session: Any) -> None:
        messages = list(session.scalars(select(ConversationMessage).where(
            ConversationMessage.user_id == self.user_id,
            ConversationMessage.session_id == self.session_id,
        ).order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc()).limit(
            self.RECENT_MESSAGE_LIMIT + self.SUMMARY_MESSAGE_LIMIT)))
        messages.reverse()
        older = messages[:-self.RECENT_MESSAGE_LIMIT]
        if not older:
            return
        selected = older[-self.SUMMARY_MESSAGE_LIMIT:]
        lines = [f"{'User' if item.role == 'user' else 'Assistant'}: {item.content}" for item in selected]
        summary = "Earlier conversation context:\n" + "\n".join(lines)
        summary = summary[:1600]
        row = session.scalar(select(ConversationSession).where(
            ConversationSession.user_id == self.user_id,
            ConversationSession.session_id == self.session_id,
        ))
        if row is None:
            session.add(ConversationSession(user_id=self.user_id, session_id=self.session_id, summary=summary))
        else:
            row.summary = summary

    def _upsert_detected_memories(self, session: Any, message: str) -> list[UserMemory]:
        saved: list[UserMemory] = []
        for category, content, importance in self._detect_memories(message):
            saved.append(self._upsert_memory(session, category, content, importance, "conversation"))
        return saved

    def _upsert_memory(self, session: Any, category: str, content: str, importance: int, source: str) -> UserMemory:
        normalized = self._normalize(content)
        existing = session.scalar(select(UserMemory).where(
            UserMemory.user_id == self.user_id,
            UserMemory.category == category,
            UserMemory.normalized_content == normalized,
        ))
        if existing:
            existing.importance = max(existing.importance, importance)
            existing.source = source
            if source == "manual":
                existing.confirmed = True
            return existing
        memory = UserMemory(user_id=self.user_id, category=category, content=content,
                            normalized_content=normalized, importance=importance, source=source,
                            confirmed=source == "manual" or category not in {"restriction", "diet_preference"})
        session.add(memory)
        session.flush()
        return memory

    @classmethod
    def _detect_memories(cls, message: str) -> list[tuple[str, str, int]]:
        """Use conservative rules: transient wishes stay in the session, not user memory."""
        value = message.strip()
        matches: list[tuple[str, str, int]] = []
        rules = [
            ("restriction", 3, r"(?:记住|以后|今后|always|from now on).{0,25}(?:不吃|不要推荐|avoid|no )\s*([^，。,.!！?？]{1,80})"),
            ("restriction", 3, r"(?:I\s+am|I'm)\s+(?:allergic\s+to|intolerant\s+of)\s+([^，。,.!！?？]{1,80})"),
            ("restriction", 3, r"我\s*(?:对)?\s*([^，。,.!！?？]{1,60})(?:过敏|不耐受)"),
            ("diet_preference", 2, r"(?:我|I)\s*(?:喜欢|偏好|prefer|like)\s*([^，。,.!！?？]{1,80})"),
            ("communication_style", 2, r"(?:回答|回复|answer|response).{0,12}(?:简短|详细|brief|concise|detailed)"),
            ("routine", 2, r"(?:我通常|我一般|I usually)\s*([^，。,.!！?？]{3,100})"),
        ]
        for category, importance, pattern in rules:
            match = re.search(pattern, value, flags=re.IGNORECASE)
            if match:
                content = value if category == "communication_style" else cls._clean_text(match.group(0))
                matches.append((category, content, importance))
        # Remove duplicates from messages that match more than one conservative rule.
        return list(dict.fromkeys(matches))

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())[:500]

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.casefold()).strip()[:500]
