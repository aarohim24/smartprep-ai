"""
SmartPrep AI - ORM Models for learner memory persistence.
Tables: Candidate, Session, QuestionAttempt, SkillNode, FSRSCard
"""
import time
from sqlalchemy import (
    Column, Integer, Float, String, Text, Boolean,
    ForeignKey, BigInteger,
)
from sqlalchemy.orm import relationship
from app.db.database import Base


class Candidate(Base):
    """Represents a unique learner (identified by client-generated UUID)."""
    __tablename__ = "candidates"

    id = Column(String, primary_key=True)            # client UUID
    created_at = Column(Float, default=time.time)
    sessions = relationship("Session", back_populates="candidate")
    skill_nodes = relationship("SkillNode", back_populates="candidate")


class Session(Base):
    """One mock interview session."""
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)            # session_id from resume upload
    candidate_id = Column(String, ForeignKey("candidates.id"), nullable=True)
    mode = Column(String, default="behavioral")      # coding | system_design | behavioral
    tier = Column(String, default="mixed")           # easy | mixed | hard
    overall_score = Column(Float, nullable=True)
    avg_correctness = Column(Float, nullable=True)
    avg_completeness = Column(Float, nullable=True)
    avg_communication = Column(Float, nullable=True)
    avg_problem_solving = Column(Float, nullable=True)
    completion_rate = Column(Float, nullable=True)
    time_used_seconds = Column(Integer, nullable=True)
    created_at = Column(Float, default=time.time)

    candidate = relationship("Candidate", back_populates="sessions")
    attempts = relationship("QuestionAttempt", back_populates="session")


class QuestionAttempt(Base):
    """One answered question within a session."""
    __tablename__ = "question_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    candidate_id = Column(String, ForeignKey("candidates.id"), nullable=True)
    question_text = Column(Text)
    category = Column(String)
    difficulty = Column(String)
    score = Column(Float)
    correctness = Column(Float, nullable=True)
    completeness = Column(Float, nullable=True)
    communication = Column(Float, nullable=True)
    problem_solving = Column(Float, nullable=True)
    low_confidence = Column(Boolean, default=False)
    created_at = Column(Float, default=time.time)

    session = relationship("Session", back_populates="attempts")


class SkillNode(Base):
    """Weighted skill node in a candidate's weakness graph."""
    __tablename__ = "skill_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String, ForeignKey("candidates.id"))
    skill = Column(String)                           # e.g., "System Design", "Behavioral"
    dimension = Column(String)                       # correctness | completeness | communication | problem_solving
    avg_score = Column(Float, default=5.0)
    sample_count = Column(Integer, default=0)
    last_updated = Column(Float, default=time.time)

    candidate = relationship("Candidate", back_populates="skill_nodes")


class FSRSCard(Base):
    """
    FSRS (Free Spaced Repetition Scheduler) card for a weak question.
    Implements a simplified FSRS-4.5 model with due-date scheduling.
    """
    __tablename__ = "fsrs_cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String, ForeignKey("candidates.id"))
    question_text = Column(Text)
    category = Column(String)
    difficulty = Column(String)

    # FSRS state
    stability = Column(Float, default=1.0)     # retention half-life in days
    difficulty_fsrs = Column(Float, default=5.0)  # FSRS card difficulty (1–10)
    reps = Column(Integer, default=0)          # total repetitions
    lapses = Column(Integer, default=0)        # number of times forgotten
    last_score = Column(Float, nullable=True)
    due_at = Column(Float, default=time.time)  # Unix timestamp when due
    last_reviewed = Column(Float, nullable=True)
    created_at = Column(Float, default=time.time)
