"""Gradio frontend for MAP Accelerator."""

import logging
import re
import traceback

import gradio as gr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("map_accelerator")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from src.constants import SEASON_ORDER
from src.models.database import (
    init_db, SessionLocal, Student, Score, PracticeSession,
    ExerciseResultRecord, compute_scores_hash,
)
from src.models.schemas import CurriculumResult, ScoreInput, SessionSummary
from src.tools.curriculum import (
    map_rit_to_curriculum, detect_trend,
    get_cached_analysis, get_cached_scores_hash, save_analysis_cache,
)
from src.tools.exercise_generator import generate_exercises, generate_report
from src.tools.score_extractor import extract_scores_from_file

def _grade_to_int(grade: str | int) -> int:
    """Convert a grade value to integer, handling 'KG' as 0."""
    if isinstance(grade, int):
        return grade
    g = str(grade).strip().upper()
    return 0 if g == "KG" else int(g)


# Initialize database
init_db()

# In-memory state for current session
current_exercises = []
current_exercise_idx = 0
current_session_id = None
current_student_id = None
current_band = ""
current_rit = 0
session_results = []

def _grade_for_score(season: str, year: int, current_grade: int, latest_season: str, latest_year: int) -> int:
    """Compute the student's grade at the time of a given score.

    School year runs Aug-June. Fall/winter of year Y = school year Y-(Y+1).
    Spring of year Y = school year (Y-1)-Y.
    Example: Fall 2025 and Winter 2026 are both the 2025-2026 school year.
             Spring 2025 is the 2024-2025 school year.
    """
    def _school_year(s: str, y: int) -> int:
        """Return the start calendar year of the school year."""
        if s == "spring":
            return y - 1  # spring 2025 → 2024-2025 school year → 2024
        return y  # fall 2025 → 2025-2026 → 2025, winter 2026 → 2025-2026 → 2025

    latest_sy = _school_year(latest_season, latest_year)
    score_sy = _school_year(season, year)

    grade = current_grade - (latest_sy - score_sy)
    return max(0, grade)


def create_score_chart(scores_data, student_name, current_grade, trend=None):
    """Create a chart showing actual scores vs NWEA national norms.

    scores_data entries must have: rit_score, season, year, and optionally grade.
    If grade is missing, it's computed from current_grade and school year logic.
    """
    from src.constants import NWEA_PERCENTILES, estimate_percentile

    # Sort chronologically: winter (Jan) < spring (Apr) < fall (Sep)
    _CHRONO_ORDER = {"winter": 0, "spring": 1, "fall": 2}
    sorted_scores = sorted(scores_data, key=lambda s: (s["year"], _CHRONO_ORDER[s["season"]]))
    latest = sorted_scores[-1]

    # Get the grade for each score — use explicit grade if provided, else compute
    grades_per_score = []
    for s in sorted_scores:
        if "grade" in s and s["grade"] is not None:
            grades_per_score.append(_grade_to_int(s["grade"]))
        else:
            grades_per_score.append(
                _grade_for_score(s["season"], s["year"], _grade_to_int(current_grade), latest["season"], latest["year"])
            )

    labels = [f"{s['season'].capitalize()} {s['year']}\n({'KG' if grades_per_score[i] == 0 else f'G{grades_per_score[i]}'})" for i, s in enumerate(sorted_scores)]
    actual = [s["rit_score"] for s in sorted_scores]

    # Build norm lines using the correct grade for each score
    norm_50th, norm_75th, norm_90th, norm_95th = [], [], [], []
    for i, s in enumerate(sorted_scores):
        g = max(0, min(grades_per_score[i], 5))  # clamp to data range
        pcts = NWEA_PERCENTILES.get(g, NWEA_PERCENTILES[3])
        norm_50th.append(pcts[s["season"]][50])
        norm_75th.append(pcts[s["season"]][75])
        norm_90th.append(pcts[s["season"]][90])
        norm_95th.append(pcts[s["season"]][95])

    # Compute expected growth line and next-exam target before plotting,
    # so labels/norms arrays are fully built before any ax.plot() calls.
    expected_line = []
    next_expected = None
    if len(actual) >= 2:
        # Find student's approximate starting percentile
        first_g = max(0, min(grades_per_score[0], 5))
        first_rit = actual[0]
        start_pct = estimate_percentile(first_rit, first_g, sorted_scores[0]["season"])

        # Clamp to nearest available percentile bracket (max 95th in our data)
        pct_keys = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95]
        clamped_pct = max(5, min(start_pct, 95))
        lower_pct = 5
        upper_pct = 95
        for j in range(len(pct_keys) - 1):
            if clamped_pct <= pct_keys[j + 1]:
                lower_pct = pct_keys[j]
                upper_pct = pct_keys[j + 1]
                break
        if upper_pct > lower_pct:
            frac = (clamped_pct - lower_pct) / (upper_pct - lower_pct)
        else:
            frac = 0.5

        # Build expected line for each existing score
        expected_line = [first_rit]
        for i in range(1, len(sorted_scores)):
            g = max(0, min(grades_per_score[i], 5))
            pcts = NWEA_PERCENTILES.get(g, NWEA_PERCENTILES[3])
            season_pcts = pcts[sorted_scores[i]["season"]]
            low_val = season_pcts[lower_pct]
            high_val = season_pcts[upper_pct]
            expected_rit = round(low_val + frac * (high_val - low_val))
            expected_line.append(expected_rit)

        # Extend one point into the future — next exam target
        _SEASON_CYCLE = ["winter", "spring", "fall"]
        last_season = sorted_scores[-1]["season"]
        last_year = sorted_scores[-1]["year"]
        last_grade = grades_per_score[-1]
        next_idx = (_SEASON_CYCLE.index(last_season) + 1) % 3
        next_season = _SEASON_CYCLE[next_idx]
        next_year = last_year if next_season != "winter" else last_year + 1
        next_grade = last_grade + 1 if next_season == "fall" else last_grade
        next_grade = max(0, min(next_grade, 5))

        next_pcts = NWEA_PERCENTILES.get(next_grade, NWEA_PERCENTILES[3])
        next_season_pcts = next_pcts[next_season]
        next_expected = round(next_season_pcts[lower_pct] + frac * (next_season_pcts[upper_pct] - next_season_pcts[lower_pct]))
        expected_line.append(next_expected)

        next_label = f"{next_season.capitalize()} {next_year}\n({'KG' if next_grade == 0 else f'G{next_grade}'})"
        labels.append(next_label)

        # Extend norm bands to cover the next exam point
        norm_50th.append(next_pcts[next_season][50])
        norm_75th.append(next_pcts[next_season][75])
        norm_90th.append(next_pcts[next_season][90])
        norm_95th.append(next_pcts[next_season][95])

    fig, ax = plt.subplots(figsize=(12, 6))

    # Shade percentile bands (now includes next-exam point if computed)
    ax.fill_between(range(len(labels)), norm_50th, norm_75th,
                    alpha=0.08, color="#6B7280", label="50th-75th percentile")
    ax.fill_between(range(len(labels)), norm_75th, norm_90th,
                    alpha=0.08, color="#4F46E5", label="75th-90th percentile")
    ax.fill_between(range(len(labels)), norm_90th, norm_95th,
                    alpha=0.06, color="#7C3AED", label="90th-95th percentile")

    # Plot norm lines
    ax.plot(labels, norm_50th, "--", color="#9CA3AF", linewidth=1.5)
    ax.plot(labels, norm_75th, "--", color="#6B7280", linewidth=1.5)
    ax.plot(labels, norm_90th, "--", color="#A78BFA", linewidth=1.5)
    ax.plot(labels, norm_95th, "--", color="#7C3AED", linewidth=1.5)

    # Inline percentile labels on the left side of the chart
    ax.annotate("50th", (labels[0], norm_50th[0]),
                textcoords="offset points", xytext=(-8, 0), ha="right",
                fontsize=9, color="#9CA3AF", fontweight="bold")
    ax.annotate("75th", (labels[0], norm_75th[0]),
                textcoords="offset points", xytext=(-8, 0), ha="right",
                fontsize=9, color="#6B7280", fontweight="bold")
    ax.annotate("90th", (labels[0], norm_90th[0]),
                textcoords="offset points", xytext=(-8, 0), ha="right",
                fontsize=9, color="#A78BFA", fontweight="bold")
    ax.annotate("95th", (labels[0], norm_95th[0]),
                textcoords="offset points", xytext=(-8, 0), ha="right",
                fontsize=9, color="#7C3AED", fontweight="bold")

    # Plot expected growth line + next-exam target
    if expected_line:
        ax.plot(labels, expected_line, "o:", color="#059669", linewidth=2, markersize=5, alpha=0.7, zorder=2)
        all_vals_extra = expected_line
    else:
        all_vals_extra = []

    # Plot actual scores (on top) — only for actual data points, not the future target
    actual_labels = labels[:len(actual)]
    ax.plot(actual_labels, actual, "o-", color="#4F46E5", linewidth=2.5, markersize=8, label=f"{student_name}", zorder=3)

    # Annotate both lines, placing green labels to avoid blue labels.
    # Blue labels always go above their dot (+12pt). Green labels are
    # placed to guarantee no overlap: below the dot when far enough from
    # blue, or shifted horizontally when the dots are very close.
    for i, v in enumerate(actual):
        exp_v = expected_line[i] if i < len(expected_line) else None

        # Blue label — always above the dot
        ax.annotate(str(v), (labels[i], v), textcoords="offset points",
                    xytext=(0, 12), ha="center", fontsize=10,
                    fontweight="bold", color="#4F46E5")

        # Green label — skip first point (same as actual) and skip if
        # values are identical (label would just duplicate blue)
        if exp_v is None or i == 0 or exp_v == v:
            continue

        gap = exp_v - v  # positive = green above blue
        if abs(gap) >= 12:
            # Plenty of room — place green below its own dot
            ax.annotate(str(exp_v), (labels[i], exp_v),
                        textcoords="offset points", xytext=(0, -14),
                        ha="center", fontsize=8, fontweight="bold",
                        color="#059669")
        elif gap > 0:
            # Green dot above blue but close — put green label further
            # above (above the green dot, away from blue's +12 label)
            ax.annotate(str(exp_v), (labels[i], exp_v),
                        textcoords="offset points", xytext=(18, 0),
                        ha="left", fontsize=8, fontweight="bold",
                        color="#059669")
        else:
            # Green dot below blue but close — put green label to
            # the right to avoid blue's above-label
            ax.annotate(str(exp_v), (labels[i], exp_v),
                        textcoords="offset points", xytext=(18, 0),
                        ha="left", fontsize=8, fontweight="bold",
                        color="#059669")

    # Label the future target point (last expected, beyond actual data)
    if expected_line and len(expected_line) > len(actual):
        ti = len(expected_line) - 1
        tv = expected_line[ti]
        ax.annotate(
            f"Target: {tv}", (labels[ti], tv),
            textcoords="offset points", xytext=(0, 12),
            ha="center", fontsize=9, color="#059669", fontweight="bold",
        )

    # Style
    ax.set_ylabel("RIT Score", fontsize=11)
    ax.set_title(f"{student_name} — Scores vs National Norms (NWEA 2025)", fontsize=13, fontweight="bold")
    ax.legend(loc="lower right", fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    all_vals = actual + norm_50th + norm_95th + all_vals_extra
    ax.set_ylim(min(all_vals) - 5, max(all_vals) + 8)

    # Add trend annotation if available
    if trend and len(actual) >= 2:
        total_change = actual[-1] - actual[0]
        sign = "+" if total_change >= 0 else ""
        trend_colors = {"growing": "#059669", "stalling": "#D97706", "declining": "#DC2626"}
        trend_icons = {"growing": "\u2191", "stalling": "\u2192", "declining": "\u2193"}
        color = trend_colors.get(trend, "#6B7280")
        icon = trend_icons.get(trend, "")

        ax.annotate(
            f"{icon} {trend.capitalize()} ({sign}{total_change} RIT)",
            xy=(0.02, 0.98), xycoords="axes fraction",
            ha="left", va="top", fontsize=9, fontweight="bold",
            color=color,
            bbox=dict(boxstyle="round,pad=0.4", facecolor=color, alpha=0.1, edgecolor=color, linewidth=1),
        )

    # Extra right margin for inline labels
    fig.subplots_adjust(right=0.88)

    fig.tight_layout()
    return fig


def get_existing_students():
    """Return list of existing students for the dropdown."""
    db = SessionLocal()
    try:
        students = db.query(Student).all()
        return {f"{s.name} — G{s.grade}": str(s.id) for s in students}
    finally:
        db.close()


def _default_scores_data() -> list[dict]:
    """Return default score rows for State."""
    return [{"rit": 185, "season": "winter", "year": 2025, "grade": "3"}]


def _empty_load_result():
    """Return empty values for a failed load_student call."""
    return "", "3", _default_scores_data()


def load_student(selection):
    """Load an existing student's scores and cached analysis from DB.

    If a cached analysis exists and matches current scores, renders it
    instantly (no Gemma call). Otherwise prompts to click Analyze.
    """
    empty = _empty_load_result()
    btn_analyze = gr.update(value="Analyze")
    btn_reanalyze = gr.update(value="Re-analyze")
    if not selection:
        return ("", "", "", None, btn_analyze) + tuple(empty)

    student_map = get_existing_students()
    student_id = student_map.get(selection)
    if not student_id:
        return ("Student not found.", "", "", None, btn_analyze) + tuple(empty)

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == int(student_id)).first()
        scores = db.query(Score).filter(Score.student_id == student.id).all()

        if not scores:
            return ("No scores found.", "", student_id, None, btn_analyze) + tuple(empty)

        global current_student_id
        current_student_id = student.id

        # Build dataframe rows from DB — most recent first, all scores
        sorted_db_scores = sorted(scores, key=lambda s: (s.year, SEASON_ORDER[s.season]), reverse=True)
        latest_db = sorted_db_scores[0]

        rows = []
        scores_with_grade = []
        for s in sorted_db_scores:
            if s.grade:
                sg = str(s.grade)
            else:
                sg = str(_grade_for_score(s.season, s.year, student.grade, latest_db.season, latest_db.year))
            rows.append({"rit": s.rit_score, "season": s.season, "year": s.year, "grade": sg})
            scores_with_grade.append({
                "rit_score": s.rit_score, "season": s.season,
                "year": s.year, "grade": _grade_to_int(sg),
            })

        # Check for cached analysis
        current_hash = compute_scores_hash(scores_with_grade, student.grade)
        cached_hash = get_cached_scores_hash(student.id, db)
        cached = get_cached_analysis(student.id, db)

        analysis_html = ""
        chart = None
        if cached and cached_hash == current_hash:
            analysis_html = _build_analysis_html(
                student.name, str(student.grade), cached,
            )
            if len(scores_with_grade) >= 2:
                chart = create_score_chart(
                    scores_with_grade, student.name, student.grade,
                    trend=cached.trend.value if cached.trend else None,
                )
            status = f"Loaded '{student.name}' with cached analysis."
            btn = btn_reanalyze
        elif cached and cached_hash != current_hash:
            analysis_html = (
                '<div class="band-card" style="border-left: 4px solid #D97706;">'
                '<div class="band-header">'
                '<span class="band-icon">⚠️</span> Scores Changed'
                "</div>"
                "<p>Scores have changed since last analysis. "
                "Click <b>Analyze</b> to update.</p></div>"
            )
            status = f"Loaded '{student.name}' — scores changed, click Analyze."
            btn = btn_analyze
        else:
            status = (
                f"Loaded '{student.name}' — click Analyze to run"
                " Gemma 4 analysis."
            )
            btn = btn_analyze

        return (
            status,
            analysis_html,
            student_id,
            chart,
            btn,
            student.name,
            str(student.grade),
            rows,
        )
    except Exception as e:
        logger.error("load_student failed: %s", traceback.format_exc())
        return (f"Error loading student: {e}", "", "", None, btn_analyze) + tuple(empty)
    finally:
        db.close()


def _parse_scores_list(scores_data: list[dict], default_grade: int) -> tuple[list[ScoreInput], list[dict]]:
    """Parse the scores state list into ScoreInput list and scores_with_grade list.

    :param scores_data: List of dicts with keys rit, season, year, grade.
    :param default_grade: Fallback grade if the grade field is empty.
    :return: Tuple of (scores, scores_with_grade).
    """
    scores: list[ScoreInput] = []
    scores_with_grade: list[dict] = []

    if not scores_data:
        return scores, scores_with_grade

    for row in scores_data:
        try:
            rit = int(row.get("rit", 0))
        except (ValueError, TypeError):
            continue
        if rit <= 0:
            continue

        season = str(row.get("season", "")).lower().strip()
        if season not in ("fall", "winter", "spring"):
            continue

        try:
            year = int(row.get("year", 0))
        except (ValueError, TypeError):
            continue

        grade_val = row.get("grade")
        if grade_val is not None and str(grade_val).strip():
            try:
                sg = _grade_to_int(grade_val)
            except (ValueError, TypeError):
                sg = default_grade
        else:
            sg = default_grade

        scores.append(ScoreInput(rit_score=rit, season=season, year=year))
        scores_with_grade.append({
            "rit_score": rit, "season": season, "year": year, "grade": sg,
        })

    return scores, scores_with_grade


def _build_analysis_html(
    name: str, grade: str | int, curriculum: CurriculumResult
) -> str:
    """Build the HTML analysis cards from a CurriculumResult.

    :param name: Student name.
    :param grade: Display grade (string or int).
    :param curriculum: CurriculumResult with bands and trend.
    :return: HTML string.
    """
    develop_cards = []
    for topic, concepts in curriculum.develop_band.topics.items():
        concept_chips = "".join(
            f'<span class="concept-chip">{c}</span>' for c in concepts
        )
        develop_cards.append(
            f'<div class="topic-card">'
            f'<div class="topic-name">{topic}</div>'
            f'<div class="concept-chips">{concept_chips}</div>'
            f'</div>'
        )

    introduce_cards = []
    for topic, concepts in curriculum.introduce_band.topics.items():
        concept_chips = "".join(
            f'<span class="concept-chip">{c}</span>' for c in concepts
        )
        introduce_cards.append(
            f'<div class="topic-card">'
            f'<div class="topic-name">{topic}</div>'
            f'<div class="concept-chips">{concept_chips}</div>'
            f'</div>'
        )

    trend_html = ""
    if curriculum.trend:
        raw = curriculum.trend_detail or ""
        sections = re.split(r"\s*-\s*\*\*", raw)
        trend_items = []
        for section in sections:
            section = section.strip()
            if not section:
                continue
            match = re.match(r"(.+?)\*\*\s*(.*)", section, re.DOTALL)
            if match:
                heading = match.group(1).rstrip(":").strip()
                body = match.group(2).strip()
                trend_items.append(
                    f'<li class="trend-item">'
                    f'<strong>{heading}:</strong> {body}'
                    f'</li>'
                )
            else:
                trend_items.append(
                    f'<li class="trend-item">{section}</li>'
                )

        trend_list = (
            f'<ul class="trend-list">{"".join(trend_items)}</ul>'
            if trend_items
            else f'<p style="color: #374151; margin: 0;">{raw}</p>'
        )
        trend_html = (
            f'<div class="band-card" style="border-left: 4px solid #6366f1;">'
            f'<div class="band-header">'
            f'<span class="band-icon">📈</span> Growth Trend'
            f'</div>'
            f'{trend_list}</div>'
        )

    develop_body = (
        "".join(develop_cards) if develop_cards
        else '<p style="color:#9ca3af;">No specific topics listed</p>'
    )
    introduce_body = "".join(introduce_cards)

    return f"""<div style="margin-bottom: 1.5rem;">
    <h1 style="color:#1e1b4b; margin-bottom: 0.75rem;">Analysis for {name}</h1>
    <span class="pill pill-primary">Latest RIT: {curriculum.rit_score}</span>
    <span class="pill pill-secondary">Current Band: {curriculum.develop_band.band}</span>
    <span class="pill pill-neutral">Grade: {grade}</span>
</div>

{trend_html}

<div class="band-card band-develop">
    <div class="band-header">
        <span class="band-icon">📚</span>
        Currently Mastering
        <span class="band-badge develop">Develop Band: {curriculum.develop_band.band}</span>
    </div>
    <p class="band-subtitle">Topics the student is working on now</p>
    <div class="topic-grid">{develop_body}</div>
</div>

<div class="band-card band-introduce">
    <div class="band-header">
        <span class="band-icon">🚀</span>
        Ready for Launch
        <span class="band-badge introduce">Introduce Band: {curriculum.introduce_band.band}</span>
    </div>
    <p class="band-subtitle">Concepts to introduce in the next practice session</p>
    <div class="topic-grid">{introduce_body}</div>
</div>
"""


def register_student(
    name: str, grade: str, scores_data: list[dict],
    force_refresh: bool = False,
) -> tuple:
    """Register a new student or analyze an existing one.

    :param name: Student name.
    :param grade: Current grade level as string.
    :param scores_data: List of dicts with keys rit, season, year, grade.
    :param force_refresh: If True, always re-run Gemma analysis.
    :return: Tuple of (status_msg, analysis, student_id, chart).
    """
    logger.info("register_student called: name=%s, grade=%s, force=%s", name, grade, force_refresh)
    if not name.strip():
        return "Please enter the student's name.", "", "", None

    scores, scores_with_grade = _parse_scores_list(scores_data, _grade_to_int(grade))
    if not scores:
        return "Please enter at least one MAP score.", "", "", None

    db = SessionLocal()
    try:
        existing = db.query(Student).filter(Student.name == name.strip()).first()

        if existing:
            student = existing
            logger.info("Found existing student: id=%s, name=%s", student.id, student.name)
            student.grade = _grade_to_int(grade)

            # Replace all existing scores with the new set
            db.query(Score).filter(Score.student_id == student.id).delete()
            for swg in scores_with_grade:
                db.add(Score(
                    student_id=student.id,
                    rit_score=swg["rit_score"],
                    season=swg["season"],
                    year=swg["year"],
                    grade=swg["grade"],
                ))
            db.commit()
            status_msg = f"Analyzing scores for '{student.name}'..."
        else:
            student = Student(name=name.strip(), grade=_grade_to_int(grade))
            db.add(student)
            db.flush()

            for swg in scores_with_grade:
                db.add(Score(
                    student_id=student.id,
                    rit_score=swg["rit_score"],
                    season=swg["season"],
                    year=swg["year"],
                    grade=swg["grade"],
                ))
            db.commit()
            db.refresh(student)
            status_msg = f"Student '{name}' registered with {len(scores)} score(s)."

        # Check cache
        current_hash = compute_scores_hash(scores_with_grade, _grade_to_int(grade))
        cached_hash = get_cached_scores_hash(student.id, db)
        curriculum = None

        if not force_refresh and cached_hash == current_hash:
            curriculum = get_cached_analysis(student.id, db)
            if curriculum:
                logger.info("Using cached analysis for student %s", student.id)
                status_msg += " (cached — instant)"

        if curriculum is None:
            latest_score = max(
                scores,
                key=lambda s: (s.year, SEASON_ORDER[str(s.season.value)]),
            )
            curriculum = map_rit_to_curriculum(
                latest_score.rit_score, scores, grade=_grade_to_int(grade),
            )
            save_analysis_cache(
                student.id, curriculum, current_hash,
                _grade_to_int(grade), db,
            )
            logger.info("Saved analysis cache for student %s", student.id)

        analysis = _build_analysis_html(name, grade, curriculum)

        global current_student_id
        current_student_id = student.id

        # Create chart if 2+ scores — actual vs NWEA norms
        chart = None
        if len(scores_with_grade) >= 2:
            chart = create_score_chart(
                scores_with_grade, name.strip(), _grade_to_int(grade),
                trend=curriculum.trend.value if curriculum.trend else None,
            )

        return (
            status_msg,
            analysis,
            str(student.id),
            chart,
        )
    except Exception as e:
        logger.error("register_student failed: %s", traceback.format_exc())
        return f"Error: {e}", "", "", None
    finally:
        db.close()


def start_practice(student_id, num_questions, progress=gr.Progress()):
    """Generate exercises and start a practice session."""
    logger.info("start_practice called: student_id=%s, num_questions=%s", student_id, num_questions)
    global current_exercises, current_exercise_idx, current_session_id, session_results, current_band, current_rit

    if not student_id:
        return "**Please go to Tab 1 and register a student first.**", "", "", gr.update(interactive=False)

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == int(student_id)).first()
        if not student:
            return "**Student not found.** Please register on Tab 1 first.", "", "", gr.update(interactive=False)

        progress(0.2, desc="Looking up curriculum bands...")
        scores = db.query(Score).filter(Score.student_id == student.id).all()
        latest = max(scores, key=lambda s: (s.year, SEASON_ORDER[s.season]))

        # Use cached analysis if available to avoid duplicate Gemma call
        curriculum = get_cached_analysis(student.id, db)
        if curriculum is None:
            score_inputs = [ScoreInput(rit_score=s.rit_score, season=s.season, year=s.year) for s in scores]
            curriculum = map_rit_to_curriculum(latest.rit_score, score_inputs)

        # Check weak concepts from prior sessions
        weak = _get_weak_concepts(student.id, db)

        try:
            progress(0.4, desc="Gemma 4 E4B generating exercises...")
            exercises = generate_exercises(
                student_name=student.name,
                grade=student.grade,
                band=curriculum.introduce_band,
                num_questions=int(num_questions),
                weak_concepts=weak,
            )
            progress(0.9, desc="Exercises ready!")
        except Exception as e:
            return f"**Error generating exercises:** {e}", "", "", gr.update(interactive=False)

        # Create session in DB
        session = PracticeSession(
            student_id=student.id,
            band=curriculum.introduce_band.band,
            total_questions=len(exercises.exercises),
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        current_exercises = exercises.exercises
        current_exercise_idx = 0
        current_session_id = session.id
        current_band = curriculum.introduce_band.band
        current_rit = latest.rit_score
        session_results = []

        return _format_exercise(0)
    except Exception as e:
        return f"**Error:** {e}", "", "", gr.update(interactive=False)
    finally:
        db.close()


def _format_exercise(idx):
    """Format the current exercise for display with enhanced UI."""
    if idx >= len(current_exercises):
        return _show_results()

    ex = current_exercises[idx]
    progress_html = f'<div style="margin-bottom: 1rem;"><span class="pill pill-primary">Question {idx + 1} of {len(current_exercises)}</span>'
    band_html = f'<span class="pill pill-secondary">RIT Band: {current_band}</span>'
    topic_html = f'<span class="pill pill-neutral">{ex.topic}</span></div>'
    
    header = f"{progress_html}{band_html}{topic_html}"
    
    question_text = f"{header}\n\n### {ex.concept}\n\n{ex.question}\n\n---\n"

    if ex.question_type == "multiple_choice" and ex.choices:
        choices_text = "\n".join(f"  {chr(65+i)}) {c}" for i, c in enumerate(ex.choices))
        question_text += f"\n{choices_text}"
    elif ex.question_type == "fill_in_the_blank":
        question_text += "\n*Type your answer below.*"
    else:
        question_text += "\n*Type your answer below.*"

    return (
        question_text,
        "",  # clear answer box
        "",  # clear feedback
        gr.update(interactive=True),  # enable submit button
    )


def submit_answer(answer):
    """Check the answer and show feedback with styled containers."""
    global current_exercise_idx

    if current_exercise_idx >= len(current_exercises):
        return _show_results()

    ex = current_exercises[current_exercise_idx]

    # Simple answer checking
    student_ans = answer.strip().lower()
    correct_ans = ex.correct_answer.strip().lower()

    # Normalize for multiple choice
    is_correct = False
    if student_ans:
        if ex.question_type == "multiple_choice" and ex.choices:
            letter_map = {chr(65+i).lower(): c.lower() for i, c in enumerate(ex.choices)}
            if student_ans in letter_map:
                is_correct = letter_map[student_ans] == correct_ans
            else:
                is_correct = student_ans == correct_ans or student_ans in correct_ans
        else:
            is_correct = student_ans == correct_ans or correct_ans in student_ans or student_ans in correct_ans

    session_results.append({
        "concept": ex.concept,
        "topic": ex.topic,
        "question": ex.question,
        "student_answer": answer.strip(),
        "correct_answer": ex.correct_answer,
        "is_correct": is_correct,
    })

    # Save to database
    if current_session_id:
        db = SessionLocal()
        try:
            record = ExerciseResultRecord(
                session_id=current_session_id,
                concept=ex.concept,
                topic=ex.topic,
                question=ex.question,
                student_answer=answer.strip(),
                correct_answer=ex.correct_answer,
                is_correct=is_correct,
            )
            db.add(record)
            db.commit()
        finally:
            db.close()

    if is_correct:
        feedback = f'<div class="feedback-correct"><h3>✅ Correct!</h3><p>{ex.explanation}</p></div>'
    else:
        feedback = f'<div class="feedback-incorrect"><h3>❌ Not quite.</h3><p><b>Your answer:</b> {answer}<br><b>Correct answer:</b> {ex.correct_answer}</p><p style="margin-top:0.5rem;">{ex.explanation}</p></div>'

    current_exercise_idx += 1

    if current_exercise_idx >= len(current_exercises):
        feedback += "\n\n---\n\n*Session complete! Click 'Next Question' to see your results.*"

    return (
        gr.update(),  # keep question visible
        gr.update(),  # keep answer visible
        feedback,
        gr.update(interactive=True),
    )


def next_question():
    """Move to the next question or show results."""
    if current_exercise_idx >= len(current_exercises):
        return _show_results()
    return _format_exercise(current_exercise_idx)


def _show_results():
    """Show session results summary."""
    if not session_results:
        return "No results yet.", "", "", gr.update(interactive=False)

    correct = sum(1 for r in session_results if r["is_correct"])
    total = len(session_results)
    pct = (correct / total * 100) if total > 0 else 0

    # Per-concept breakdown
    concept_scores = {}
    for r in session_results:
        c = r["concept"]
        if c not in concept_scores:
            concept_scores[c] = {"correct": 0, "total": 0}
        concept_scores[c]["total"] += 1
        if r["is_correct"]:
            concept_scores[c]["correct"] += 1

    breakdown = "\n".join(
        f"  - **{c}**: {d['correct']}/{d['total']} correct"
        for c, d in concept_scores.items()
    )

    # Update session in DB
    if current_session_id:
        db = SessionLocal()
        try:
            from datetime import datetime, timezone
            session = db.query(PracticeSession).filter(PracticeSession.id == current_session_id).first()
            if session:
                session.correct = correct
                session.total_questions = total
                session.score_pct = pct
                session.concept_scores = concept_scores
                session.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    # Identify weak concepts for adaptive follow-up
    weak = [c for c, d in concept_scores.items() if d["total"] > 0 and d["correct"] / d["total"] < 0.8]

    if weak and pct < 100:
        weak_list = ", ".join(f"**{c}**" for c in weak)
        follow_up = f"\n\n### Recommended Follow-Up\nYou struggled with {weak_list}. Click **Start Practice** again — the next session will prioritize these concepts."
    else:
        follow_up = "\n\n### Great Job!\nAll concepts at 80%+ mastery. Try increasing the question count for a challenge!"

    results_text = f"""## Session Complete!

**Score: {correct}/{total} ({pct:.0f}%)**

### Concept Breakdown
{breakdown}
{follow_up}"""

    return results_text, "", "", gr.update(interactive=False)


def get_progress_report(student_id, progress=gr.Progress()):
    """Generate a progress report for the student."""
    if not student_id:
        return "Register a student first."

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == int(student_id)).first()
        if not student:
            return "Student not found."

        scores = db.query(Score).filter(Score.student_id == student.id).all()
        if not scores:
            return "No scores found."

        latest = max(scores, key=lambda s: (s.year, SEASON_ORDER[s.season]))

        # Use cached trend if available to avoid Gemma call
        cached = get_cached_analysis(student.id, db)
        if cached:
            trend = cached.trend
        else:
            score_inputs = [ScoreInput(rit_score=s.rit_score, season=s.season, year=s.year) for s in scores]
            trend, _ = detect_trend(score_inputs)

        sessions = db.query(PracticeSession).filter(
            PracticeSession.student_id == student.id,
            PracticeSession.completed_at.isnot(None),
        ).all()

        if not sessions:
            return "No completed practice sessions yet. Complete a practice session first to get a report."

        # Aggregate mastery
        concept_totals = {}
        for s in sessions:
            for concept, data in (s.concept_scores or {}).items():
                if concept not in concept_totals:
                    concept_totals[concept] = {"correct": 0, "total": 0}
                concept_totals[concept]["correct"] += data.get("correct", 0)
                concept_totals[concept]["total"] += data.get("total", 0)

        mastered = [c for c, d in concept_totals.items() if d["total"] > 0 and d["correct"] / d["total"] >= 0.8]
        needs_work = [c for c, d in concept_totals.items() if d["total"] > 0 and d["correct"] / d["total"] < 0.8]

        from src.models.schemas import StudentProgress
        student_progress = StudentProgress(
            student_name=student.name,
            grade=student.grade,
            latest_rit=latest.rit_score,
            trend=trend,
            sessions=[],
            mastered_concepts=mastered,
            needs_work_concepts=needs_work,
        )

        progress(0.5, desc="Gemma 4 E4B generating report...")
        report = generate_report(student_progress)
        return f"## Progress Report for {student.name}\n\n{report}"
    finally:
        db.close()


def _get_weak_concepts(student_id, db):
    """Find concepts where the student scored < 80%."""
    sessions = db.query(PracticeSession).filter(
        PracticeSession.student_id == student_id,
        PracticeSession.completed_at.isnot(None),
    ).all()

    concept_totals = {}
    for s in sessions:
        for concept, data in (s.concept_scores or {}).items():
            if concept not in concept_totals:
                concept_totals[concept] = {"correct": 0, "total": 0}
            concept_totals[concept]["correct"] += data.get("correct", 0)
            concept_totals[concept]["total"] += data.get("total", 0)

    return [
        c for c, d in concept_totals.items()
        if d["total"] > 0 and d["correct"] / d["total"] < 0.8
    ]


# --- Build the UI ---

theme = gr.themes.Soft(
    primary_hue=gr.themes.colors.indigo,
    secondary_hue=gr.themes.colors.emerald,
    text_size=gr.themes.sizes.text_lg,
    font=("Nunito", "Inter", "system-ui", "-apple-system", "sans-serif"),
    font_mono=("JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"),
)
theme.custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');
.gradio-container { background-color: #f9fafb !important; font-family: 'Nunito', 'Inter', system-ui, sans-serif !important; }
.tabitem { border-radius: 16px !important; padding: 2rem !important; border: 1px solid #e5e7eb !important; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1) !important; margin-top: 1rem; }
.card-section { background: white; border-radius: 12px; padding: 1.5rem; border: 1px solid #f3f4f6; margin-bottom: 1rem; }
.pill { display: inline-block; padding: 5px 14px; border-radius: 9999px; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.025em; margin-right: 0.5rem; }
.pill-primary { background-color: #e0e7ff; color: #4338ca; }
.pill-secondary { background-color: #ecfdf5; color: #047857; }
.pill-neutral { background-color: #f3f4f6; color: #374151; }
button.primary { background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important; border: none !important; color: white !important; transition: all 0.2s ease; }
button.primary:hover { transform: translateY(-1px); box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.4); }
.analysis-output h2 { color: #1e1b4b; border-bottom: 2px solid #e0e7ff; padding-bottom: 0.5rem; margin-top: 1.5rem; }
.feedback-correct { background-color: #f0fdf4; border-left: 4px solid #22c55e; padding: 1rem; border-radius: 8px; }
.feedback-incorrect { background-color: #fff7ed; border-left: 4px solid #f97316; padding: 1rem; border-radius: 8px; }

/* Curriculum band cards */
.band-card { background: white; border-radius: 12px; padding: 1.5rem; border: 1px solid #e5e7eb; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.band-develop { border-left: 4px solid #6366f1; }
.band-introduce { border-left: 4px solid #10b981; }
.band-header { font-size: 1.3rem; font-weight: 800; color: #1e1b4b; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; letter-spacing: -0.01em; }
.band-icon { font-size: 1.4rem; }
.band-badge { font-size: 0.72rem; font-weight: 700; padding: 4px 12px; border-radius: 9999px; margin-left: auto; text-transform: uppercase; letter-spacing: 0.03em; }
.band-badge.develop { background: #e0e7ff; color: #4338ca; }
.band-badge.introduce { background: #d1fae5; color: #065f46; }
.band-subtitle { color: #6b7280; font-size: 0.92rem; margin: 0.35rem 0 1rem 0; }
.topic-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 0.75rem; }
.topic-card { background: #f9fafb; border: 1px solid #f3f4f6; border-radius: 12px; padding: 1rem 1.1rem; }
.topic-name { font-weight: 700; color: #374151; margin-bottom: 0.5rem; font-size: 0.95rem; }
.concept-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.concept-chip { background: #e0e7ff; color: #3730a3; font-size: 0.8rem; padding: 3px 10px; border-radius: 8px; font-weight: 600; }
.trend-list { list-style: none; padding: 0; margin: 0.75rem 0 0 0; display: flex; flex-direction: column; gap: 0.6rem; }
.trend-item { background: #f9fafb; border: 1px solid #f3f4f6; border-radius: 10px; padding: 0.85rem 1.1rem; color: #374151; font-size: 0.95rem; line-height: 1.6; }
"""

custom_css = theme.custom_css

with gr.Blocks(title="MAP Accelerator") as demo:
    gr.HTML("""
        <div style="text-align: center; padding: 2rem 0;">
            <h1 style="font-size: 2.5rem; font-weight: 800; color: #1e1b4b; margin-bottom: 0.5rem;">MAP Accelerator</h1>
            <p style="font-size: 1.125rem; color: #6b7280; max-width: 600px; margin: 0 auto;">Personalized math practice for advanced students, powered by Gemma 4</p>
        </div>
    """)

    student_id_state = gr.State("")

    with gr.Tabs():
        # --- Tab 1: Student Registration ---
        with gr.Tab("1. Enter Scores"):
            gr.Markdown("### Load Existing Student")
            with gr.Row():
                student_dropdown = gr.Dropdown(
                    choices=list(get_existing_students().keys()),
                    label="Select Student",
                    interactive=True,
                    scale=3,
                )
                load_btn = gr.Button("Load Student", variant="primary", scale=1)
                refresh_btn = gr.Button("Refresh List", variant="secondary", scale=1)

            gr.Markdown("---")

            gr.Markdown("### Student Details")
            with gr.Row():
                name_input = gr.Textbox(label="Student Name", placeholder="e.g., Alex", scale=3)
                grade_input = gr.Dropdown(choices=["KG", "1", "2", "3", "4", "5"], label="Current Grade", value="3", scale=1)

            gr.Markdown("### Upload Score Report *(optional — auto-fills scores below)*")
            with gr.Row():
                score_file = gr.File(
                    label="Upload MAP score image or PDF",
                    file_types=[".png", ".jpg", ".jpeg", ".pdf", ".webp", ".bmp"],
                    scale=3,
                )
                extract_btn = gr.Button("Extract Scores with Gemma 4", variant="secondary", scale=1)
            extract_status = gr.Markdown("")

            gr.Markdown("### MAP Scores")
            gr.Markdown("*Enter scores below or upload an image/PDF above. Add/remove rows as needed.*")

            # State holds list of dicts: [{"rit": 185, "season": "winter", "year": 2025, "grade": "3"}, ...]
            scores_state = gr.State(value=[{"rit": 185, "season": "winter", "year": 2025, "grade": "3"}])

            @gr.render(inputs=scores_state)
            def render_score_rows(scores_list):
                rits, seasons, years, grades_at = [], [], [], []
                for i, score in enumerate(scores_list):
                    with gr.Row():
                        rit = gr.Number(
                            value=score.get("rit", 0),
                            label=f"RIT Score" if i == 0 else f"RIT Score ({i + 1})",
                            precision=0,
                            key=f"rit_{i}",
                            interactive=True,
                        )
                        season = gr.Dropdown(
                            choices=["fall", "winter", "spring"],
                            value=score.get("season", "fall"),
                            label="Season",
                            key=f"season_{i}",
                            interactive=True,
                        )
                        year = gr.Number(
                            value=score.get("year", 2025),
                            label="Year",
                            precision=0,
                            key=f"year_{i}",
                            interactive=True,
                        )
                        grade_at = gr.Dropdown(
                            choices=["KG", "1", "2", "3", "4", "5"],
                            value=str(score.get("grade", "3")),
                            label="Grade",
                            key=f"grade_{i}",
                            interactive=True,
                        )
                        rits.append(rit)
                        seasons.append(season)
                        years.append(year)
                        grades_at.append(grade_at)

                # Wire analyze button inside @gr.render so it reads dynamic components
                def _collect_scores(*args) -> list[dict]:
                    n = len(args) // 4
                    scores_data = []
                    for j in range(n):
                        scores_data.append({
                            "rit": args[j],
                            "season": args[n + j],
                            "year": args[2 * n + j],
                            "grade": args[3 * n + j],
                        })
                    return scores_data

                def collect_and_analyze(name, grade, *args):
                    scores_data = _collect_scores(*args)
                    try:
                        return register_student(name, grade, scores_data)
                    except Exception as e:
                        logger.error("register_and_analyze failed: %s", traceback.format_exc())
                        return f"Error: {e}", "", "", None

                def refresh_student_list():
                    return gr.update(choices=list(get_existing_students().keys()))

                register_btn.click(
                    fn=collect_and_analyze,
                    inputs=[name_input, grade_input] + rits + seasons + years + grades_at,
                    outputs=[status_output, analysis_output, student_id_state, score_chart],
                ).then(
                    fn=refresh_student_list,
                    inputs=[],
                    outputs=[student_dropdown],
                    show_progress="hidden",
                )


            with gr.Row():
                add_row_btn = gr.Button("+ Add Score Row", variant="secondary", size="sm")
                remove_row_btn = gr.Button("- Remove Last Row", variant="secondary", size="sm")

            def add_score_row(current_scores):
                return current_scores + [{"rit": 0, "season": "fall", "year": 2025, "grade": "3"}]

            def remove_score_row(current_scores):
                if len(current_scores) > 1:
                    return current_scores[:-1]
                return current_scores

            add_row_btn.click(fn=add_score_row, inputs=[scores_state], outputs=[scores_state])
            remove_row_btn.click(fn=remove_score_row, inputs=[scores_state], outputs=[scores_state])

            with gr.Row():
                register_btn = gr.Button("Analyze", variant="primary", size="lg")
            status_output = gr.Markdown(value="*Status: Ready to analyze scores.*")
            score_chart = gr.Plot(label="Growth Trajectory")
            analysis_output = gr.Markdown(label="Analysis")

            def extract_from_file(file_path: str | None) -> tuple:
                """Extract scores from an uploaded image or PDF via Gemma 4 vision."""
                if file_path is None:
                    return gr.update(), gr.update(), gr.update(), "No file uploaded."
                try:
                    result = extract_scores_from_file(file_path)
                except Exception as e:
                    logger.error("Score extraction failed: %s", traceback.format_exc())
                    return gr.update(), gr.update(), gr.update(), f"Extraction failed: {e}"

                if not result["scores"]:
                    return gr.update(), gr.update(), gr.update(), (
                        "No MAP scores found in the image. "
                        "Please try a clearer screenshot."
                    )

                new_scores = []
                for s in result["scores"]:
                    new_scores.append({
                        "rit": s["rit_score"],
                        "season": s["season"],
                        "year": s["year"],
                        "grade": str(s["grade"]) if s.get("grade") is not None else "3",
                    })

                name_update = gr.update(value=result["student_name"]) if result.get("student_name") else gr.update()
                # Use explicit grade if provided, otherwise infer from most recent score
                current_grade = result.get("grade")
                if current_grade is None and new_scores:
                    first_grade = new_scores[0].get("grade")
                    if first_grade is not None and str(first_grade).strip():
                        current_grade = first_grade
                if current_grade is not None:
                    grade_str = "KG" if str(current_grade) == "KG" or current_grade == 0 else str(current_grade)
                    grade_update = gr.update(value=grade_str)
                else:
                    grade_update = gr.update()
                count = len(new_scores)
                status = f"Extracted **{count}** score(s). Review and edit below, then click Analyze."

                return new_scores, name_update, grade_update, status

            extract_btn.click(
                fn=extract_from_file,
                inputs=[score_file],
                outputs=[scores_state, name_input, grade_input, extract_status],
            )

            load_btn.click(
                fn=load_student,
                inputs=[student_dropdown],
                show_progress="hidden",
                outputs=[
                    status_output, analysis_output, student_id_state, score_chart,
                    register_btn, name_input, grade_input, scores_state,
                ],
            )

            def refresh_student_list_btn():
                return (
                    gr.update(choices=list(get_existing_students().keys()), value=None),
                    "",         # name
                    "3",        # grade
                    _default_scores_data(),  # scores
                    "",         # status
                    "",         # analysis
                    None,       # chart
                    gr.update(value="Analyze"),  # button label
                )

            refresh_btn.click(
                fn=refresh_student_list_btn,
                inputs=[],
                outputs=[
                    student_dropdown, name_input, grade_input, scores_state,
                    status_output, analysis_output, score_chart, register_btn,
                ],
            )

        # --- Tab 2: Practice ---
        with gr.Tab("2. Practice"):
            with gr.Row():
                num_q_input = gr.Slider(minimum=3, maximum=10, value=5, step=1, label="Number of Questions", scale=3)
                start_btn = gr.Button("Start Practice", variant="primary", scale=1)

            question_display = gr.Markdown(label="Question")
            answer_input = gr.Textbox(label="Your Answer", placeholder="Type your answer here...", lines=2)
            with gr.Row():
                submit_btn = gr.Button("Submit Answer", variant="primary", scale=2)
                next_btn = gr.Button("Next Question", variant="secondary", scale=1)

            feedback_display = gr.Markdown(label="Feedback")

            start_btn.click(
                fn=start_practice,
                inputs=[student_id_state, num_q_input],
                outputs=[question_display, answer_input, feedback_display, submit_btn],
            )

            submit_btn.click(
                fn=submit_answer,
                inputs=[answer_input],
                outputs=[question_display, answer_input, feedback_display, submit_btn],
            )

            next_btn.click(
                fn=next_question,
                inputs=[],
                outputs=[question_display, answer_input, feedback_display, submit_btn],
            )

        # --- Tab 3: Report ---
        with gr.Tab("3. Progress Report"):
            report_btn = gr.Button("Generate Report", variant="primary")
            report_output = gr.Markdown(label="Report")

            report_btn.click(
                fn=get_progress_report,
                inputs=[student_id_state],
                outputs=[report_output],
            )


if __name__ == "__main__":
    demo.launch(server_port=7860, theme=theme, css=custom_css)
