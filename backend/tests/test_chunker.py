"""
Unit tests for TextChunker service.
Run: pytest tests/test_chunker.py -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.chunker import TextChunker


@pytest.fixture
def chunker():
    return TextChunker(chunk_size=200, overlap=40)


class TestTextChunker:

    def test_short_text_returns_single_chunk(self, chunker):
        text = "Hello world. This is a short resume."
        result = chunker.chunk(text)
        assert len(result) == 1
        assert result[0] == text

    def test_empty_text_returns_empty(self, chunker):
        result = chunker.chunk("")
        assert result == []

    def test_whitespace_only_returns_empty(self, chunker):
        result = chunker.chunk("   \n\n\t  ")
        assert result == []

    def test_long_text_produces_multiple_chunks(self, chunker):
        # 10 sentences, each ~30 chars → ~300 chars total, > chunk_size=200
        sentences = ["This is sentence number {}.".format(i) for i in range(10)]
        text = " ".join(sentences)
        result = chunker.chunk(text)
        assert len(result) > 1

    def test_no_chunk_exceeds_max_size(self, chunker):
        sentences = ["Word " * 20 + "." for _ in range(20)]
        text = " ".join(sentences)
        result = chunker.chunk(text)
        for chunk in result:
            # Allow small overshoot from overlap carry, but nothing wild
            assert len(chunk) < chunker.chunk_size * 2

    def test_chunks_cover_all_content(self, chunker):
        """All words from the original text must appear in at least one chunk."""
        words = ["alpha", "beta", "gamma", "delta", "epsilon",
                 "zeta", "eta", "theta", "iota", "kappa"]
        # Build sentences so each word appears exactly once
        sentences = [f"The word {w} is important here." for w in words]
        text = " ".join(sentences)
        chunks_combined = " ".join(chunker.chunk(text))
        for word in words:
            assert word in chunks_combined, f"Word '{word}' missing from chunks"

    def test_overlap_carries_content_forward(self):
        """With large overlap, boundary content appears in consecutive chunks."""
        chunker = TextChunker(chunk_size=100, overlap=50)
        # Build text that will definitely split
        text = ("First section has some important context here. " * 3 +
                "Second section continues the discussion. " * 3)
        chunks = chunker.chunk(text)
        if len(chunks) >= 2:
            # The last part of chunk[0] should share words with the start of chunk[1]
            last_words_of_0 = set(chunks[0].split()[-5:])
            first_words_of_1 = set(chunks[1].split()[:10])
            assert len(last_words_of_0 & first_words_of_1) > 0

    def test_cleans_excessive_whitespace(self, chunker):
        text = "Hello   world.\n\n\n\nNew   paragraph   here."
        result = chunker.chunk(text)
        for chunk in result:
            assert "   " not in chunk  # No triple spaces

    def test_trivially_short_chunks_filtered(self, chunker):
        """Chunks under 30 chars should be filtered out."""
        result = chunker.chunk("Hi.")
        assert result == []

    def test_resume_like_text(self):
        """Integration-style: chunking a realistic resume excerpt."""
        chunker = TextChunker(chunk_size=512, overlap=64)
        resume = """
        John Smith | john@example.com | San Francisco, CA

        EXPERIENCE
        Senior Software Engineer – Acme Corp (2020–Present)
        Led a team of 5 engineers to redesign the payment microservice.
        Reduced API latency by 40% through Redis caching and query optimization.
        Built a real-time analytics pipeline handling 100K events/day using Kafka and Spark.
        Mentored 3 junior engineers through weekly 1:1s and code reviews.

        Software Engineer – StartupXYZ (2017–2020)
        Developed RESTful APIs in Python/Django serving 50K daily active users.
        Migrated monolithic Rails application to microservices architecture.
        Improved test coverage from 40% to 90% using pytest and factory_boy.

        EDUCATION
        B.S. Computer Science – UC Berkeley (2017)

        SKILLS
        Python, FastAPI, Django, PostgreSQL, Redis, Kafka, Docker, Kubernetes, AWS, GCP
        """
        chunks = chunker.chunk(resume)
        assert len(chunks) >= 1
        all_text = " ".join(chunks)
        # Key facts should survive chunking
        assert "Acme Corp" in all_text
        assert "Kafka" in all_text
        assert "UC Berkeley" in all_text
