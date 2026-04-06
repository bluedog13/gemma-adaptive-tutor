"""SQLite database models and setup."""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Boolean,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    grade = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    scores = relationship(
        "Score", back_populates="student", cascade="all, delete-orphan"
    )
    sessions = relationship(
        "PracticeSession", back_populates="student", cascade="all, delete-orphan"
    )
    analysis = relationship(
        "StudentAnalysis",
        back_populates="student",
        uselist=True,
        cascade="all, delete-orphan",
    )


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("student_id", "subject", "season", "year"),)

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    rit_score = Column(Integer, nullable=False)
    season = Column(String, nullable=False)  # fall, winter, spring
    year = Column(Integer, nullable=False)
    grade = Column(Integer, nullable=True)  # grade at time of test
    subject = Column(String, nullable=False, default="math")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    student = relationship("Student", back_populates="scores")


class PracticeSession(Base):
    __tablename__ = "practice_sessions"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    band = Column(String, nullable=False)  # e.g. "191-200"
    subject = Column(String, nullable=False, default="math")
    total_questions = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    score_pct = Column(Float, default=0.0)
    concept_scores = Column(
        JSON, default=dict
    )  # {"capacity": {"correct": 2, "total": 3}}
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    student = relationship("Student", back_populates="sessions")
    results = relationship(
        "ExerciseResultRecord", back_populates="session", cascade="all, delete-orphan"
    )


class ExerciseResultRecord(Base):
    __tablename__ = "exercise_results"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("practice_sessions.id"), nullable=False)
    concept = Column(String, nullable=False)
    topic = Column(String, nullable=False)
    question = Column(String, nullable=False)
    student_answer = Column(String, nullable=False)
    correct_answer = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("PracticeSession", back_populates="results")


class StudentAnalysis(Base):
    __tablename__ = "student_analyses"
    __table_args__ = (
        UniqueConstraint("student_id", "subject", name="uq_student_subject"),
    )

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    subject = Column(String, nullable=False, default="math")
    trend = Column(String, nullable=True)
    trend_detail = Column(String, nullable=True)
    develop_band = Column(String, nullable=False)
    develop_band_json = Column(JSON, nullable=False)
    introduce_band = Column(String, nullable=False)
    introduce_band_json = Column(JSON, nullable=False)
    latest_rit = Column(Integer, nullable=False)
    scores_hash = Column(String, nullable=False)
    grade = Column(Integer, nullable=False)
    analyzed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    student = relationship("Student", back_populates="analysis")


def compute_scores_hash(scores: list[dict], grade: int) -> str:
    """Compute SHA-256 hash of scores + grade for cache invalidation.

    :param scores: List of dicts with rit_score, season, year, grade keys.
    :param grade: Current student grade.
    :return: Hex digest string.
    """
    tuples = sorted(
        (s["rit_score"], s["season"], s["year"], s.get("grade", grade)) for s in scores
    )
    payload = f"{tuples}|{grade}"
    return hashlib.sha256(payload.encode()).hexdigest()


# Database setup

DATABASE_URL = "sqlite:///map_accelerator.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create tables and verify schema is up-to-date.

    SQLAlchemy's ``create_all`` only creates missing tables — it will NOT add
    new columns to existing tables.  We check for the ``subject`` column and
    advise the user to run ``just reset-db`` if it is missing.
    """
    import sqlite3

    Base.metadata.create_all(engine)

    # Verify the 'subject' column exists on all tables that require it.
    conn = sqlite3.connect(DATABASE_URL.replace("sqlite:///", ""))
    try:
        for table in ("scores", "practice_sessions", "student_analyses"):
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in cursor.fetchall()}
            if "subject" not in columns:
                raise RuntimeError(
                    f"Database schema is outdated — the 'subject' column is missing "
                    f"from '{table}'. Run `just reset-db` to recreate the database."
                )
    finally:
        conn.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
