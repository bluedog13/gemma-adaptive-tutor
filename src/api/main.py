"""FastAPI application for MAP Accelerator."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from src.constants import SEASON_ORDER
from src.models.database import (
    ExerciseResultRecord,
    PracticeSession,
    Score,
    Student,
    get_db,
    init_db,
)
from src.models.schemas import (
    AnswerInput,
    CurriculumResult,
    ScoreInput,
    SessionSummary,
    StudentInput,
    StudentProgress,
    Subject,
)
from src.tools.curriculum import map_rit_to_curriculum
from src.tools.exercise_generator import generate_exercises, generate_report
from src.tools.student_progress import get_weak_concepts, grade_for_score


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="MAP Accelerator",
    description="Gemma 4-powered adaptive tutor for advanced students",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Student & Score endpoints ---


@app.post("/students", response_model=dict)
def create_student(student_input: StudentInput, db: Session = Depends(get_db)):
    """Register a student and their MAP scores.

    If a student with the same name exists, returns an error directing the
    caller to use ``POST /students/{id}/scores`` instead.
    """
    existing = db.query(Student).filter(Student.name == student_input.name).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Student '{student_input.name}' already exists "
            f"(id={existing.id}). Use POST /students/{existing.id}/scores "
            "to add scores.",
        )

    student = Student(name=student_input.name, grade=student_input.grade)
    db.add(student)
    db.flush()

    added = _upsert_scores(db, student.id, student_input.scores, student_input.grade)

    db.commit()
    db.refresh(student)
    return {
        "student_id": student.id,
        "name": student.name,
        "scores_added": added,
    }


@app.post("/students/{student_id}/scores", response_model=dict)
def add_scores(
    student_id: int,
    scores: list[ScoreInput],
    db: Session = Depends(get_db),
):
    """Add or replace scores for an existing student.

    Scores are deduped on ``(student_id, subject, season, year)``.
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    added = _upsert_scores(db, student_id, scores, student.grade)
    db.commit()
    return {"student_id": student_id, "scores_added": added}


@app.delete("/students/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db)):
    """Delete a student and all related records (scores, sessions, results, analyses).

    :param student_id: ID of the student to delete.
    :return: Confirmation message.
    :raises HTTPException: 404 if student not found.
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    db.delete(student)
    db.commit()
    return {"message": f"Student '{student.name}' deleted"}


def _upsert_scores(
    db: Session,
    student_id: int,
    scores: list[ScoreInput],
    current_grade: int | None = None,
) -> int:
    """Insert scores, replacing any existing row with the same natural key.

    Uses SQLite ``INSERT ... ON CONFLICT ... DO UPDATE`` for atomicity.
    Computes per-score grade-at-test from ``current_grade`` and the latest
    score's season/year, so historical scores get the correct grade.

    :param current_grade: Student's current grade level.
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    if not scores:
        return 0

    # Determine latest score to compute grade offsets
    latest = max(scores, key=lambda s: (s.year, SEASON_ORDER.get(s.season, 0)))

    added = 0
    for score_input in scores:
        score_grade = None
        if current_grade is not None:
            score_grade = grade_for_score(
                score_input.season,
                score_input.year,
                current_grade,
                latest.season,
                latest.year,
            )
        stmt = sqlite_insert(Score).values(
            student_id=student_id,
            rit_score=score_input.rit_score,
            season=score_input.season,
            year=score_input.year,
            subject=score_input.subject,
            grade=score_grade,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["student_id", "subject", "season", "year"],
            set_={
                "rit_score": stmt.excluded.rit_score,
                "grade": stmt.excluded.grade,
            },
        )
        db.execute(stmt)
        added += 1
    return added


# --- Curriculum endpoints ---


@app.get("/curriculum/{student_id}", response_model=CurriculumResult)
def get_curriculum(
    student_id: int, subject: Subject = Subject.MATH, db: Session = Depends(get_db)
):
    """Get the Develop/Introduce bands for a student's latest score."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    scores = (
        db.query(Score)
        .filter(
            Score.student_id == student_id,
            Score.subject == subject,
        )
        .all()
    )
    if not scores:
        raise HTTPException(status_code=404, detail="No scores found for student")

    # Use the latest score
    latest = max(scores, key=lambda s: (s.year, SEASON_ORDER[s.season]))

    score_inputs = [
        ScoreInput(rit_score=s.rit_score, season=s.season, year=s.year) for s in scores
    ]

    return map_rit_to_curriculum(
        latest.rit_score, score_inputs, grade=student.grade, subject=subject
    )


# --- Exercise endpoints ---


@app.post("/exercises/{student_id}")
def create_exercises(
    student_id: int,
    num_questions: int = 5,
    subject: Subject = Subject.MATH,
    db: Session = Depends(get_db),
):
    """Generate exercises for a student based on their Introduce band."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Get curriculum mapping
    curriculum = get_curriculum(student_id, subject, db)

    # Check past sessions for weak concepts
    weak_concepts = get_weak_concepts(student_id, db, subject)

    exercises = generate_exercises(
        student_name=student.name,
        grade=student.grade,
        band=curriculum.introduce_band,
        num_questions=num_questions,
        weak_concepts=weak_concepts,
        subject=subject,
    )

    # Create a practice session record
    session = PracticeSession(
        student_id=student_id,
        band=curriculum.introduce_band.band,
        total_questions=len(exercises.exercises),
        subject=subject,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {"session_id": session.id, **exercises.model_dump()}


@app.post("/exercises/{student_id}/answer")
def submit_answer(
    student_id: int, session_id: int, answer: AnswerInput, db: Session = Depends(get_db)
):
    """Submit an answer for an exercise in a session."""
    session = (
        db.query(PracticeSession)
        .filter(
            PracticeSession.id == session_id,
            PracticeSession.student_id == student_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"received": True, "session_id": session_id}


# --- Session & Progress endpoints ---


@app.post("/sessions/{session_id}/complete", response_model=SessionSummary)
def complete_session(
    session_id: int, results: list[AnswerInput], db: Session = Depends(get_db)
):
    """Complete a practice session with all answers."""
    session = db.query(PracticeSession).filter(PracticeSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    student = db.query(Student).filter(Student.id == session.student_id).first()

    correct = 0
    concept_scores: dict[str, dict[str, int]] = {}
    records_added = 0

    if session.results:
        for record in session.results:
            concept_bucket = concept_scores.setdefault(
                record.concept, {"correct": 0, "total": 0}
            )
            concept_bucket["total"] += 1
            if record.is_correct:
                concept_bucket["correct"] += 1
                correct += 1
    else:
        for result in results:
            concept = result.concept or f"exercise_{result.exercise_index + 1}"
            normalized_answer = result.student_answer.strip()
            is_correct = bool(result.is_correct)
            concept_bucket = concept_scores.setdefault(
                concept, {"correct": 0, "total": 0}
            )
            concept_bucket["total"] += 1
            if is_correct:
                concept_bucket["correct"] += 1
                correct += 1
            db.add(
                ExerciseResultRecord(
                    session_id=session.id,
                    concept=concept,
                    topic=result.topic or "unknown",
                    question=result.question or f"Exercise {result.exercise_index + 1}",
                    student_answer=normalized_answer,
                    correct_answer=result.correct_answer or "",
                    is_correct=is_correct,
                )
            )
            records_added += 1

    total_questions = len(results) if results else len(session.results) + records_added
    score_pct = (correct / total_questions * 100) if total_questions > 0 else 0.0

    session.completed_at = datetime.now(timezone.utc)
    session.total_questions = total_questions
    session.correct = correct
    session.score_pct = score_pct
    session.concept_scores = concept_scores
    db.commit()

    return SessionSummary(
        session_id=session.id,
        student_name=student.name,
        band=session.band,
        total_questions=session.total_questions,
        correct=session.correct,
        score_pct=session.score_pct,
        concept_scores=session.concept_scores or {},
        timestamp=session.started_at,
        subject=session.subject,
    )


@app.get("/progress/{student_id}", response_model=StudentProgress)
def get_progress(
    student_id: int, subject: Subject = Subject.MATH, db: Session = Depends(get_db)
):
    """Get a student's overall progress across all sessions."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    scores = (
        db.query(Score)
        .filter(
            Score.student_id == student_id,
            Score.subject == subject,
        )
        .all()
    )
    if not scores:
        raise HTTPException(status_code=404, detail="No scores found")

    latest_score = max(scores, key=lambda s: (s.year, SEASON_ORDER[s.season]))

    score_inputs = [
        ScoreInput(rit_score=s.rit_score, season=s.season, year=s.year) for s in scores
    ]
    from src.tools.curriculum import detect_trend

    trend, _ = detect_trend(score_inputs, grade=student.grade, subject=subject)

    sessions = (
        db.query(PracticeSession)
        .filter(
            PracticeSession.student_id == student_id,
            PracticeSession.subject == subject,
            PracticeSession.completed_at.isnot(None),
        )
        .all()
    )

    # Aggregate concept mastery across sessions
    concept_totals: dict[str, dict] = {}
    for s in sessions:
        for concept, data in (s.concept_scores or {}).items():
            if concept not in concept_totals:
                concept_totals[concept] = {"correct": 0, "total": 0}
            concept_totals[concept]["correct"] += data.get("correct", 0)
            concept_totals[concept]["total"] += data.get("total", 0)

    mastered = []
    needs_work = []
    for concept, data in concept_totals.items():
        if data["total"] > 0:
            pct = data["correct"] / data["total"]
            if pct >= 0.8:
                mastered.append(concept)
            else:
                needs_work.append(concept)

    # Sort sessions chronologically before building summaries
    sessions = sorted(sessions, key=lambda s: s.completed_at or s.started_at)

    session_summaries = [
        SessionSummary(
            session_id=s.id,
            student_name=student.name,
            band=s.band,
            total_questions=s.total_questions,
            correct=s.correct,
            score_pct=s.score_pct,
            concept_scores=s.concept_scores or {},
            timestamp=s.completed_at or s.started_at,
            subject=s.subject,
        )
        for s in sessions
    ]

    return StudentProgress(
        student_name=student.name,
        grade=student.grade,
        latest_rit=latest_score.rit_score,
        trend=trend,
        sessions=session_summaries,
        mastered_concepts=mastered,
        needs_work_concepts=needs_work,
        subject=subject,
    )


@app.get("/report/{student_id}")
def get_report(
    student_id: int, subject: Subject = Subject.MATH, db: Session = Depends(get_db)
):
    """Generate a teacher/parent report for a student."""
    progress = get_progress(student_id, subject, db)
    report_text = generate_report(progress)
    return {
        "student_name": progress.student_name,
        "report": report_text,
        "subject": subject,
    }
