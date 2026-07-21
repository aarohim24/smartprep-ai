# ── Stage 1: install deps ───────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System libs needed by some Python packages (e.g. faiss, pdfplumber)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Use the production-only requirements.
# fastembed (ONNX Runtime) replaces sentence-transformers (PyTorch).
# This keeps the image well under the 512 MB Render free-tier RAM limit.
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
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL}

# Pre-download the fastembed ONNX model at build time so startup is instant.
# fastembed caches models in ~/.cache/fastembed inside the image layer.
RUN python -c "\
from fastembed import TextEmbedding; \
import os; \
TextEmbedding(model_name=os.environ['EMBEDDING_MODEL'])" || true

EXPOSE 8000

# Render injects PORT. Force a single worker so the model is loaded only once.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
