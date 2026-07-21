"""
SmartPrep AI — centralised configuration.

All settings are read from environment variables (or a .env file in development).
In production set these as env vars in your hosting dashboard (Railway / Render / Fly.io).
"""
from __future__ import annotations

from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── LLM (Groq) ───────────────────────────────────────────────────────────
    GROQ_API_KEY: str = "your-groq-api-key-here"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ── Embeddings ───────────────────────────────────────────────────────────────
    # Uses fastembed (ONNX Runtime) — no PyTorch, ~80 MB RAM.
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # ── Storage ──────────────────────────────────────────────────────────────
    VECTOR_STORE_PATH: str = "./vector_store"
    DATABASE_URL: str = "sqlite+aiosqlite:///./smartprep.db"

    # ── Server ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    # ── Memory optimisation ───────────────────────────────────────────────────
    # Set to true only if your instance has >1 GB RAM; cross-encoder adds ~200 MB.
    ENABLE_RERANKER: bool = False

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins, or "*" for open access.
    # Example: "https://smartprep.up.railway.app,https://my-frontend.vercel.app"
    ALLOWED_ORIGINS_STR: str = "*"

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """Parse the comma-separated ALLOWED_ORIGINS_STR into a list."""
        raw = self.ALLOWED_ORIGINS_STR.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return upper


# Singleton — import this everywhere
settings = Settings()
