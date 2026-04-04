"""FastAPI application for MAP Accelerator."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from src.constants import SEASON_ORDER
from src.models.database import ExerciseResultRecord, PracticeSession, Score, Student, get_db, init_db
from src.models.schemas import (
    AnswerInput,
    CurriculumResult,
    ExerciseSet,
    ScoreInput,
    SessionSummary,
    StudentInput,
    StudentProgress,
    Trend,
)
from src.tools.curriculum import map_rit_to_curriculum
from src.tools.exercise_generator import generate_exercises, generate_report


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
    """Register a student and their MAP scores."""
    student = Student(name=student_input.name, grade=student_input.grade)
    db.add(student)
    db.flush()

    for score_input in student_input.scores:
        score = Score(
            student_id=student.id,
            rit_score=score_input.rit_score,
            season=score_input.season,
            year=score_input.year,
        )
        db.add(score)

    db.commit()
    db.refresh(student)
    return {"student_id": student.id, "name": student.name, "scores_added": len(student_input.scores)}


# --- Curriculum endpoints ---


@app.get("/curriculum/{student_id}", response_model=CurriculumResult)
def get_curriculum(student_id: int, db: Session = Depends(get_db)):
    """Get the Develop/Introduce bands for a student's latest score."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    scores = db.query(Score).filter(Score.student_id == student_id).all()
    if not scores:
        raise HTTPException(status_code=404, detail="No scores found for student")

    # Use the latest score
    latest = max(scores, key=lambda s: (s.year, SEASON_ORDER[s.season]))

    score_inputs = [ScoreInput(rit_score=s.rit_score, season=s.season, year=s.year) for s in scores]

    return map_rit_to_curriculum(latest.rit_score, score_inputs)


# --- Exercise endpoints ---


@app.post("/exercises/{student_id}")
def create_exercises(student_id: int, num_questions: int = 5, db: Session = Depends(get_db)):
    """Generate exercises for a student based on their Introduce band."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Get curriculum mapping
    curriculum = get_curriculum(student_id, db)

    # Check past sessions for weak concepts
    weak_concepts = _get_weak_concepts(student_id, db)

    exercises = generate_exercises(
        student_name=student.name,
        grade=student.grade,
        band=curriculum.introduce_band,
        num_questions=num_questions,
        weak_concepts=weak_concepts,
    )

    # Create a practice session record
    session = PracticeSession(
        student_id=student_id,
        band=curriculum.introduce_band.band,
        total_questions=len(exercises.exercises),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {"session_id": session.id, **exercises.model_dump()}


@app.post("/exercises/{student_id}/answer")
def submit_answer(student_id: int, session_id: int, answer: AnswerInput, db: Session = Depends(get_db)):
    """Submit an answer for an exercise in a session."""
    session = db.query(PracticeSession).filter(
        PracticeSession.id == session_id,
        PracticeSession.student_id == student_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"received": True, "session_id": session_id}


# --- Session & Progress endpoints ---


@app.post("/sessions/{session_id}/complete", response_model=SessionSummary)
def complete_session(session_id: int, results: list[AnswerInput], db: Session = Depends(get_db)):
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
            concept_bucket = concept_scores.setdefault(record.concept, {"correct": 0, "total": 0})
            concept_bucket["total"] += 1
            if record.is_correct:
                concept_bucket["correct"] += 1
                correct += 1
    else:
        for result in results:
            concept = result.concept or f"exercise_{result.exercise_index + 1}"
            normalized_answer = result.student_answer.strip()
            is_correct = bool(result.is_correct)
            concept_bucket = concept_scores.setdefault(concept, {"correct": 0, "total": 0})
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
    )


@app.get("/progress/{student_id}", response_model=StudentProgress)
def get_progress(student_id: int, db: Session = Depends(get_db)):
    """Get a student's overall progress across all sessions."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    scores = db.query(Score).filter(Score.student_id == student_id).all()
    latest_score = max(scores, key=lambda s: (s.year, SEASON_ORDER[s.season]))

    score_inputs = [ScoreInput(rit_score=s.rit_score, season=s.season, year=s.year) for s in scores]
    from src.tools.curriculum import detect_trend
    trend, _ = detect_trend(score_inputs)

    sessions = db.query(PracticeSession).filter(
        PracticeSession.student_id == student_id,
        PracticeSession.completed_at.isnot(None),
    ).all()

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

    session_summaries = [
        SessionSummary(
            session_id=s.id,
            student_name=student.name,
            band=s.band,
            total_questions=s.total_questions,
            correct=s.correct,
            score_pct=s.score_pct,
            concept_scores=s.concept_scores or {},
            timestamp=s.started_at,
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
    )


@app.get("/report/{student_id}")
def get_report(student_id: int, db: Session = Depends(get_db)):
    """Generate a teacher/parent report for a student."""
    progress = get_progress(student_id, db)
    report_text = generate_report(progress)
    return {"student_name": progress.student_name, "report": report_text}


def _get_weak_concepts(student_id: int, db: Session) -> list[str]:
    """Find concepts where the student scored < 80% in past sessions."""
    sessions = db.query(PracticeSession).filter(
        PracticeSession.student_id == student_id,
        PracticeSession.completed_at.isnot(None),
    ).all()

    concept_totals: dict[str, dict] = {}
    for s in sessions:
        for concept, data in (s.concept_scores or {}).items():
            if concept not in concept_totals:
                concept_totals[concept] = {"correct": 0, "total": 0}
            concept_totals[concept]["correct"] += data.get("correct", 0)
            concept_totals[concept]["total"] += data.get("total", 0)

    return [
        concept
        for concept, data in concept_totals.items()
        if data["total"] > 0 and data["correct"] / data["total"] < 0.8
    ]
