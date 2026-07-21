# ── Stage 1: install deps ───────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System libs needed by some Python packages (e.g. faiss, pdfplumber)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Use the production-only requirements (no scipy/matplotlib/pandas/pytest/cross-encoder)
# to keep the image well under the 512 MB Render free-tier limit.
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app source (.env is excluded by .dockerignore — set secrets in Render dashboard)
COPY . .

# Build-time arg so the pre-bake model matches the runtime default exactly.
# Override with --build-arg EMBEDDING_MODEL=... if you switch models.
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL}

# Pre-download the dense embedder at build time so startup is instant.
# The cross-encoder reranker is NOT pre-loaded (ENABLE_RERANKER=false by default)
# to keep container RAM well under the 512 MB Render free-tier limit.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
import os; \
SentenceTransformer(os.environ['EMBEDDING_MODEL'])" || true

EXPOSE 8000

# Render injects PORT. Force a single worker so two model copies never coexist.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
