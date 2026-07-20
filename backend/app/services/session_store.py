"""
SmartPrep AI — In-memory async session store with TTL-based cleanup.

Sessions are keyed by UUID and expire after SESSION_TTL_SECONDS of inactivity.
For production persistence swap _store for Redis; the interface stays identical.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Sessions expire after 2 hours of inactivity (can be overridden by env var)
SESSION_TTL_SECONDS: int = 2 * 60 * 60
CLEANUP_INTERVAL_SECONDS: int = 10 * 60  # run cleanup every 10 minutes


class _Session:
    """Thin wrapper that tracks last-access time for TTL enforcement."""

    __slots__ = ("data", "last_access")

    def __init__(self, data: Dict[str, Any]) -> None:
        self.data: Dict[str, Any] = dict(data)
        self.last_access: float = time.monotonic()

    def touch(self) -> None:
        self.last_access = time.monotonic()

    def is_expired(self, ttl: int = SESSION_TTL_SECONDS) -> bool:
        return (time.monotonic() - self.last_access) > ttl


class SessionStore:
    """
    Thread-safe (asyncio-friendly) in-memory session store.

    Public API
    ----------
    await create(session_id, data)   → None
    await get(session_id)            → dict | None
    await update(session_id, data)   → None
    await delete(session_id)         → None
    start_cleanup_task()             → None   (call on app startup)
    stop_cleanup_task()              → None   (call on app shutdown)
    """

    def __init__(self) -> None:
        self._store: Dict[str, _Session] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    # ── Public interface ──────────────────────────────────────────────────────

    async def create(self, session_id: str, data: Dict[str, Any]) -> None:
        """Create a new session. Overwrites silently if session_id already exists."""
        async with self._lock:
            self._store[session_id] = _Session(data)
        logger.debug(f"Session created: {session_id}")

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return session data dict or None if not found / expired."""
        async with self._lock:
            session = self._store.get(session_id)
            if session is None:
                return None
            if session.is_expired():
                del self._store[session_id]
                logger.debug(f"Session expired on access: {session_id}")
                return None
            session.touch()
            return dict(session.data)

    async def update(self, session_id: str, data: Dict[str, Any]) -> None:
        """Merge *data* into an existing session. Creates the session if absent."""
        async with self._lock:
            session = self._store.get(session_id)
            if session is None:
                self._store[session_id] = _Session(data)
                logger.debug(f"Session auto-created on update: {session_id}")
            else:
                session.data.update(data)
                session.touch()

    async def delete(self, session_id: str) -> None:
        """Remove a session explicitly."""
        async with self._lock:
            self._store.pop(session_id, None)
        logger.debug(f"Session deleted: {session_id}")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start_cleanup_task(self) -> None:
        """Schedule background TTL cleanup. Call once from app lifespan startup."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Session cleanup task started")

    def stop_cleanup_task(self) -> None:
        """Cancel background cleanup. Call from app lifespan shutdown."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("Session cleanup task stopped")

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
                await self._purge_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Session cleanup error (non-fatal): {e}")

    async def _purge_expired(self) -> None:
        async with self._lock:
            expired = [sid for sid, s in self._store.items() if s.is_expired()]
            for sid in expired:
                del self._store[sid]
        if expired:
            logger.info(f"Session cleanup: purged {len(expired)} expired session(s)")


# Singleton — import this everywhere
session_store = SessionStore()
