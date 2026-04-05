"""Exercise generator — uses Gemma 4 to create practice problems."""

import json
import logging

import ollama

from src.constants import MODEL
from src.models.schemas import BandInfo, Exercise, ExerciseSet, StudentProgress
from src.prompts import build_exercise_prompt, build_report_prompt

logger = logging.getLogger("map_accelerator")


_REQUIRED_FIELDS_BY_TYPE: dict[str, list[str]] = {
    "multi_select": ["num_correct", "correct_answers"],
    "two_part": ["part_b_question", "part_b_choices", "part_b_correct"],
    "sequence_order": ["items_to_order", "correct_order"],
    "table_matching": ["match_pairs", "match_options"],
}

_SCENARIO_REQUIRED_SUBJECTS = {"reading", "science"}


def _validate_exercises(
    exercises: list[Exercise],
    num_questions: int,
    subject: str,
    topics: dict[str, list[str]] | None = None,
) -> list[str]:
    """Validate parsed exercises against prompt contract.

    :param exercises: Parsed exercise list.
    :param num_questions: Expected number of exercises.
    :param subject: Subject (used to check scenario requirement).
    :param topics: Allowed topic-to-concepts mapping from the band. When
        provided, concept and topic values are checked against this set.
    :return: List of validation error messages (empty if valid).
    """
    errors: list[str] = []

    if len(exercises) != num_questions:
        errors.append(
            f"Expected {num_questions} exercises, got {len(exercises)}"
        )

    # Build allowed sets for semantic validation (case-insensitive)
    allowed_topics: set[str] | None = None
    allowed_concepts: set[str] | None = None
    if topics:
        allowed_topics = {t.lower() for t in topics}
        allowed_concepts = {
            c.lower() for concepts in topics.values() for c in concepts
        }

    for i, ex in enumerate(exercises):
        prefix = f"Exercise {i + 1}"

        # Required base fields must be non-empty
        if not ex.concept.strip():
            errors.append(f"{prefix}: missing concept")
        if not ex.question.strip():
            errors.append(f"{prefix}: missing question")
        if not ex.correct_answer.strip():
            errors.append(f"{prefix}: missing correct_answer")

        # Semantic: concept and topic must match the supplied band
        if allowed_topics is not None and ex.topic.strip():
            if ex.topic.strip().lower() not in allowed_topics:
                errors.append(
                    f"{prefix}: topic '{ex.topic}' not in allowed topics"
                )
        if allowed_concepts is not None and ex.concept.strip():
            if ex.concept.strip().lower() not in allowed_concepts:
                errors.append(
                    f"{prefix}: concept '{ex.concept}' not in allowed concepts"
                )

        # Scenario required for reading and science
        if subject in _SCENARIO_REQUIRED_SUBJECTS and not ex.scenario:
            errors.append(f"{prefix}: missing scenario (required for {subject})")

        # Type-specific required fields
        required = _REQUIRED_FIELDS_BY_TYPE.get(ex.question_type, [])
        for field in required:
            if getattr(ex, field, None) is None:
                errors.append(
                    f"{prefix} ({ex.question_type}): missing {field}"
                )

        # MC-style types need choices
        if ex.question_type in ("multiple_choice", "multi_select", "two_part"):
            if not ex.choices:
                errors.append(f"{prefix} ({ex.question_type}): missing choices")

    return errors


def _normalize_list(raw: list | None) -> list[str] | None:
    """Normalize a list field from Gemma — flatten nested lists, stringify."""
    if not raw or not isinstance(raw, list):
        return None
    return [str(c[0]) if isinstance(c, list) else str(c) for c in raw]


def generate_exercises(
    student_name: str,
    grade: int,
    band: BandInfo,
    num_questions: int = 5,
    weak_concepts: list[str] | None = None,
    subject: str = "math",
) -> ExerciseSet:
    """Generate exercises using Gemma 4."""

    prompt = build_exercise_prompt(
        student_name=student_name,
        grade=grade,
        band_name=band.band,
        topics=band.topics,
        num_questions=num_questions,
        weak_concepts=weak_concepts,
        subject=subject,
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
        choices = _normalize_list(raw_choices)

        # Normalize other list fields
        part_b_choices = _normalize_list(ex.get("part_b_choices"))
        correct_answers = _normalize_list(ex.get("correct_answers"))
        items_to_order = _normalize_list(ex.get("items_to_order"))
        correct_order = _normalize_list(ex.get("correct_order"))

        # Normalize match fields
        match_pairs = ex.get("match_pairs")
        if match_pairs and not isinstance(match_pairs, dict):
            match_pairs = None
        match_options = _normalize_list(ex.get("match_options"))

        exercises.append(
            Exercise(
                concept=ex.get("concept", ""),
                topic=ex.get("topic", ""),
                question=ex.get("question", ""),
                question_type=ex.get("question_type", "multiple_choice"),
                choices=choices,
                correct_answer=str(ex.get("correct_answer", "")),
                explanation=ex.get("explanation", ""),
                scenario=ex.get("scenario"),
                num_correct=ex.get("num_correct"),
                correct_answers=correct_answers,
                part_b_question=ex.get("part_b_question"),
                part_b_choices=part_b_choices,
                part_b_correct=(
                    str(ex["part_b_correct"]) if ex.get("part_b_correct") else None
                ),
                items_to_order=items_to_order,
                correct_order=correct_order,
                match_pairs=match_pairs,
                match_options=match_options,
            )
        )

    # Validate exercises against prompt contract
    validation_errors = _validate_exercises(
        exercises, num_questions, subject, topics=band.topics
    )
    if validation_errors:
        logger.warning(
            "Exercise validation issues: %s", "; ".join(validation_errors)
        )
        raise ValueError(
            f"Generated exercises failed validation: {'; '.join(validation_errors)}"
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
        subject=progress.subject,
    )

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.message.content.strip()
