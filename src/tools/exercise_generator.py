"""Exercise generator — uses Gemma 4 to create practice problems."""

import json
import logging
import random

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


_VALID_QUESTION_TYPES = {
    "multiple_choice",
    "multi_select",
    "fill_in_the_blank",
    "two_part",
    "sequence_order",
    "table_matching",
}


def _generate_distractors(correct: str) -> list[str]:
    """Generate 3 plausible distractors + the correct answer as choices.

    Uses simple heuristics: if the answer looks numeric, vary the number.
    Otherwise, create generic wrong-answer labels.

    :param correct: The correct answer string.
    :return: List of 4 choices with the correct answer at a random position.
    """
    distractors: list[str] = []

    # Try numeric distractors
    try:
        num = float(correct.replace(",", ""))
        # Generate nearby values
        offsets = random.sample([-3, -2, -1, 1, 2, 3], 3)
        for off in offsets:
            d = num + off
            # Keep same format (int vs float)
            if num == int(num):
                distractors.append(str(int(d)))
            else:
                distractors.append(f"{d:.{len(correct.split('.')[-1])}f}")
    except (ValueError, IndexError):
        # Non-numeric — use generic labels
        distractors = [
            f"Not {correct}",
            "None of the above",
            "Cannot be determined",
        ]

    choices = distractors + [correct]
    random.shuffle(choices)
    return choices


def _salvage_exercise(ex: Exercise) -> Exercise | None:
    """Attempt to salvage an exercise by demoting its type if needed.

    If an exercise has the core fields (question + correct_answer) but is
    missing type-specific fields (e.g. multi_select without choices), demote
    it to fill_in_the_blank rather than dropping it entirely.

    :param ex: Parsed exercise.
    :return: The (possibly demoted) exercise, or None if unsalvageable.
    """
    # Must have question text and a correct answer — can't salvage without these
    if not ex.question.strip() or not ex.correct_answer.strip():
        return None

    q_type = ex.question_type

    # Sequence/table types require typing comma-separated values which
    # is poor UX for young students. Convert to MC.
    if q_type in ("sequence_order", "table_matching"):
        if ex.choices:
            ex.question_type = "multiple_choice"
        else:
            # Will be handled by the missing-choices block below
            ex.question_type = "multiple_choice"
        q_type = ex.question_type

    # Any type that's missing choices: generate distractors from the
    # correct answer so we always show clickable radio buttons.
    if not ex.choices and ex.correct_answer.strip():
        ex.choices = _generate_distractors(ex.correct_answer.strip())
        ex.question_type = "multiple_choice"
        q_type = "multiple_choice"

    # Type-specific required fields
    required = _REQUIRED_FIELDS_BY_TYPE.get(q_type, [])
    missing = [f for f in required if getattr(ex, f, None) is None]
    if missing:
        if ex.choices:
            ex.question_type = "multiple_choice"
        else:
            ex.question_type = "fill_in_the_blank"

    return ex


def _build_allowed_sets(
    topics: dict[str, list[str]],
) -> tuple[set[str], set[str]]:
    """Build allowed topic and concept sets from band data.

    Handles semicolon-separated compound topic names and also adds each
    topic name (and its parts) as an allowed concept, since the LLM
    frequently uses a topic name as the concept value.

    :param topics: Topic-to-concepts mapping from the band.
    :return: (allowed_topics, allowed_concepts) both lowercased.
    """
    allowed_topics: set[str] = set()
    allowed_concepts: set[str] = set()

    for t, concepts in topics.items():
        allowed_topics.add(t.lower())
        for part in t.split(";"):
            stripped = part.strip().lower()
            if stripped:
                allowed_topics.add(stripped)
                # Allow topic names as concept values — the LLM often
                # uses e.g. "volume" as the concept for topic "Volume".
                allowed_concepts.add(stripped)
        for c in concepts:
            allowed_concepts.add(c.lower())

    return allowed_topics, allowed_concepts


def _fixup_exercise(
    ex: Exercise,
    allowed_topics: set[str],
    allowed_concepts: set[str],
) -> Exercise:
    """Best-effort repair of topic/concept values.

    If the LLM returned a concept that matches a topic name (or vice
    versa), swap them into the right field. This avoids rejecting
    otherwise-good exercises over minor labelling issues.

    :param ex: Exercise to fix up.
    :param allowed_topics: Allowed topic names (lowercased).
    :param allowed_concepts: Allowed concept names (lowercased).
    :return: Possibly-modified exercise.
    """
    topic_lc = ex.topic.strip().lower()
    concept_lc = ex.concept.strip().lower()

    # If concept value is actually a topic name and topic value is a
    # concept name, they were swapped.
    if (
        concept_lc in allowed_topics
        and concept_lc not in allowed_concepts
        and topic_lc in allowed_concepts
        and topic_lc not in allowed_topics
    ):
        ex.topic, ex.concept = ex.concept, ex.topic

    return ex


def _normalize_list(raw: list | None) -> list[str] | None:
    """Normalize a list field from Gemma — flatten nested lists, stringify."""
    if not raw or not isinstance(raw, list):
        return None
    return [str(c[0]) if isinstance(c, list) else str(c) for c in raw]


def _parse_exercises(content: str) -> list[Exercise]:
    """Parse raw JSON from Gemma into a list of Exercise objects.

    Handles both array and ``{"exercises": [...]}`` formats, normalizes
    field values, and coerces unrecognized question types.

    :param content: Raw JSON string from Gemma.
    :return: List of parsed exercises (may include broken ones).
    """
    parsed = json.loads(content)

    # Handle both array and object responses
    if isinstance(parsed, dict):
        exercises_data = parsed.get("exercises", [parsed])
    else:
        exercises_data = parsed

    # If Gemma returned a single dict (not wrapped), ensure it's a list
    if isinstance(exercises_data, dict):
        exercises_data = [exercises_data]

    exercises: list[Exercise] = []
    for ex in exercises_data:
        if not isinstance(ex, dict):
            continue

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

        # Normalize question_type — coerce unrecognized types so the UI
        # can render them properly.
        raw_q_type = ex.get("question_type", "multiple_choice")
        if raw_q_type not in _VALID_QUESTION_TYPES:
            if choices:
                raw_q_type = "multiple_choice"
            else:
                raw_q_type = "fill_in_the_blank"

        exercises.append(
            Exercise(
                concept=ex.get("concept", ""),
                topic=ex.get("topic", ""),
                question=ex.get("question", ""),
                question_type=raw_q_type,
                choices=choices,
                correct_answer=str(
                    ex.get("correct_answer")
                    or (correct_answers[0] if correct_answers else None)
                    or (ex.get("part_b_correct") if raw_q_type == "two_part" else None)
                    or ""
                ),
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

    return exercises


def _call_gemma(prompt: str) -> str:
    """Call Gemma and return the raw response content.

    :param prompt: The prompt to send.
    :return: Raw response text.
    """
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )
    return response.message.content.strip()


_MAX_RETRIES = 2


def generate_exercises(
    student_name: str,
    grade: int,
    band: BandInfo,
    num_questions: int = 5,
    weak_concepts: list[str] | None = None,
    subject: str = "math",
) -> ExerciseSet:
    """Generate exercises using Gemma 4.

    Makes up to ``_MAX_RETRIES`` attempts, accumulating valid exercises
    across retries until the requested count is reached.
    """
    prompt = build_exercise_prompt(
        student_name=student_name,
        grade=grade,
        band_name=band.band,
        topics=band.topics,
        num_questions=num_questions,
        weak_concepts=weak_concepts,
        subject=subject,
    )

    # Build allowed sets once for fixup
    allowed_topics: set[str] | None = None
    allowed_concepts: set[str] | None = None
    if band.topics:
        allowed_topics, allowed_concepts = _build_allowed_sets(band.topics)

    all_valid: list[Exercise] = []

    for attempt in range(_MAX_RETRIES):
        # On retry, ask for only the missing count
        needed = num_questions - len(all_valid)
        if needed <= 0:
            break

        if attempt > 0:
            logger.info(
                "Retry %d: requesting %d more exercises", attempt, needed
            )
            prompt = build_exercise_prompt(
                student_name=student_name,
                grade=grade,
                band_name=band.band,
                topics=band.topics,
                num_questions=needed,
                weak_concepts=weak_concepts,
                subject=subject,
            )

        content = _call_gemma(prompt)
        logger.info(
            "Gemma response attempt %d (%d chars): %s",
            attempt + 1,
            len(content),
            content[:6000],
        )

        exercises = _parse_exercises(content)

        # Fix up topic/concept values
        if allowed_topics and allowed_concepts:
            exercises = [
                _fixup_exercise(ex, allowed_topics, allowed_concepts)
                for ex in exercises
            ]

        for i, ex in enumerate(exercises):
            logger.info(
                "Exercise %d: type=%s, concept=%s, has_choices=%s, "
                "has_correct_answer=%s",
                i + 1,
                ex.question_type,
                ex.concept,
                bool(ex.choices),
                bool(ex.correct_answer and ex.correct_answer.strip()),
            )

        # Salvage and collect valid exercises
        for i, ex in enumerate(exercises):
            salvaged = _salvage_exercise(ex)
            if salvaged is not None:
                all_valid.append(salvaged)
            else:
                logger.warning(
                    "Dropped exercise %d (attempt %d): question=%r, "
                    "correct_answer=%r, question_type=%r, choices=%r",
                    i + 1,
                    attempt + 1,
                    ex.question[:80] if ex.question else None,
                    ex.correct_answer[:40] if ex.correct_answer else None,
                    ex.question_type,
                    bool(ex.choices),
                )

        if len(all_valid) >= num_questions:
            break

    if not all_valid:
        raise ValueError(
            "All generated exercises failed validation — none were usable"
        )

    # Trim to requested count in case we got extras
    all_valid = all_valid[:num_questions]

    logger.info(
        "Returning %d/%d exercises after %d attempt(s)",
        len(all_valid),
        num_questions,
        attempt + 1,
    )

    return ExerciseSet(
        student_name=student_name,
        band=band.band,
        exercises=all_valid,
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
