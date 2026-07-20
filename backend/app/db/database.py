"""
SmartPrep AI - Async SQLAlchemy database setup.
Uses SQLite by default; swap DATABASE_URL env var for Postgres/MySQL.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.utils.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

DATABASE_URL = getattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///./smartprep.db")


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Create all tables. Call from app startup."""
    from app.db import models  # noqa: F401 — registers ORM models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized (SQLite)")


async def get_db():
    """FastAPI dependency for async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
