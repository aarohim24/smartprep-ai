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

# Copy app source
COPY . .

# Pre-download only the dense embedder (all-MiniLM-L6-v2, ~90 MB).
# The cross-encoder reranker is NOT pre-loaded here; it is off by default
# (ENABLE_RERANKER=false) to keep startup RAM under 300 MB.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')" || true

EXPOSE 8000

# Render injects PORT. Force a single worker so two model copies never coexist.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
