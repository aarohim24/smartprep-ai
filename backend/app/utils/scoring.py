"""
SmartPrep AI — Scoring utilities.

Central place for grade conversions so every endpoint uses the same scale.
"""
from __future__ import annotations


def score_to_grade(score: float) -> str:
    """
    Convert a numeric score (0–10) to a letter grade.

    Scale
    -----
    9.0 – 10.0  →  A+
    8.0 –  8.9  →  A
    7.0 –  7.9  →  B+
    6.0 –  6.9  →  B
    5.0 –  5.9  →  C
    4.0 –  4.9  →  D
    0.0 –  3.9  →  F
    """
    s = max(0.0, min(10.0, float(score)))
    if s >= 9.0:
        return "A+"
    if s >= 8.0:
        return "A"
    if s >= 7.0:
        return "B+"
    if s >= 6.0:
        return "B"
    if s >= 5.0:
        return "C"
    if s >= 4.0:
        return "D"
    return "F"


def grade_to_color(grade: str) -> str:
    """Return a CSS-friendly colour token for a grade (used by telemetry / reports)."""
    return {
        "A+": "#22c55e",
        "A":  "#4ade80",
        "B+": "#86efac",
        "B":  "#facc15",
        "C":  "#fb923c",
        "D":  "#f87171",
        "F":  "#ef4444",
    }.get(grade, "#94a3b8")
