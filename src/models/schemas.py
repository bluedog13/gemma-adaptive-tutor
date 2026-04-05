"""Pydantic schemas for MAP Accelerator."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TestSeason(str, Enum):
    FALL = "fall"
    WINTER = "winter"
    SPRING = "spring"


class Subject(str, Enum):
    MATH = "math"
    READING = "reading"
    SCIENCE = "science"


SUBJECT_DISPLAY: dict[str, str] = {
    "math": "Math",
    "reading": "Language Arts: Reading",
    "science": "Science",
}


class Trend(str, Enum):
    GROWING = "growing"
    STALLING = "stalling"
    DECLINING = "declining"


# --- Input schemas ---


class ScoreInput(BaseModel):
    rit_score: int = Field(..., ge=100, le=350, description="MAP RIT score")
    season: TestSeason
    year: int = Field(..., ge=2020, le=2030, description="School year (e.g. 2026)")
    subject: Subject = Field(
        default=Subject.MATH, description="Subject (math, reading, science)"
    )


class StudentInput(BaseModel):
    name: str
    grade: int = Field(..., ge=2, le=5, description="Current grade level (2-5)")
    scores: list[ScoreInput] = Field(
        ..., min_length=1, description="MAP scores (one or more)"
    )


# --- Curriculum schemas ---


class BandInfo(BaseModel):
    band: str  # e.g. "191-200"
    building_on_prior: list[str] = []
    topics: dict[str, list[str]] = {}  # topic name -> list of concepts
    additional_learning_continuum_topics: list[str] = []


class CurriculumResult(BaseModel):
    rit_score: int
    develop_band: BandInfo
    introduce_band: BandInfo
    trend: Trend | None = None
    trend_detail: str | None = None
    subject: str = "math"


# --- Exercise schemas ---


class Exercise(BaseModel):
    concept: str
    topic: str
    question: str
    question_type: str  # "word_problem", "multiple_choice", "fill_in_the_blank"
    choices: list[str] | None = None  # for multiple choice
    correct_answer: str
    explanation: str
    difficulty: str = "introduce"  # reinforce, develop, introduce


class ExerciseSet(BaseModel):
    student_name: str
    band: str
    exercises: list[Exercise]


# --- Session & Progress schemas ---


class AnswerInput(BaseModel):
    exercise_index: int
    student_answer: str
    concept: str | None = None
    topic: str | None = None
    question: str | None = None
    correct_answer: str | None = None
    is_correct: bool | None = None


class ExerciseResult(BaseModel):
    concept: str
    topic: str
    question: str
    student_answer: str
    correct_answer: str
    is_correct: bool


class SessionSummary(BaseModel):
    session_id: int
    student_name: str
    band: str
    total_questions: int
    correct: int
    score_pct: float
    concept_scores: dict[str, dict]  # concept -> {"correct": n, "total": n}
    timestamp: datetime
    subject: str = "math"


class StudentProgress(BaseModel):
    student_name: str
    grade: int
    latest_rit: int
    trend: Trend | None
    sessions: list[SessionSummary]
    mastered_concepts: list[str]  # >= 80% correct
    needs_work_concepts: list[str]  # < 80% correct
    subject: str = "math"
