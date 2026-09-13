"""A small, citable nutrition RAG knowledge base backed by SQLite.

The source catalogue contains only public health organisations. Refreshing is explicit
so launching the local app never silently downloads web content.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import hashlib
import json
import logging
import math
import re
from typing import Any

import requests
from sqlalchemy import delete, select

from config import OPENAI_API_KEY, OPENAI_EMBEDDING_MODEL, REQUEST_TIMEOUT_SECONDS
from database.database import get_session
from database.models import KnowledgeChunk, KnowledgeSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthoritativeSource:
    title: str
    url: str
    publisher: str
    category: str
    refreshable: bool = True


AUTHORITATIVE_SOURCES = (
    AuthoritativeSource("Healthy diet", "https://www.who.int/news-room/fact-sheets/detail/healthy-diet", "World Health Organization", "healthy eating"),
    AuthoritativeSource("What are healthy diets?", "https://www.who.int/publications/b/76012", "WHO / FAO", "healthy eating"),
    AuthoritativeSource("Sodium reduction", "https://www.who.int/westernpacific/newsroom/fact-sheets/detail/sodium-reduction", "World Health Organization", "sodium"),
    AuthoritativeSource("Balanced diet and My Healthy Plate", "https://www.healthhub.sg/well-being-and-lifestyle/food-diet-and-nutrition/healthy-balanced-diet-plan", "Singapore Health Promotion Board", "singapore healthy eating"),
    AuthoritativeSource("Dietary Guidelines for Adult Singaporeans", "https://www.healthhub.sg/well-being-and-lifestyle/food-diet-and-nutrition/dietary_guidelines_adults", "Singapore Health Promotion Board", "singapore dietary guidelines"),
    AuthoritativeSource("Understanding Food and Nutrition Labels", "https://www.sfa.gov.sg/food-safety-tips/food-risk-concerns/understanding-food-nutrition-labels-before-purchase", "Singapore Food Agency", "nutrition labels"),
)

# Available immediately and traceable to the original webpages. A manual refresh
# replaces these short starter passages with current webpage text.
STARTER_CONTENT = {
    AUTHORITATIVE_SOURCES[0].url: "Healthy diets are based on adequacy, balance, moderation and diversity. Prefer varied minimally processed foods, including vegetables, fruit, pulses, whole grains and lean protein sources. Limit free sugars, sodium, saturated fat and trans fat. Individual needs vary by age, health, activity, culture and local foods.",
    AUTHORITATIVE_SOURCES[1].url: "Healthy diets support health, growth and active lives. Their exact composition varies with individual needs and local context, while the underlying principles of a varied, balanced and safe diet remain consistent.",
    AUTHORITATIVE_SOURCES[2].url: "Excess sodium is associated with raised blood pressure. Processed foods, salty snacks and condiments can be important sources. Adults are generally advised to keep sodium below 2000 milligrams per day, equivalent to less than 5 grams of salt; individual clinical advice can differ.",
    AUTHORITATIVE_SOURCES[3].url: "Singapore's My Healthy Plate uses a Quarter, Quarter, Half guide: a quarter plate of wholegrains, a quarter plate of protein foods, and half a plate of fruit and vegetables. Choose water and options lower in saturated fat, sodium and added sugar where practical.",
    AUTHORITATIVE_SOURCES[4].url: "Singapore dietary guidance encourages variety across food groups, fruit and vegetables, wholegrains, and choices lower in saturated fat, salt and added sugar. Recommendations should be adapted to individual needs and health conditions.",
    AUTHORITATIVE_SOURCES[5].url: "Singapore Nutrition Information Panels show energy and the amounts of protein, carbohydrate and fat. Compare products using the same basis, such as per 100 grams, and account for the serving size when estimating intake.",
}


class _ReadableText(HTMLParser):
    """Extract readable body text without storing scripts, navigation, or styles."""
    def __init__(self) -> None:
        super().__init__(); self.parts: list[str] = []; self._ignore = 0; self._capture = 0
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer", "header"}: self._ignore += 1
        elif tag in {"p", "li", "h1", "h2", "h3"} and not self._ignore: self._capture += 1
    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer", "header"} and self._ignore: self._ignore -= 1
        elif tag in {"p", "li", "h1", "h2", "h3"} and self._capture: self._capture -= 1; self.parts.append("\n")
    def handle_data(self, data: str) -> None:
        if self._capture and not self._ignore: self.parts.append(data)
    def text(self) -> str: return re.sub(r"\n{2,}", "\n", re.sub(r"[ \t]+", " ", "".join(self.parts))).strip()


class KnowledgeBaseService:
    """Ingest, embed, and retrieve public nutrition guidance with source citations."""
    CHUNK_SIZE = 900
    CHUNK_OVERLAP = 160

    def ensure_seeded(self) -> int:
        """Create a small curated starter set; no network request is made here."""
        try:
            with get_session() as session:
                added = 0
                for source in AUTHORITATIVE_SOURCES:
                    existing = session.scalar(select(KnowledgeSource).where(KnowledgeSource.url == source.url))
                    if existing is not None:
                        continue
                    row = KnowledgeSource(title=source.title, url=source.url, publisher=source.publisher, category=source.category)
                    session.add(row); session.flush()
                    self._replace_chunks(session, row, STARTER_CONTENT[source.url], [])
                    added += 1
                return added
        except Exception:
            logger.warning("Knowledge-base starter content could not be initialised.", exc_info=True)
            return 0

    def refresh_authoritative_sources(self) -> dict[str, int]:
        """Fetch current content from the curated public sources and re-index changes."""
        result = {"updated": 0, "unchanged": 0, "failed": 0, "skipped": 0}
        for source in AUTHORITATIVE_SOURCES:
            if not source.refreshable:
                result["skipped"] += 1
                continue
            try:
                response = requests.get(source.url, timeout=REQUEST_TIMEOUT_SECONDS,
                                        headers={"User-Agent": "CalorieCoach/1.0 (+local nutrition RAG)"})
                response.raise_for_status()
                parser = _ReadableText(); parser.feed(response.text)
                content = parser.text()
                if len(content) < 250:
                    raise ValueError("The source did not provide enough readable text.")
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                with get_session() as session:
                    previous = session.scalar(select(KnowledgeSource).where(KnowledgeSource.url == source.url))
                    previous_chunks = list(session.scalars(select(KnowledgeChunk).where(
                        KnowledgeChunk.source_id == previous.id))) if previous else []
                    needs_vectors = bool(OPENAI_API_KEY and (not previous_chunks or any(
                        not chunk.embedding or chunk.embedding_model != OPENAI_EMBEDDING_MODEL for chunk in previous_chunks)))
                    if previous and previous.content_hash == digest and not needs_vectors:
                        result["unchanged"] += 1
                        continue
                # Network work happens before opening a write transaction.
                vectors = self._embed(self._split(content))
                with get_session() as session:
                    row = session.scalar(select(KnowledgeSource).where(KnowledgeSource.url == source.url))
                    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if row and row.content_hash == digest and not needs_vectors:
                        result["unchanged"] += 1; continue
                    if row is None:
                        row = KnowledgeSource(title=source.title, url=source.url, publisher=source.publisher, category=source.category)
                        session.add(row); session.flush()
                    row.title, row.publisher, row.category = source.title, source.publisher, source.category
                    row.content_hash, row.fetched_at = digest, datetime.utcnow()
                    self._replace_chunks(session, row, content, vectors)
                    result["updated"] += 1
            except Exception:
                logger.warning("Could not refresh knowledge source %s", source.url, exc_info=True)
                result["failed"] += 1
        return result

    def retrieve(self, question: str, limit: int = 4) -> list[dict[str, Any]]:
        if not question.strip(): return []
        self.ensure_seeded()
        try:
            with get_session() as session:
                rows = list(session.execute(select(KnowledgeChunk, KnowledgeSource).join(KnowledgeSource, KnowledgeChunk.source_id == KnowledgeSource.id)).all())
        except Exception:
            logger.warning("Knowledge-base retrieval failed.", exc_info=True); return []
        # Do not pay for a query vector when this corpus has no compatible vectors.
        has_vectors = any(chunk.embedding and chunk.embedding_model == OPENAI_EMBEDDING_MODEL for chunk, _ in rows)
        vectors = self._embed([question]) if OPENAI_API_KEY and has_vectors else []
        query_vector = vectors[0] if vectors else None
        scored: list[tuple[float, KnowledgeChunk, KnowledgeSource]] = []
        for chunk, source in rows:
            # Rank in one score space; mixing lexical and cosine scores is misleading.
            score = (self._cosine(query_vector, self._load_vector(chunk.embedding))
                     if query_vector and chunk.embedding_model == OPENAI_EMBEDDING_MODEL
                     else (0.0 if query_vector else self._lexical_score(question, chunk.content)))
            if score > 0: scored.append((score, chunk, source))
        scored.sort(key=lambda item: item[0], reverse=True)
        # Several adjacent chunks can be relevant, but repeating the same link
        # gives the user the false impression that there are multiple sources.
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for score, chunk, source in scored:
            if source.url in seen_urls:
                continue
            seen_urls.add(source.url)
            results.append({"title": source.title, "url": source.url, "publisher": source.publisher,
                            "category": source.category, "excerpt": chunk.content[:1000], "score": round(score, 3)})
            if len(results) == limit:
                break
        return results

    def stats(self) -> dict[str, int]:
        self.ensure_seeded()
        try:
            with get_session() as session:
                return {"sources": int(session.query(KnowledgeSource).count()), "chunks": int(session.query(KnowledgeChunk).count())}
        except Exception: return {"sources": 0, "chunks": 0}

    def _replace_chunks(self, session: Any, source: KnowledgeSource, content: str,
                        vectors: list[list[float]]) -> None:
        session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.source_id == source.id))
        chunks = self._split(content)
        for ordinal, chunk in enumerate(chunks):
            vector = vectors[ordinal] if ordinal < len(vectors) else None
            session.add(KnowledgeChunk(source_id=source.id, ordinal=ordinal, content=chunk,
                                       embedding=json.dumps(vector) if vector else None,
                                       embedding_model=OPENAI_EMBEDDING_MODEL if vector else None))

    @classmethod
    def _split(cls, content: str) -> list[str]:
        clean = re.sub(r"\s+", " ", content).strip()
        return [clean[start:start + cls.CHUNK_SIZE] for start in range(0, len(clean), cls.CHUNK_SIZE - cls.CHUNK_OVERLAP) if clean[start:start + cls.CHUNK_SIZE]]

    @staticmethod
    def _embed(texts: list[str]) -> list[list[float]]:
        if not OPENAI_API_KEY or not texts: return []
        try:
            from openai import OpenAI
            response = OpenAI(api_key=OPENAI_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=1).embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=texts)
            return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        except Exception:
            logger.warning("Embedding request failed; using lexical retrieval.", exc_info=True); return []

    @staticmethod
    def _lexical_score(question: str, content: str) -> float:
        terms = set(re.findall(r"[\w]+", question.casefold()))
        words = re.findall(r"[\w]+", content.casefold())
        if not terms or not words: return 0.0
        return sum(words.count(term) for term in terms) / math.sqrt(len(words))

    @staticmethod
    def _load_vector(value: str | None) -> list[float] | None:
        try: return json.loads(value) if value else None
        except json.JSONDecodeError: return None

    @staticmethod
    def _cosine(left: list[float] | None, right: list[float] | None) -> float:
        if not left or not right or len(left) != len(right): return 0.0
        denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
        return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0
