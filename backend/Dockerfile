# ── Stage 1: install deps ───────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System libs needed by some Python packages (e.g. faiss, pdfplumber)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app source
COPY . .

# Pre-download the sentence-transformer model at build time
# so the first request isn't slow and cold starts don't fail
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')" || true

EXPOSE 8000

# Use PORT env var (Render injects it) with 8000 as fallback
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
