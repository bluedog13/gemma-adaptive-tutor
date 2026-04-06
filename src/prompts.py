"""All Gemma 4 prompt templates for MAP Accelerator."""

import re

from src.constants import (
    NWEA_CONDITIONAL_GROWTH,
    NWEA_MEAN_RIT,
    estimate_percentile,
    get_percentile_cutoffs,
)
from src.models.schemas import SUBJECT_DISPLAY

_MAX_NAME_LENGTH = 60


def _sanitize_name(name: str) -> str:
    """Sanitize a student name for safe prompt interpolation.

    Strips control characters, collapses whitespace, limits length, and
    removes characters that could be used for prompt injection.

    :param name: Raw student name.
    :return: Sanitized name safe for embedding in prompts.
    """
    # Remove control characters and non-printable chars
    name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", name)
    # Allow letters, numbers, spaces, hyphens, apostrophes, periods
    name = re.sub(r"[^\w\s\-'.À-ÖØ-öø-ÿ]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Truncate
    name = name[:_MAX_NAME_LENGTH]
    return name or "Student"


def _build_norms_context(
    grade: int, latest_rit: int, season: str = "fall", subject: str = "math"
) -> str:
    """Build NWEA norms context string for prompts."""
    subject_display = SUBJECT_DISPLAY.get(subject, subject.title())
    if subject not in NWEA_MEAN_RIT:
        raise ValueError(
            f"No NWEA norms data for subject '{subject}'. "
            f"Available: {list(NWEA_MEAN_RIT.keys())}"
        )
    means = NWEA_MEAN_RIT[subject].get(grade, NWEA_MEAN_RIT[subject][3])
    season_pcts = get_percentile_cutoffs(grade, season, subject)
    cond_growth = NWEA_CONDITIONAL_GROWTH[subject].get(
        grade, NWEA_CONDITIONAL_GROWTH[subject][3]
    )
    pct = estimate_percentile(latest_rit, grade, season, subject)

    return f"""NWEA 2025 National Norms for Grade {grade} {subject_display}:
- Mean RIT: Fall {means["fall"]}, Winter {means["winter"]}, Spring {means["spring"]}
- Percentile cutoffs ({season.capitalize()}): 25th={season_pcts[25]}, 50th={season_pcts[50]}, 75th={season_pcts[75]}, 90th={season_pcts[90]}, 95th={season_pcts[95]}
- This student's latest RIT {latest_rit} ({season.capitalize()}) is approximately at the {pct}th percentile

Expected fall-to-spring growth by starting percentile (Grade {grade}):
- 10th percentile students: ~{cond_growth[10]} RIT points
- 25th percentile students: ~{cond_growth[25]} RIT points
- 50th percentile students: ~{cond_growth[50]} RIT points
- 75th percentile students: ~{cond_growth[75]} RIT points
- 90th percentile students: ~{cond_growth[90]} RIT points
- 95th percentile students: ~{cond_growth[95]} RIT points

Key research findings (NWEA, Fordham Institute, Northwestern CTD):
- Advanced students (75th+ percentile) consistently show LOWER growth than peers — not because they can't grow, but because they aren't challenged with above-grade-level content
- This is called the "excellence gap": high-achieving students plateau when instruction focuses on grade-level proficiency rather than extension
- A student at the 90th percentile typically grows only {cond_growth[90]} RIT points/year vs {cond_growth[50]} for a median student — that's {cond_growth[50] - cond_growth[90]} fewer points of growth
- NWEA research shows these norms are DESCRIPTIVE (what typically happens), NOT PRESCRIPTIVE (what should happen) — advanced students CAN grow more with targeted enrichment
- The "sawtooth pattern" (scores dip at start of year, recover by spring) is common when untaught above-grade content is assessed
- The conditional growth data above shows what students WHO STARTED AT THE SAME LEVEL are growing nationally. If this student is growing LESS than peers who started at the same level, it means other schools/programs ARE closing this gap — this student's school is not providing sufficient challenge
- Growing below expected for your starting percentile = falling behind similar-ability peers nationally, even if the raw score is still high"""


def build_trend_prompt(
    grade: int,
    timeline: str,
    latest_rit: int,
    season: str = "fall",
    subject: str = "math",
) -> str:
    """Build the trend analysis prompt for Gemma 4."""
    subject_display = SUBJECT_DISPLAY.get(subject, subject.title())
    norms_context = _build_norms_context(grade, latest_rit, season, subject)

    return f"""You are an educational data analyst specializing in MAP (NWEA) assessment data.

A grade {grade} student has the following MAP {subject_display} RIT scores:
{timeline}

{norms_context}

IMPORTANT ANALYSIS RULES:
1. Focus on RECENT growth (last 2-3 test sessions), not just the total over all time
2. If the score dropped from spring to fall when entering a new grade, that is a "sawtooth pattern" — flag it
3. If the student's RIT is the same or lower than it was 2-3 sessions ago, that is STALLING, not growing
4. Compare the student's RECENT growth rate against expected growth for their percentile level
5. Be honest — do not say "strong growth" if the student has plateaued recently
6. A student who scores 196 in Spring, drops to 193 in Fall, and recovers to 196 in Winter has had ZERO net growth in 9 months — that is stalling
7. The "expected fall-to-spring growth" numbers ONLY apply to fall-to-spring comparisons within the SAME school year. Do NOT cite these numbers for spring-to-winter or spring-to-fall intervals — those cross grade boundaries and are not comparable. For non fall-to-spring intervals, describe the actual growth without citing a specific expected number

Compare this student's actual growth against what is typical for students at their percentile level. Use the national norms data above to ground your analysis in real numbers.

Analyze this student's trajectory. Respond with ONLY a JSON object with these exact keys:
{{
  "trend": "growing" or "stalling" or "declining",
  "where_they_stand": "One sentence: their current percentile and how it compares to grade-level peers",
  "growth_pattern": "One sentence: RECENT growth (last 2-3 sessions) vs expected, cite the specific numbers",
  "what_this_means": "One sentence: name the pattern (excellence gap, sawtooth, plateau, strong growth, etc.) and why it matters",
  "recommendation": "One sentence: a specific, actionable next step"
}}

JSON:"""


_EXERCISE_TYPE_GUIDANCE: dict[str, str] = {
    "math": (
        "Use a MIX of these MAP-style question types (vary across questions):\n"
        "\n"
        "1. **multiple_choice** — Standard 4-option MC. Set question_type to "
        '"multiple_choice", provide "choices" (4 items), "correct_answer".\n'
        "   - For visual questions (coins, base-10 blocks, arrays, shapes), "
        "DESCRIBE the visual in the question text. Example: "
        '"A set of base-10 blocks shows 4 hundreds flats, 3 tens rods, '
        'and 2 ones cubes. What number do the blocks represent?"\n'
        "\n"
        '2. **multi_select** — "Choose all that apply" or "Choose two". '
        'Set question_type to "multi_select", provide "choices" (4-6 items), '
        '"num_correct" (how many to pick), "correct_answers" (list of correct '
        "choices). Set correct_answer to the first correct answer.\n"
        "\n"
        "3. **two_part** — Error analysis or two-step reasoning. "
        "Part A asks what went wrong or for a first answer. "
        "Part B asks for the correct answer or supporting evidence. "
        'Set question_type to "two_part", provide "choices" for Part A, '
        '"part_b_question", "part_b_choices", "part_b_correct". '
        "correct_answer is the Part A answer.\n"
        "\n"
        "Rules:\n"
        "- Vary reasoning depth across questions:\n"
        "  - 2 questions: SINGLE-STEP (difficulty_tier 1) — one concept, "
        "direct application\n"
        "  - 2 questions: MULTI-STEP (difficulty_tier 2) — same concept "
        "but chain 2-3 operations in a word problem. Do NOT hint which "
        "operations to use\n"
        "  - 1 question: CHALLENGE (difficulty_tier 3) — combine two "
        "concepts from the list into one problem that requires the "
        "student to figure out the approach\n"
        "- Every question ends with a clear question sentence\n"
        "- Include a step-by-step explanation for each answer\n"
        "- Make word problems relatable to a child's everyday life\n"
        "- Aim for roughly: 2 multiple_choice, 1 multi_select, "
        "1 two_part, 1 of any type\n"
        '- EVERY question MUST have a "choices" array with 4 options — '
        "do NOT use fill_in_the_blank"
    ),
    "reading": (
        "Use a MIX of these MAP-style question types (vary across questions):\n"
        "\n"
        'ALL reading questions MUST include a "scenario" field with a '
        "4-8 sentence age-appropriate passage. The passage goes in the "
        '"scenario" field, NOT in the "question" field.\n'
        "\n"
        "1. **multiple_choice** — Standard passage + MC. Set question_type "
        'to "multiple_choice", provide "scenario" (passage), "choices" '
        "(4 items), correct_answer.\n"
        "\n"
        '2. **two_part** — Part A/Part B (e.g., "What is the lesson?" then '
        '"Which detail supports your answer?"). Set question_type to '
        '"two_part", provide "scenario" (passage), "choices" for Part A, '
        '"part_b_question", "part_b_choices", "part_b_correct". '
        "correct_answer is the Part A answer.\n"
        "\n"
        '3. **multi_select** — "Choose two details that support..." '
        'Set question_type to "multi_select", provide "scenario", '
        '"choices" (4-6 items), "num_correct", "correct_answers".\n'
        "\n"
        "4. **sequence_order** — Procedural text with steps to order. "
        'Set question_type to "sequence_order", provide "scenario", '
        '"items_to_order" (shuffled list), "correct_order" (correct list). '
        "correct_answer = comma-joined correct order.\n"
        "\n"
        "Rules:\n"
        "- EVERY question must have a scenario (passage)\n"
        "- Use engaging, age-appropriate passages about topics kids enjoy\n"
        "- Include vocabulary-in-context questions where appropriate\n"
        "- Explanations should reference the text\n"
        "- Aim for roughly: 2 multiple_choice, 1 two_part, 1 multi_select, "
        "1 of any type"
    ),
    "science": (
        "Use a MIX of these MAP-style question types (vary across questions):\n"
        "\n"
        'ALL science questions MUST include a "scenario" field describing '
        "an experiment, observation, or real-world situation. The scenario "
        'goes in the "scenario" field, NOT in the "question" field.\n'
        "\n"
        "1. **multiple_choice** — Scenario + standard MC. Set question_type "
        'to "multiple_choice", provide "scenario", "choices" (4 items), '
        "correct_answer.\n"
        "\n"
        '2. **multi_select** — "Which two designs would reduce warming?" '
        'Set question_type to "multi_select", provide "scenario", '
        '"choices" (4-6 items), "num_correct", "correct_answers".\n'
        "\n"
        "3. **table_matching** — Before/after, cause/effect, or "
        'classification. Set question_type to "table_matching", provide '
        '"scenario", "match_pairs" (dict mapping item to correct category), '
        '"match_options" (list of category labels). '
        "correct_answer = summary of correct pairs.\n"
        "\n"
        "4. **sequence_order** — Life cycle stages, process steps. "
        'Set question_type to "sequence_order", provide "scenario", '
        '"items_to_order" (shuffled), "correct_order" (correct sequence). '
        "correct_answer = comma-joined correct order.\n"
        "\n"
        "5. **multiple_choice** with pattern prediction — Describe a pattern "
        "(e.g., moon phases, seasons) and ask what comes next.\n"
        "\n"
        "Rules:\n"
        "- EVERY question must have a scenario\n"
        "- Describe diagrams, tables, and visuals in text\n"
        "- Include step-by-step explanations\n"
        "- Connect concepts to real-world observations kids relate to\n"
        "- Aim for roughly: 2 multiple_choice, 1 multi_select or "
        "table_matching, 1 sequence_order, 1 of any type"
    ),
}

_TUTOR_ROLE: dict[str, str] = {
    "math": "math tutor",
    "reading": "reading and language arts tutor",
    "science": "science tutor",
}


def build_exercise_prompt(
    student_name: str,
    grade: int,
    band_name: str,
    topics: dict[str, list[str]],
    num_questions: int = 5,
    weak_concepts: list[str] | None = None,
    subject: str = "math",
) -> str:
    """Build the exercise generation prompt for Gemma 4.

    :param topics: Mapping of topic name to list of concept strings.
    """
    subject_display = SUBJECT_DISPLAY.get(subject, subject.title())
    if subject not in _TUTOR_ROLE:
        raise ValueError(
            f"No tutor role defined for subject '{subject}'. "
            f"Available: {list(_TUTOR_ROLE.keys())}"
        )
    tutor_role = _TUTOR_ROLE[subject]
    type_guidance = _EXERCISE_TYPE_GUIDANCE[subject]

    focus_note = ""
    if weak_concepts:
        focus_note = (
            "\nFocus more questions on these concepts the student is "
            f"struggling with: {', '.join(weak_concepts)}"
        )

    # Format concepts grouped under their topic.
    # Curriculum data may contain semicolon-separated compound topic names
    # (e.g. "Decimals — Compare/Order; Decimals — Represent/Model").
    # Split them so the LLM sees each as a separate, valid topic name.
    topic_lines: list[str] = []
    for topic_name, concepts in topics.items():
        individual_topics = [t.strip() for t in topic_name.split(";") if t.strip()]
        for indiv in individual_topics:
            topic_lines.append(f"Topic: {indiv}")
            for concept in concepts:
                topic_lines.append(f"  - {concept}")
    concepts_block = chr(10).join(topic_lines)

    student_name = _sanitize_name(student_name)

    return f"""You are a {tutor_role} for a grade {grade} student named {student_name}.

Generate exactly {num_questions} {subject_display} practice exercises for the following concepts from RIT band {band_name}:

{concepts_block}
{focus_note}

Requirements:
- Age-appropriate for grade {grade} (ages {grade + 5}-{grade + 6})
- NEVER use LaTeX, MathJax, or dollar-sign math notation (e.g., $\\frac{{3}}{{10}}$). Write fractions as plain text like "3/10", exponents as "2^3", and symbols as words or Unicode (e.g., "x", ">=", "+")
{type_guidance}

CRITICAL: Return a JSON object with an "exercises" array containing EXACTLY {num_questions} exercise objects.
Format: {{"exercises": [exercise1, exercise2, ..., exercise{num_questions}]}}

Each exercise object MUST have ALL of these fields:
- "concept": the specific concept being tested (use EXACTLY a concept name from the list above)
- "topic": the broader topic category (use EXACTLY a Topic name from the list above)
- "question": the full question text (do NOT put passage/scenario text here)
- "question_type": one of "multiple_choice", "multi_select", "two_part", "sequence_order", "table_matching"
- "choices": array of 4 answer options (REQUIRED for ALL question types)
- "correct_answer": the correct answer as a string (REQUIRED — never omit this)
- "explanation": step-by-step explanation of how to solve it
- "difficulty_tier": integer 1 (single-step), 2 (multi-step), or 3 (challenge)

Additional fields for specific question types:
- "scenario": passage text shown above the question (REQUIRED for reading and science)
- "num_correct": integer, how many to pick (for multi_select)
- "correct_answers": array of correct answer strings (for multi_select)
- "part_b_question": Part B question text (for two_part)
- "part_b_choices": array of Part B options (for two_part)
- "part_b_correct": correct Part B answer string (for two_part)
- "items_to_order": array of shuffled items (for sequence_order)
- "correct_order": array in correct sequence (for sequence_order)
- "match_pairs": object mapping item to correct category (for table_matching)
- "match_options": array of category labels (for table_matching)

JSON:"""


def build_report_prompt(
    student_name: str,
    grade: int,
    latest_rit: int,
    trend: str,
    num_sessions: int,
    mastered_concepts: list[str],
    needs_work_concepts: list[str],
    subject: str = "math",
    session_details: list[str] | None = None,
) -> str:
    """Build the progress report prompt for Gemma 4.

    :param session_details: one-line summaries per practice session.
    """
    subject_display = SUBJECT_DISPLAY.get(subject, subject.title())

    student_name = _sanitize_name(student_name)

    session_section = ""
    if session_details:
        lines = "\n".join(f"- {line}" for line in session_details)
        session_section = f"\n\nPractice session results:\n{lines}"

    return f"""You are writing a brief progress report for a grade {grade} student named {student_name}.

Subject: {subject_display}

Student data:
- Latest MAP {subject_display} RIT score: {latest_rit}
- Trend: {trend}
- Total practice sessions: {num_sessions}
- Mastered concepts (>=80% correct): {", ".join(mastered_concepts) if mastered_concepts else "None yet"}
- Needs more work (<80% correct): {", ".join(needs_work_concepts) if needs_work_concepts else "None yet"}{session_section}

Do NOT use placeholder text like "[Parent/Teacher Name]". Start directly with the report content.
Do NOT repeat the raw data tables — a data dashboard is shown separately above your narrative.

Write a structured progress report for their teacher or parent using this exact format:

**Growth Trajectory**
One short paragraph interpreting the trend — is the student improving, plateauing, or struggling? Call out specific sessions that show breakthroughs or dips.

**Strengths**
- One bullet per mastered concept, with a brief note on what it means (e.g., "**Unit cube** — understands 3D volume building blocks")

**Focus Areas**
- One bullet per concept below 80%, with a concrete, parent-friendly activity suggestion (e.g., "**Rates** — try comparing speeds of toy cars: 'Which car is faster?' builds intuition for rates")

**Next Steps**
A short encouraging closing paragraph with 1-2 specific recommendations for continued practice.

Keep the tone warm, specific, and actionable. No jargon — a parent should understand it."""
