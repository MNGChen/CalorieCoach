from __future__ import annotations

import unittest

from services.knowledge_base_service import KnowledgeBaseService


class KnowledgeBaseTests(unittest.TestCase):
    def test_chunking_preserves_overlap(self) -> None:
        text = "a" * (KnowledgeBaseService.CHUNK_SIZE + 100)
        chunks = KnowledgeBaseService._split(text)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), KnowledgeBaseService.CHUNK_SIZE)
        self.assertGreater(len(chunks[1]), KnowledgeBaseService.CHUNK_OVERLAP)

    def test_lexical_retrieval_scores_matching_terms(self) -> None:
        score = KnowledgeBaseService._lexical_score("protein meal", "A protein-rich meal can be practical.")
        self.assertGreater(score, 0)
        self.assertEqual(KnowledgeBaseService._lexical_score("protein", "vegetables and fruit"), 0)

    def test_cosine_is_safe_for_invalid_vectors(self) -> None:
        self.assertEqual(KnowledgeBaseService._cosine([1.0], [1.0, 2.0]), 0.0)
        self.assertAlmostEqual(KnowledgeBaseService._cosine([1.0, 0.0], [1.0, 0.0]), 1.0)


if __name__ == "__main__":
    unittest.main()
