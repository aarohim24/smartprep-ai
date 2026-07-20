# SmartPrep AI — Interview Preparation Platform

An end-to-end AI-powered interview coach that generates personalised questions from your resume and job description, evaluates answers in real time, and adapts difficulty dynamically.

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18 + Vite, CSS Modules |
| Backend | FastAPI + Uvicorn |
| LLM | Groq — `llama-3.3-70b-versatile` |
| RAG | FAISS + BM25 + cross-encoder reranking |
| Embeddings | `all-MiniLM-L6-v2` (sentence-transformers) |
| Code Execution | Piston sandbox (10 languages) |
| Spaced Repetition | FSRS algorithm |
| Database | SQLite + Alembic migrations |
| Containerisation | Docker Compose |

## Features

- **3 interview modes** — Behavioral, Coding, System Design
- **3 difficulty tiers** — Easy (5q / 15 min), Mixed (7q / 25 min), Hard (10q / 35 min)
- **4-dimension rubric evaluation** — correctness, completeness, communication, problem-solving
- **Agentic follow-up loop** — escalates, probes, or pivots based on answer quality
- **Voice recording** — record answers via microphone
- **Sandboxed code execution** — auto-injected Python test harnesses with pass/fail signals
- **FSRS spaced-repetition** — tracks weak areas across sessions
- **Session debrief** — per-question breakdown with grade, score, and detailed feedback

## Quick Start

### Prerequisites
- Python 3.9+, Node 18+
- A [Groq API key](https://console.groq.com)

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add your GROQ_API_KEY
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

### Docker (recommended)

```bash
# Add GROQ_API_KEY to backend/.env first
docker compose up --build
```

## Project Structure

```
smartprep-redesign/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers (22 endpoints)
│   │   ├── services/     # LLM, RAG, sandbox, session services
│   │   ├── db/           # SQLAlchemy models + Alembic migrations
│   │   └── models/       # Pydantic schemas
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/   # Shared UI components
│       ├── pages/        # Route-level page components
│       └── services/     # API client
└── docker-compose.yml
```

## Docs

See [`docs/`](docs/) for architecture notes and API reference.
