"""Shared helpers for student score and practice progress calculations."""

from sqlalchemy.orm import Session

from src.models.database import PracticeSession


def grade_for_score(
    season: str, year: int, current_grade: int, latest_season: str, latest_year: int
) -> int:
    """Compute the student's grade at the time of a given score."""

    def school_year_start(s: str, y: int) -> int:
        season_value = str(getattr(s, "value", s))
        if season_value == "spring":
            return y - 1
        return y

    latest_sy = school_year_start(latest_season, latest_year)
    score_sy = school_year_start(season, year)
    return max(0, current_grade - (latest_sy - score_sy))


def get_weak_concepts(
    student_id: int, db: Session, subject: str = "math", threshold: float = 0.8
) -> list[str]:
    """Find concepts where the student scored below the mastery threshold."""
    subject_value = str(getattr(subject, "value", subject))
    sessions = (
        db.query(PracticeSession)
        .filter(
            PracticeSession.student_id == student_id,
            PracticeSession.subject == subject_value,
            PracticeSession.completed_at.isnot(None),
        )
        .all()
    )

    concept_totals: dict[str, dict[str, int]] = {}
    for session in sessions:
        for concept, data in (session.concept_scores or {}).items():
            concept_bucket = concept_totals.setdefault(
                concept, {"correct": 0, "total": 0}
            )
            concept_bucket["correct"] += data.get("correct", 0)
            concept_bucket["total"] += data.get("total", 0)

    return [
        concept
        for concept, data in concept_totals.items()
        if data["total"] > 0 and data["correct"] / data["total"] < threshold
    ]
