"""
SmartPrep AI - Admin / Cohort Analytics API
Read-only views for system health, cost tracking, and cohort performance trends.

Endpoints:
  GET /api/v1/admin/metrics     — Prometheus text format metrics
  GET /api/v1/admin/telemetry   — JSON telemetry summary
  GET /api/v1/admin/cohort      — Cohort performance analytics (from DB)
  GET /api/v1/admin/difficulty  — Question difficulty drift from community pool
"""
import time
from fastapi import APIRouter, Response, HTTPException
from fastapi.responses import PlainTextResponse

from app.utils.telemetry import telemetry
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.get("/admin/metrics", response_class=PlainTextResponse, tags=["Admin"])
async def prometheus_metrics():
    """
    Expose telemetry in Prometheus text exposition format.
    Compatible with any Prometheus scraper or Grafana data source.
    """
    return PlainTextResponse(
        content=telemetry.to_prometheus_text(),
        media_type="text/plain; version=0.0.4",
    )


@router.get("/admin/telemetry", tags=["Admin"])
async def telemetry_summary():
    """
    JSON summary of all in-process metrics:
    - Total requests, errors, error rate
    - Estimated LLM cost (USD)
    - Per-endpoint latency stats
    - Cost per session
    """
    return telemetry.get_summary()


@router.get("/admin/cohort", tags=["Admin"])
async def cohort_analytics(
    mode: str = None,
    tier: str = None,
    limit: int = 100,
):
    """
    Cohort performance analytics from the learner memory DB.
    Returns aggregate stats: avg score per mode/tier, completion rates,
    score distribution, and drop-off points.
    """
    try:
        from app.db.database import AsyncSessionLocal
        from app.db.models import Session as DBSession, QuestionAttempt
        from sqlalchemy import select, func

        async with AsyncSessionLocal() as db:
            # Build base query
            query = select(DBSession)
            if mode:
                query = query.where(DBSession.mode == mode)
            if tier:
                query = query.where(DBSession.tier == tier)
            query = query.order_by(DBSession.created_at.desc()).limit(limit)

            result = await db.execute(query)
            sessions = result.scalars().all()

            if not sessions:
                return {"message": "No session data yet.", "sessions": []}

            # Aggregate stats
            total = len(sessions)
            scores = [s.overall_score for s in sessions if s.overall_score is not None]
            avg_score = round(sum(scores) / len(scores), 2) if scores else None
            completion_rates = [s.completion_rate for s in sessions if s.completion_rate is not None]
            avg_completion = round(sum(completion_rates) / len(completion_rates), 2) if completion_rates else None

            # Score distribution buckets
            dist = {"0-4": 0, "4-6": 0, "6-8": 0, "8-10": 0}
            for s in scores:
                if s < 4:   dist["0-4"] += 1
                elif s < 6: dist["4-6"] += 1
                elif s < 8: dist["6-8"] += 1
                else:        dist["8-10"] += 1

            # By mode breakdown
            by_mode: dict = {}
            for s in sessions:
                key = s.mode or "unknown"
                if key not in by_mode:
                    by_mode[key] = {"count": 0, "scores": [], "completion_rates": []}
                by_mode[key]["count"] += 1
                if s.overall_score is not None:
                    by_mode[key]["scores"].append(s.overall_score)
                if s.completion_rate is not None:
                    by_mode[key]["completion_rates"].append(s.completion_rate)

            mode_stats = [
                {
                    "mode": k,
                    "session_count": v["count"],
                    "avg_score": round(sum(v["scores"]) / len(v["scores"]), 2) if v["scores"] else None,
                    "avg_completion": round(sum(v["completion_rates"]) / len(v["completion_rates"]), 2) if v["completion_rates"] else None,
                }
                for k, v in by_mode.items()
            ]

            # By tier breakdown
            by_tier: dict = {}
            for s in sessions:
                key = s.tier or "unknown"
                if key not in by_tier:
                    by_tier[key] = {"count": 0, "scores": []}
                by_tier[key]["count"] += 1
                if s.overall_score is not None:
                    by_tier[key]["scores"].append(s.overall_score)

            tier_stats = [
                {
                    "tier": k,
                    "session_count": v["count"],
                    "avg_score": round(sum(v["scores"]) / len(v["scores"]), 2) if v["scores"] else None,
                }
                for k, v in by_tier.items()
            ]

            return {
                "generated_at": time.time(),
                "total_sessions": total,
                "avg_score": avg_score,
                "avg_completion_rate": avg_completion,
                "score_distribution": dist,
                "by_mode": mode_stats,
                "by_tier": tier_stats,
            }

    except Exception as e:
        logger.error(f"Cohort analytics failed: {e}", exc_info=True)
        raise HTTPException(500, f"Analytics unavailable: {str(e)}")


@router.get("/admin/difficulty-drift", tags=["Admin"])
async def difficulty_drift():
    """
    Reports difficulty drift for community questions based on Elo rating vs.
    stated difficulty. Useful for surfacing mis-tagged questions.
    """
    try:
        from app.api.community import _question_pool

        questions = [q for q in _question_pool.values() if q.approved and q.attempt_count > 0]
        if not questions:
            return {"message": "No attempted community questions yet.", "drift": []}

        drift = []
        for q in questions:
            # Elo ~1000 = "Medium" baseline; >1100 = harder than stated, <900 = easier
            elo_category = (
                "harder_than_stated" if q.elo_difficulty > 1100 else
                "easier_than_stated" if q.elo_difficulty < 900 else
                "accurate"
            )
            drift.append({
                "id": q.id,
                "question": q.question[:80] + "..." if len(q.question) > 80 else q.question,
                "stated_difficulty": q.difficulty,
                "elo_rating": q.elo_difficulty,
                "elo_category": elo_category,
                "attempt_count": q.attempt_count,
                "avg_score": q.avg_score,
            })

        drift.sort(key=lambda x: abs(x["elo_rating"] - 1000), reverse=True)
        return {"total": len(drift), "drift": drift}

    except Exception as e:
        logger.error(f"Difficulty drift analysis failed: {e}", exc_info=True)
        raise HTTPException(500, "Difficulty drift analysis unavailable.")


@router.get("/admin/export/sessions", tags=["Admin"])
async def export_sessions(format: str = "json", limit: int = 500):
    """
    Export session data as JSON or CSV for offline analysis.
    """
    try:
        from app.db.database import AsyncSessionLocal
        from app.db.models import Session as DBSession
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            query = select(DBSession).order_by(DBSession.created_at.desc()).limit(limit)
            result = await db.execute(query)
            sessions = result.scalars().all()

        data = [
            {
                "session_id": s.id,
                "candidate_id": s.candidate_id,
                "mode": s.mode,
                "tier": s.tier,
                "overall_score": s.overall_score,
                "avg_correctness": s.avg_correctness,
                "avg_completeness": s.avg_completeness,
                "avg_communication": s.avg_communication,
                "avg_problem_solving": s.avg_problem_solving,
                "completion_rate": s.completion_rate,
                "time_used_seconds": s.time_used_seconds,
                "created_at": s.created_at,
            }
            for s in sessions
        ]

        if format == "csv":
            if not data:
                return PlainTextResponse("No data", media_type="text/csv")
            import io, csv
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return PlainTextResponse(
                content=buf.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=sessions.csv"}
            )

        return {"total": len(data), "sessions": data}

    except Exception as e:
        logger.error(f"Session export failed: {e}", exc_info=True)
        raise HTTPException(500, "Export unavailable.")
