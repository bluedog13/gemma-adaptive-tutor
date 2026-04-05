"""All Gemma 4 prompt templates for MAP Accelerator."""

from src.constants import (
    NWEA_CONDITIONAL_GROWTH,
    NWEA_MEAN_RIT,
    estimate_percentile,
    get_percentile_cutoffs,
)
from src.models.schemas import SUBJECT_DISPLAY


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
        "- Most questions must be multiple_choice with exactly 4 choices\n"
        "- You may include 1-2 fill_in_the_blank questions where the answer is a single number or short expression\n"
        "- Every question MUST end with a clear question sentence (e.g. 'What is the value of x?', 'How many apples are left?')\n"
        "- Each question should test ONE concept\n"
        "- Include a clear, step-by-step explanation for each answer\n"
        "- Make word problems relatable to a child's everyday life"
    ),
    "reading": (
        "- ALL questions must be multiple_choice with exactly 4 choices\n"
        "- Most questions should include a short age-appropriate passage (3-5 sentences) followed by a question about it\n"
        "- Every question MUST end with a clear question sentence (e.g. 'What is the main idea of this passage?', 'What does the word ___ mean in this sentence?')\n"
        "- Include vocabulary-in-context questions where appropriate\n"
        "- Include a clear explanation for each answer, referencing the text\n"
        "- Use engaging, age-appropriate passages about topics kids enjoy"
    ),
    "science": (
        "- ALL questions must be multiple_choice with exactly 4 choices\n"
        "- Include experiment scenarios where you describe a simple experiment and ask about predictions, variables, or conclusions\n"
        "- Every question MUST end with a clear question sentence (e.g. 'What would most likely happen?', 'Which best explains why...?')\n"
        "- Include diagram interpretation questions when relevant (describe the diagram in text)\n"
        "- Include a clear, step-by-step explanation for each answer\n"
        "- Connect concepts to real-world observations kids can relate to"
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
    all_concepts: list[str],
    num_questions: int = 5,
    weak_concepts: list[str] | None = None,
    subject: str = "math",
) -> str:
    """Build the exercise generation prompt for Gemma 4."""
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
        focus_note = f"\nFocus more questions on these concepts the student is struggling with: {', '.join(weak_concepts)}"

    return f"""You are a {tutor_role} for a grade {grade} student named {student_name}.

Generate exactly {num_questions} {subject_display} practice exercises for the following concepts from RIT band {band_name}:

Concepts to cover:
{chr(10).join(f"- {c}" for c in all_concepts)}
{focus_note}

Requirements:
- Age-appropriate for grade {grade} (ages {grade + 5}-{grade + 6})
{type_guidance}

Respond with ONLY a JSON array of exercises. Each exercise must have:
- "concept": the specific concept being tested
- "topic": the broader topic category
- "question": the full question text
- "question_type": one of the types listed above
- "choices": array of 4 options (only for multiple_choice, null otherwise)
- "correct_answer": the correct answer as a string
- "explanation": step-by-step explanation of how to solve it

JSON array:"""


def build_report_prompt(
    student_name: str,
    grade: int,
    latest_rit: int,
    trend: str,
    num_sessions: int,
    mastered_concepts: list[str],
    needs_work_concepts: list[str],
    subject: str = "math",
) -> str:
    """Build the progress report prompt for Gemma 4."""
    subject_display = SUBJECT_DISPLAY.get(subject, subject.title())

    return f"""You are writing a brief progress report for a grade {grade} student named {student_name}.

Subject: {subject_display}

Student data:
- Latest MAP {subject_display} RIT score: {latest_rit}
- Trend: {trend}
- Total practice sessions: {num_sessions}
- Mastered concepts (>=80% correct): {", ".join(mastered_concepts) if mastered_concepts else "None yet"}
- Needs more work (<80% correct): {", ".join(needs_work_concepts) if needs_work_concepts else "None yet"}

Write a 3-4 paragraph report for their teacher or parent that:
1. Summarizes where the student is and their growth trend in {subject_display}
2. Highlights what they've mastered
3. Recommends specific next steps for concepts that need work
4. Encourages continued practice

Keep the tone warm, specific, and actionable. No jargon — a parent should understand it."""
