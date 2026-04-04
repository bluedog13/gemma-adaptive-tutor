"""Exercise generator — uses Gemma 4 to create practice problems."""

import json

import ollama

from src.constants import MODEL
from src.models.schemas import BandInfo, Exercise, ExerciseSet, StudentProgress
from src.prompts import build_exercise_prompt, build_report_prompt


def generate_exercises(
    student_name: str,
    grade: int,
    band: BandInfo,
    num_questions: int = 5,
    weak_concepts: list[str] | None = None,
) -> ExerciseSet:
    """Generate exercises using Gemma 4."""

    # Flatten all concepts from the band
    all_concepts = []
    for topic, concepts in band.topics.items():
        for concept in concepts:
            all_concepts.append(f"{concept} ({topic})")

    prompt = build_exercise_prompt(
        student_name=student_name,
        grade=grade,
        band_name=band.band,
        all_concepts=all_concepts,
        num_questions=num_questions,
        weak_concepts=weak_concepts,
    )

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )

    content = response.message.content.strip()

    # Parse the JSON response
    parsed = json.loads(content)

    # Handle both array and object responses
    if isinstance(parsed, dict):
        exercises_data = parsed.get("exercises", [parsed])
    else:
        exercises_data = parsed

    exercises = []
    for ex in exercises_data:
        # Normalize choices — Gemma sometimes returns nested lists
        raw_choices = ex.get("choices")
        choices = None
        if raw_choices and isinstance(raw_choices, list):
            choices = [str(c[0]) if isinstance(c, list) else str(c) for c in raw_choices]

        exercises.append(
            Exercise(
                concept=ex.get("concept", ""),
                topic=ex.get("topic", ""),
                question=ex.get("question", ""),
                question_type=ex.get("question_type", "word_problem"),
                choices=choices,
                correct_answer=str(ex.get("correct_answer", "")),
                explanation=ex.get("explanation", ""),
            )
        )

    return ExerciseSet(
        student_name=student_name,
        band=band.band,
        exercises=exercises,
    )


def generate_report(progress: StudentProgress) -> str:
    """Generate a teacher/parent report using Gemma 4."""

    prompt = build_report_prompt(
        student_name=progress.student_name,
        grade=progress.grade,
        latest_rit=progress.latest_rit,
        trend=progress.trend.value if progress.trend else "N/A",
        num_sessions=len(progress.sessions),
        mastered_concepts=progress.mastered_concepts,
        needs_work_concepts=progress.needs_work_concepts,
    )

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.message.content.strip()
