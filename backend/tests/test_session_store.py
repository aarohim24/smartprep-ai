"""
Unit tests for SessionStore service.
Run: pytest tests/test_session_store.py -v
"""
import pytest
import asyncio
import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.session_store import SessionStore


@pytest.fixture
def store():
    return SessionStore()


class TestSessionStore:

    @pytest.mark.asyncio
    async def test_create_and_get(self, store):
        await store.create("s1", {"resume_text": "hello", "skills": ["Python"]})
        result = await store.get("s1")
        assert result is not None
        assert result["resume_text"] == "hello"
        assert result["skills"] == ["Python"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store):
        result = await store.get("does-not-exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_merges_data(self, store):
        await store.create("s1", {"resume_text": "hello"})
        await store.update("s1", {"job_description": "engineer role"})
        result = await store.get("s1")
        assert result["resume_text"] == "hello"
        assert result["job_description"] == "engineer role"

    @pytest.mark.asyncio
    async def test_update_nonexistent_session_is_noop(self, store):
        # Should not raise
        await store.update("no-such-session", {"key": "value"})

    @pytest.mark.asyncio
    async def test_delete_removes_session(self, store):
        await store.create("s1", {"data": "x"})
        await store.delete("s1")
        result = await store.get("s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_existing(self, store):
        await store.create("s1", {})
        assert await store.exists("s1") is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_missing(self, store):
        assert await store.exists("nope") is False

    @pytest.mark.asyncio
    async def test_last_accessed_updates_on_get(self, store):
        await store.create("s1", {})
        before = (await store.get("s1"))["_last_accessed"]
        await asyncio.sleep(0.01)
        after = (await store.get("s1"))["_last_accessed"]
        assert after >= before

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired_sessions(self, store):
        store.SESSION_TTL = 0  # Expire immediately
        await store.create("s1", {})
        await store.create("s2", {})
        time.sleep(0.01)
        await store.cleanup_expired()
        assert await store.get("s1") is None
        assert await store.get("s2") is None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_fresh_sessions(self, store):
        store.SESSION_TTL = 3600
        await store.create("s1", {})
        await store.cleanup_expired()
        assert await store.get("s1") is not None

    @pytest.mark.asyncio
    async def test_concurrent_creates_are_safe(self, store):
        """Multiple concurrent creates should not cause race conditions."""
        await asyncio.gather(*[
            store.create(f"session-{i}", {"i": i})
            for i in range(50)
        ])
        results = await asyncio.gather(*[
            store.get(f"session-{i}")
            for i in range(50)
        ])
        for i, r in enumerate(results):
            assert r is not None
            assert r["i"] == i
