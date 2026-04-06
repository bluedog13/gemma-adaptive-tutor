"""Gradio frontend for MAP Accelerator."""

import html
import logging
import logging.handlers
import re
import traceback

from markdown_it import MarkdownIt

_md = MarkdownIt()

import gradio as gr

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)

# Rolling file log: 5 MB per file, keep 3 backups (logs/map_accelerator.log)
_log_dir = __import__("pathlib").Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    _log_dir / "map_accelerator.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
_file_handler.setLevel(logging.DEBUG)

logger = logging.getLogger("map_accelerator")
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from src.constants import SEASON_ORDER, SUBJECTS
from src.models.database import (
    init_db,
    SessionLocal,
    Student,
    Score,
    PracticeSession,
    ExerciseResultRecord,
    compute_scores_hash,
)
from src.models.schemas import (
    CurriculumResult,
    ScoreInput,
    SUBJECT_DISPLAY,
)
from src.tools.curriculum import (
    map_rit_to_curriculum,
    detect_trend,
    get_cached_analysis,
    get_cached_scores_hash,
    save_analysis_cache,
)
from src.tools.exercise_generator import generate_exercises, generate_report
from src.tools.score_extractor import extract_all_subjects_from_file


def _grade_to_int(grade: str | int) -> int:
    """Convert a grade value to integer, handling 'KG' as 0."""
    if isinstance(grade, int):
        return grade
    g = str(grade).strip().upper()
    return 0 if g == "KG" else int(g)


# Initialize database
init_db()


def _empty_practice_state() -> dict:
    """Return a fresh per-client practice state dict."""
    return {
        "exercises": [],
        "exercise_idx": 0,
        "session_id": None,
        "band": "",
        "rit": 0,
        "results": [],
    }


def _grade_for_score(
    season: str, year: int, current_grade: int, latest_season: str, latest_year: int
) -> int:
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


def create_score_chart(
    scores_data, student_name, current_grade, trend=None, subject="math"
):
    """Create a chart showing actual scores vs NWEA national norms.

    scores_data entries must have: rit_score, season, year, and optionally grade.
    If grade is missing, it's computed from current_grade and school year logic.
    """
    from src.constants import NWEA_PERCENTILES, estimate_percentile

    subject_display = SUBJECT_DISPLAY.get(subject, subject.title())

    # Sort chronologically: winter (Jan) < spring (Apr) < fall (Sep)
    _CHRONO_ORDER = {"winter": 0, "spring": 1, "fall": 2}
    sorted_scores = sorted(
        scores_data, key=lambda s: (s["year"], _CHRONO_ORDER[s["season"]])
    )
    latest = sorted_scores[-1]

    # Get the grade for each score — use explicit grade if provided, else compute
    grades_per_score = []
    for s in sorted_scores:
        if "grade" in s and s["grade"] is not None:
            grades_per_score.append(_grade_to_int(s["grade"]))
        else:
            grades_per_score.append(
                _grade_for_score(
                    s["season"],
                    s["year"],
                    _grade_to_int(current_grade),
                    latest["season"],
                    latest["year"],
                )
            )

    labels = [
        f"{s['season'].capitalize()} {s['year']}\n({'KG' if grades_per_score[i] == 0 else f'G{grades_per_score[i]}'})"
        for i, s in enumerate(sorted_scores)
    ]
    actual = [s["rit_score"] for s in sorted_scores]

    if subject not in NWEA_PERCENTILES:
        raise ValueError(
            f"No NWEA percentile data for subject '{subject}'. "
            f"Available: {list(NWEA_PERCENTILES.keys())}"
        )
    subj_pcts = NWEA_PERCENTILES[subject]

    # Build norm lines using the correct grade for each score
    norm_50th, norm_75th, norm_90th, norm_95th = [], [], [], []
    for i, s in enumerate(sorted_scores):
        g = max(0, min(grades_per_score[i], 5))  # clamp to data range
        pcts = subj_pcts.get(g, subj_pcts[3])
        norm_50th.append(pcts[s["season"]][50])
        norm_75th.append(pcts[s["season"]][75])
        norm_90th.append(pcts[s["season"]][90])
        norm_95th.append(pcts[s["season"]][95])

    # Compute expected growth line and next-exam target before plotting
    expected_line = []
    next_expected = None
    if len(actual) >= 2:
        first_g = max(0, min(grades_per_score[0], 5))
        first_rit = actual[0]
        start_pct = estimate_percentile(
            first_rit, first_g, sorted_scores[0]["season"], subject
        )

        pct_keys = [
            5,
            10,
            15,
            20,
            25,
            30,
            35,
            40,
            45,
            50,
            55,
            60,
            65,
            70,
            75,
            80,
            85,
            90,
            95,
        ]
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

        expected_line = [first_rit]
        for i in range(1, len(sorted_scores)):
            g = max(0, min(grades_per_score[i], 5))
            pcts = subj_pcts.get(g, subj_pcts[3])
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

        next_pcts = subj_pcts.get(next_grade, subj_pcts[3])
        next_season_pcts = next_pcts[next_season]
        next_expected = round(
            next_season_pcts[lower_pct]
            + frac * (next_season_pcts[upper_pct] - next_season_pcts[lower_pct])
        )
        expected_line.append(next_expected)

        next_label = f"{next_season.capitalize()} {next_year}\n({'KG' if next_grade == 0 else f'G{next_grade}'})"
        labels.append(next_label)

        norm_50th.append(next_pcts[next_season][50])
        norm_75th.append(next_pcts[next_season][75])
        norm_90th.append(next_pcts[next_season][90])
        norm_95th.append(next_pcts[next_season][95])

    fig, ax = plt.subplots(figsize=(12, 6))

    # Shade percentile bands
    ax.fill_between(
        range(len(labels)),
        norm_50th,
        norm_75th,
        alpha=0.08,
        color="#6B7280",
        label="50th-75th percentile",
    )
    ax.fill_between(
        range(len(labels)),
        norm_75th,
        norm_90th,
        alpha=0.08,
        color="#4F46E5",
        label="75th-90th percentile",
    )
    ax.fill_between(
        range(len(labels)),
        norm_90th,
        norm_95th,
        alpha=0.06,
        color="#7C3AED",
        label="90th-95th percentile",
    )

    # Plot norm lines
    ax.plot(labels, norm_50th, "--", color="#9CA3AF", linewidth=1.5)
    ax.plot(labels, norm_75th, "--", color="#6B7280", linewidth=1.5)
    ax.plot(labels, norm_90th, "--", color="#A78BFA", linewidth=1.5)
    ax.plot(labels, norm_95th, "--", color="#7C3AED", linewidth=1.5)

    # Inline percentile labels on the left side of the chart
    ax.annotate(
        "50th",
        (labels[0], norm_50th[0]),
        textcoords="offset points",
        xytext=(-8, 0),
        ha="right",
        fontsize=9,
        color="#9CA3AF",
        fontweight="bold",
    )
    ax.annotate(
        "75th",
        (labels[0], norm_75th[0]),
        textcoords="offset points",
        xytext=(-8, 0),
        ha="right",
        fontsize=9,
        color="#6B7280",
        fontweight="bold",
    )
    ax.annotate(
        "90th",
        (labels[0], norm_90th[0]),
        textcoords="offset points",
        xytext=(-8, 0),
        ha="right",
        fontsize=9,
        color="#A78BFA",
        fontweight="bold",
    )
    ax.annotate(
        "95th",
        (labels[0], norm_95th[0]),
        textcoords="offset points",
        xytext=(-8, 0),
        ha="right",
        fontsize=9,
        color="#7C3AED",
        fontweight="bold",
    )

    # Plot expected growth line + next-exam target
    if expected_line:
        ax.plot(
            labels,
            expected_line,
            "o:",
            color="#059669",
            linewidth=2,
            markersize=5,
            alpha=0.7,
            zorder=2,
        )
        all_vals_extra = expected_line
    else:
        all_vals_extra = []

    # Plot actual scores (on top)
    actual_labels = labels[: len(actual)]
    ax.plot(
        actual_labels,
        actual,
        "o-",
        color="#4F46E5",
        linewidth=2.5,
        markersize=8,
        label=f"{student_name}",
        zorder=3,
    )

    for i, v in enumerate(actual):
        exp_v = expected_line[i] if i < len(expected_line) else None

        ax.annotate(
            str(v),
            (labels[i], v),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=10,
            fontweight="bold",
            color="#4F46E5",
        )

        if exp_v is None or i == 0 or exp_v == v:
            continue

        gap = exp_v - v
        if abs(gap) >= 12:
            ax.annotate(
                str(exp_v),
                (labels[i], exp_v),
                textcoords="offset points",
                xytext=(0, -14),
                ha="center",
                fontsize=8,
                fontweight="bold",
                color="#059669",
            )
        else:
            ax.annotate(
                str(exp_v),
                (labels[i], exp_v),
                textcoords="offset points",
                xytext=(18, 0),
                ha="left",
                fontsize=8,
                fontweight="bold",
                color="#059669",
            )

    # Label the future target point
    if expected_line and len(expected_line) > len(actual):
        ti = len(expected_line) - 1
        tv = expected_line[ti]
        ax.annotate(
            f"Target: {tv}",
            (labels[ti], tv),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=9,
            color="#059669",
            fontweight="bold",
        )

    # Style
    ax.set_ylabel("RIT Score", fontsize=11)
    ax.set_title(
        f"{student_name} — {subject_display} Scores vs National Norms (NWEA 2025)",
        fontsize=13,
        fontweight="bold",
    )
    ax.legend(loc="lower right", fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    all_vals = actual + norm_50th + norm_95th + all_vals_extra
    ax.set_ylim(min(all_vals) - 5, max(all_vals) + 8)

    # Add trend annotation if available
    if trend and len(actual) >= 2:
        total_change = actual[-1] - actual[0]
        sign = "+" if total_change >= 0 else ""
        trend_colors = {
            "growing": "#059669",
            "stalling": "#D97706",
            "declining": "#DC2626",
        }
        trend_icons = {"growing": "\u2191", "stalling": "\u2192", "declining": "\u2193"}
        color = trend_colors.get(trend, "#6B7280")
        icon = trend_icons.get(trend, "")

        ax.annotate(
            f"{icon} {trend.capitalize()} ({sign}{total_change} RIT)",
            xy=(0.02, 0.98),
            xycoords="axes fraction",
            ha="left",
            va="top",
            fontsize=9,
            fontweight="bold",
            color=color,
            bbox=dict(
                boxstyle="round,pad=0.4",
                facecolor=color,
                alpha=0.1,
                edgecolor=color,
                linewidth=1,
            ),
        )

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


def load_student(selection, subject="math"):
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
        scores = (
            db.query(Score)
            .filter(Score.student_id == student.id, Score.subject == subject)
            .all()
        )

        if not scores:
            return ("No scores found.", "", student_id, None, btn_analyze) + tuple(
                empty
            )

        # Build dataframe rows from DB — most recent first, all scores
        sorted_db_scores = sorted(
            scores, key=lambda s: (s.year, SEASON_ORDER[s.season]), reverse=True
        )
        latest_db = sorted_db_scores[0]

        rows = []
        scores_with_grade = []
        for s in sorted_db_scores:
            if s.grade:
                sg = str(s.grade)
            else:
                sg = str(
                    _grade_for_score(
                        s.season,
                        s.year,
                        student.grade,
                        latest_db.season,
                        latest_db.year,
                    )
                )
            rows.append(
                {"rit": s.rit_score, "season": s.season, "year": s.year, "grade": sg}
            )
            scores_with_grade.append(
                {
                    "rit_score": s.rit_score,
                    "season": s.season,
                    "year": s.year,
                    "grade": _grade_to_int(sg),
                }
            )

        # Check for cached analysis
        current_hash = compute_scores_hash(scores_with_grade, student.grade)
        cached_hash = get_cached_scores_hash(student.id, db, subject)
        cached = get_cached_analysis(student.id, db, subject)

        analysis_html = ""
        chart = None
        if cached and cached_hash == current_hash:
            analysis_html = _build_analysis_html(
                student.name,
                str(student.grade),
                cached,
                subject,
            )
            if len(scores_with_grade) >= 2:
                chart = create_score_chart(
                    scores_with_grade,
                    student.name,
                    student.grade,
                    trend=cached.trend.value if cached.trend else None,
                    subject=subject,
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
            status = f"Loaded '{student.name}' — click Analyze to run Gemma 4 analysis."
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


def _parse_scores_list(
    scores_data: list[dict], default_grade: int
) -> tuple[list[ScoreInput], list[dict]]:
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
        scores_with_grade.append(
            {
                "rit_score": rit,
                "season": season,
                "year": year,
                "grade": sg,
            }
        )

    return scores, scores_with_grade


def _build_analysis_html(
    name: str, grade: str | int, curriculum: CurriculumResult, subject: str = "math"
) -> str:
    """Build the HTML analysis cards from a CurriculumResult.

    :param name: Student name.
    :param grade: Display grade (string or int).
    :param curriculum: CurriculumResult with bands and trend.
    :param subject: Subject key.
    :return: HTML string.
    """
    subject_display = SUBJECT_DISPLAY.get(subject, subject.title())

    develop_cards = []
    for topic, concepts in curriculum.develop_band.topics.items():
        concept_chips = "".join(
            f'<span class="concept-chip">{c}</span>' for c in concepts
        )
        develop_cards.append(
            f'<div class="topic-card">'
            f'<div class="topic-name">{topic}</div>'
            f'<div class="concept-chips">{concept_chips}</div>'
            f"</div>"
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
            f"</div>"
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
                    f'<li class="trend-item"><strong>{heading}:</strong> {body}</li>'
                )
            else:
                trend_items.append(f'<li class="trend-item">{section}</li>')

        trend_list = (
            f'<ul class="trend-list">{"".join(trend_items)}</ul>'
            if trend_items
            else f'<p style="color: #374151; margin: 0;">{raw}</p>'
        )
        trend_html = (
            f'<div class="band-card" style="border-left: 4px solid #6366f1;">'
            f'<div class="band-header">'
            f'<span class="band-icon">📈</span> Growth Trend'
            f"</div>"
            f"{trend_list}</div>"
        )

    develop_body = (
        "".join(develop_cards)
        if develop_cards
        else '<p style="color:#9ca3af;">No specific topics listed</p>'
    )
    introduce_body = "".join(introduce_cards)

    return f"""<div style="margin-bottom: 1.5rem;">
    <h1 style="color:#1e1b4b; margin-bottom: 0.75rem;">Analysis for {name} — {subject_display}</h1>
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
    name: str,
    grade: str,
    scores_data: list[dict],
    force_refresh: bool = False,
    subject: str = "math",
) -> tuple:
    """Register a new student or analyze an existing one.

    :param name: Student name.
    :param grade: Current grade level as string.
    :param scores_data: List of dicts with keys rit, season, year, grade.
    :param force_refresh: If True, always re-run Gemma analysis.
    :param subject: Subject for this analysis.
    :return: Tuple of (status_msg, analysis, student_id, chart).
    """
    logger.info(
        "register_student called: name=%s, grade=%s, subject=%s, force=%s",
        name,
        grade,
        subject,
        force_refresh,
    )
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
            logger.info(
                "Found existing student: id=%s, name=%s", student.id, student.name
            )
            student.grade = _grade_to_int(grade)

            # Replace all existing scores for this subject with the new set
            db.query(Score).filter(
                Score.student_id == student.id,
                Score.subject == subject,
            ).delete()
            for swg in scores_with_grade:
                db.add(
                    Score(
                        student_id=student.id,
                        rit_score=swg["rit_score"],
                        season=swg["season"],
                        year=swg["year"],
                        grade=swg["grade"],
                        subject=subject,
                    )
                )
            db.commit()
            status_msg = f"Analyzing scores for '{student.name}'..."
        else:
            student = Student(name=name.strip(), grade=_grade_to_int(grade))
            db.add(student)
            db.flush()

            for swg in scores_with_grade:
                db.add(
                    Score(
                        student_id=student.id,
                        rit_score=swg["rit_score"],
                        season=swg["season"],
                        year=swg["year"],
                        grade=swg["grade"],
                        subject=subject,
                    )
                )
            db.commit()
            db.refresh(student)
            status_msg = f"Student '{name}' registered with {len(scores)} score(s)."

        # Check cache
        current_hash = compute_scores_hash(scores_with_grade, _grade_to_int(grade))
        cached_hash = get_cached_scores_hash(student.id, db, subject)
        curriculum = None

        if not force_refresh and cached_hash == current_hash:
            curriculum = get_cached_analysis(student.id, db, subject)
            if curriculum:
                logger.info(
                    "Using cached analysis for student %s, subject %s",
                    student.id,
                    subject,
                )
                status_msg += " (cached — instant)"

        if curriculum is None:
            latest_score = max(
                scores,
                key=lambda s: (s.year, SEASON_ORDER[str(s.season.value)]),
            )
            curriculum = map_rit_to_curriculum(
                latest_score.rit_score,
                scores,
                grade=_grade_to_int(grade),
                subject=subject,
            )
            save_analysis_cache(
                student.id,
                curriculum,
                current_hash,
                _grade_to_int(grade),
                db,
                subject=subject,
            )
            logger.info(
                "Saved analysis cache for student %s, subject %s", student.id, subject
            )

        analysis = _build_analysis_html(name, grade, curriculum, subject)

        # Create chart if 2+ scores
        chart = None
        if len(scores_with_grade) >= 2:
            chart = create_score_chart(
                scores_with_grade,
                name.strip(),
                _grade_to_int(grade),
                trend=curriculum.trend.value if curriculum.trend else None,
                subject=subject,
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


def start_practice(student_id, num_questions, pstate, subject="math"):
    """Generate exercises and start a practice session.

    :param pstate: Per-client practice state dict (from ``gr.State``).
    :return: 7-tuple of (question, answer_input, answer_radio,
             answer_checkbox, feedback, submit_btn, updated_pstate).
    """
    logger.info(
        "start_practice called: student_id=%s, num_questions=%s, subject=%s",
        student_id,
        num_questions,
        subject,
    )

    if not student_id:
        return (
            "<p><b>Please go to the Scores tab and register a student first.</b></p>",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            "",
            gr.update(interactive=False),
            pstate,
        )

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == int(student_id)).first()
        if not student:
            return (
                "<p><b>Student not found.</b> Please register first.</p>",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                "",
                gr.update(interactive=False),
                pstate,
            )

        scores = (
            db.query(Score)
            .filter(Score.student_id == student.id, Score.subject == subject)
            .all()
        )
        if not scores:
            return (
                f"<p><b>No {SUBJECT_DISPLAY.get(subject, subject)} scores found.</b> Enter scores first.</p>",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                "",
                gr.update(interactive=False),
                pstate,
            )

        latest = max(scores, key=lambda s: (s.year, SEASON_ORDER[s.season]))

        # Use cached analysis if available
        curriculum = get_cached_analysis(student.id, db, subject)
        if curriculum is None:
            score_inputs = [
                ScoreInput(rit_score=s.rit_score, season=s.season, year=s.year)
                for s in scores
            ]
            curriculum = map_rit_to_curriculum(
                latest.rit_score, score_inputs, subject=subject
            )

        # Check weak concepts from prior sessions
        weak = _get_weak_concepts(student.id, db, subject)

        try:
            exercises = generate_exercises(
                student_name=student.name,
                grade=student.grade,
                band=curriculum.introduce_band,
                num_questions=int(num_questions),
                weak_concepts=weak,
                subject=subject,
            )
        except Exception as e:
            return (
                f"<p><b>Error generating exercises:</b> {html.escape(str(e))}</p>",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                "",
                gr.update(interactive=False),
                pstate,
            )

        # Create session in DB
        session = PracticeSession(
            student_id=student.id,
            band=curriculum.introduce_band.band,
            total_questions=len(exercises.exercises),
            subject=subject,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        pstate = {
            "exercises": [ex.model_dump() for ex in exercises.exercises],
            "exercise_idx": 0,
            "session_id": session.id,
            "band": curriculum.introduce_band.band,
            "rit": latest.rit_score,
            "results": [],
            "subject": subject,
        }

        result = _format_exercise(0, pstate)
        return (*result, pstate)
    except Exception as e:
        logger.error("start_practice failed: %s", traceback.format_exc())
        return (
            f"<p><b>Error:</b> {html.escape(str(e))}</p>",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            "",
            gr.update(interactive=False),
            pstate,
        )
    finally:
        db.close()


def _format_choices(ex: dict, subject: str) -> list[str]:
    """Format choice labels with letter/number prefixes.

    :param ex: Exercise dict.
    :param subject: Subject key.
    :return: List of formatted choice labels.
    """
    choices = []
    for i, c in enumerate(ex.get("choices") or []):
        c_stripped = re.sub(r"^[A-Za-z]\.\s*", "", c)
        c_stripped = re.sub(r"^\d+\.\s*", "", c_stripped)
        if subject == "reading":
            label = f"{i + 1}.  {c_stripped}"
        else:
            label = f"{chr(65 + i)}.  {c_stripped}"
        choices.append(label)
    return choices


def _build_question_html(
    idx: int,
    ex: dict,
    total: int,
    pstate: dict | None = None,
    part_label: str | None = None,
) -> str:
    """Build the common question HTML (topbar, progress bar, topic chip, question).

    :param idx: Current exercise index.
    :param ex: Exercise dict.
    :param total: Total number of exercises.
    :param pstate: Practice state dict (used for subject display).
    :param part_label: Optional "Part A" / "Part B" label.
    :return: HTML string.
    """
    concept = html.escape(ex["concept"])
    question = html.escape(ex["question"]).replace("\n", "<br>")
    subject = (pstate or {}).get("subject", "math")
    subject_emoji = {
        "math": "🔢",
        "language arts: reading": "📚",
        "science": "🔬",
    }.get(subject.lower(), "📖")
    from src.models.schemas import SUBJECT_DISPLAY as _SD

    subject_display = _SD.get(subject, subject.title())

    # Progress bar width as percentage
    progress_pct = int(((idx) / total) * 100) if total > 0 else 0

    topbar = (
        f'<div class="map-topbar">'
        f'<span class="map-topbar-subject">{subject_emoji} {subject_display}</span>'
        f"</div>"
        f'<div class="map-progress-area">'
        f'<div class="map-progress-bar-wrap">'
        f'<div class="map-progress-fill" style="width:{progress_pct}%"></div>'
        f"</div>"
        f'<span class="map-progress-label">{idx + 1} of {total}</span>'
        f"</div>"
    )

    scenario_html = ""
    if ex.get("scenario"):
        scenario_text = html.escape(ex["scenario"]).replace("\n", "<br>")
        scenario_html = (
            f'<div class="map-scenario-box">'
            f'<div class="map-scenario-label">📖 Read This First</div>'
            f"{scenario_text}</div>"
        )

    part_html = ""
    if part_label:
        part_html = f'<span class="map-part-label">{part_label}</span> '

    question_area = (
        f'<div class="map-question-area">'
        f'<div class="map-topic-chip">{concept}</div>'
        f"{scenario_html}"
        f"{part_html}"
        f'<p class="map-question-text">{question}</p>'
        f"</div>"
    )
    return f"{topbar}{question_area}"


def _hidden_all_inputs():
    """Return update tuples to hide textbox, radio, and checkbox."""
    return (
        gr.update(visible=False, value=""),
        gr.update(visible=False, value=None, choices=[]),
        gr.update(visible=False, value=None, choices=[]),
    )


def _format_mc(idx: int, ex: dict, total: int, pstate: dict) -> tuple:
    """Format a multiple-choice exercise.

    :param idx: Current exercise index.
    :param ex: Exercise dict.
    :param total: Total number of exercises.
    :param pstate: Practice state dict.
    :return: 6-tuple for display.
    """
    subject = pstate.get("subject", "math")
    if not ex.get("choices"):
        return _format_fill_blank(idx, ex, total, pstate)
    question_html = _build_question_html(idx, ex, total, pstate=pstate)
    choices = _format_choices(ex, subject)
    return (
        question_html,
        gr.update(visible=False, value=""),
        gr.update(choices=choices, value=None, visible=True, interactive=True),
        gr.update(visible=False, value=None, choices=[]),
        "",
        gr.update(interactive=True),
    )


def _format_multi_select(idx: int, ex: dict, total: int, pstate: dict) -> tuple:
    """Format a multi-select exercise.

    :param idx: Current exercise index.
    :param ex: Exercise dict.
    :param total: Total number of exercises.
    :param pstate: Practice state dict.
    :return: 6-tuple for display.
    """
    subject = pstate.get("subject", "math")
    if not ex.get("choices"):
        return _format_fill_blank(idx, ex, total, pstate)
    num_correct = ex.get("num_correct", 2)
    question_html = _build_question_html(idx, ex, total, pstate=pstate)
    question_html += f'<p class="map-instruction">Choose {num_correct} answers.</p>'
    choices = _format_choices(ex, subject)
    return (
        question_html,
        gr.update(visible=False, value=""),
        gr.update(visible=False, value=None, choices=[]),
        gr.update(choices=choices, value=None, visible=True, interactive=True),
        "",
        gr.update(interactive=True),
    )


def _format_two_part(idx: int, ex: dict, total: int, pstate: dict) -> tuple:
    """Format a two-part exercise (Part A).

    :param idx: Current exercise index.
    :param ex: Exercise dict.
    :param total: Total number of exercises.
    :param pstate: Practice state dict.
    :return: 6-tuple for display.
    """
    subject = pstate.get("subject", "math")
    if not ex.get("choices"):
        return _format_fill_blank(idx, ex, total, pstate)
    question_html = _build_question_html(
        idx, ex, total, pstate=pstate, part_label="Part A"
    )
    choices = _format_choices(ex, subject)
    return (
        question_html,
        gr.update(visible=False, value=""),
        gr.update(choices=choices, value=None, visible=True, interactive=True),
        gr.update(visible=False, value=None, choices=[]),
        "",
        gr.update(interactive=True),
    )


def _format_sequence(idx: int, ex: dict, total: int, pstate: dict) -> tuple:
    """Format a sequence-ordering exercise.

    :param idx: Current exercise index.
    :param ex: Exercise dict.
    :param total: Total number of exercises.
    :param pstate: Practice state dict.
    :return: 6-tuple for display.
    """
    if not ex.get("items_to_order"):
        return _format_fill_blank(idx, ex, total, pstate)
    question_html = _build_question_html(idx, ex, total, pstate=pstate)
    items_list = "".join(
        f"<li>{html.escape(item)}</li>" for item in ex["items_to_order"]
    )
    question_html += (
        f'<p class="map-instruction">'
        f"Put these in the correct order. Type the numbers "
        f"separated by commas (e.g., 2, 4, 1, 3).</p>"
        f"<ol>{items_list}</ol>"
    )
    return (
        question_html,
        gr.update(visible=True, value=""),
        gr.update(visible=False, value=None, choices=[]),
        gr.update(visible=False, value=None, choices=[]),
        "",
        gr.update(interactive=True),
    )


def _format_table(idx: int, ex: dict, total: int, pstate: dict) -> tuple:
    """Format a table-matching exercise.

    :param idx: Current exercise index.
    :param ex: Exercise dict.
    :param total: Total number of exercises.
    :param pstate: Practice state dict.
    :return: 6-tuple for display.
    """
    if not ex.get("match_pairs"):
        return _format_fill_blank(idx, ex, total, pstate)
    question_html = _build_question_html(idx, ex, total, pstate=pstate)
    options = ex.get("match_options", [])
    options_str = ", ".join(html.escape(o) for o in options)
    rows_html = ""
    for item in ex["match_pairs"]:
        rows_html += f"<tr><td>{html.escape(item)}</td><td>___</td></tr>"
    question_html += (
        f'<p class="map-instruction">'
        f"For each item, choose: {options_str}</p>"
        f'<table class="map-match-table">'
        f"<tr><th>Item</th><th>Category</th></tr>"
        f"{rows_html}</table>"
        f'<p class="map-instruction">'
        f"Type your answers separated by commas, in order "
        f"(e.g., {options_str}).</p>"
    )
    return (
        question_html,
        gr.update(visible=True, value=""),
        gr.update(visible=False, value=None, choices=[]),
        gr.update(visible=False, value=None, choices=[]),
        "",
        gr.update(interactive=True),
    )


def _format_fill_blank(idx: int, ex: dict, total: int, pstate: dict) -> tuple:
    """Format a fill-in-the-blank exercise (also used as fallback).

    :param idx: Current exercise index.
    :param ex: Exercise dict.
    :param total: Total number of exercises.
    :param pstate: Practice state dict.
    :return: 6-tuple for display.
    """
    question_html = _build_question_html(idx, ex, total, pstate=pstate)
    return (
        question_html,
        gr.update(visible=True, value=""),
        gr.update(visible=False, value=None, choices=[]),
        gr.update(visible=False, value=None, choices=[]),
        "",
        gr.update(interactive=True),
    )


_FORMATTERS: dict[str, callable] = {
    "multiple_choice": _format_mc,
    "multi_select": _format_multi_select,
    "two_part": _format_two_part,
    "sequence_order": _format_sequence,
    "table_matching": _format_table,
    "fill_in_the_blank": _format_fill_blank,
}


def _format_exercise(idx: int, pstate: dict):
    """Format the current exercise as MAP-styled HTML.

    Dispatches to the appropriate per-type formatter.

    :return: 6-tuple of (question_html, textbox_update, radio_update,
             checkbox_update, feedback_clear, submit_btn_update).
             Caller appends pstate.
    """
    exercises = pstate["exercises"]
    if idx >= len(exercises):
        return _show_results(pstate)

    ex = exercises[idx]
    q_type = ex.get("question_type", "multiple_choice")

    # Reset two-part state for new exercise
    pstate["current_part"] = "a"

    formatter = _FORMATTERS.get(q_type, _format_mc)
    return formatter(idx, ex, len(exercises), pstate)


def _grade_mc_answer(raw_answer: str, ex: dict, correct_ans: str) -> bool:
    """Grade a multiple-choice answer from radio selection.

    :param raw_answer: Raw radio label string.
    :param ex: Exercise dict with choices.
    :param correct_ans: Lowercased correct answer.
    :return: True if correct.
    """
    parts = raw_answer.split(".  ", 1)
    if len(parts) == 2:
        prefix = parts[0].strip()
        choice_text = parts[1].strip().lower()
        if prefix.isdigit():
            letter = chr(96 + int(prefix)) if int(prefix) >= 1 else ""
        else:
            letter = prefix.lower()
    else:
        prefix = ""
        letter = ""
        choice_text = raw_answer.strip().lower()

    letter_map = {
        chr(65 + i).lower(): c.lower() for i, c in enumerate(ex.get("choices") or [])
    }

    if letter == correct_ans:
        return True
    if prefix and prefix.lower() == correct_ans:
        return True
    if choice_text == correct_ans:
        return True
    if letter in letter_map and letter_map[letter] == correct_ans:
        return True
    return False


def _extract_choice_text(label: str) -> str:
    """Extract the choice text from a formatted label like 'A.  foo'.

    :param label: Formatted radio/checkbox label.
    :return: Cleaned choice text.
    """
    parts = label.split(".  ", 1)
    return parts[1].strip() if len(parts) == 2 else label.strip()


def _normalize_answer_text(text: str) -> str:
    """Strip letter/number prefixes from an answer string.

    Handles formats like ``"A. photosynthesis"``, ``"1. answer"``,
    or plain ``"photosynthesis"``.

    :param text: Raw answer text from Gemma.
    :return: Cleaned text without prefix.
    """
    stripped = re.sub(r"^[A-Za-z]\.\s*", "", text.strip())
    stripped = re.sub(r"^\d+\.\s*", "", stripped)
    return stripped


def _resolve_answer_to_choice(answer: str, choices: list[str]) -> str:
    """Resolve an answer value to the corresponding choice text.

    Handles three Gemma output formats:
    - Bare letter: ``"A"`` → look up choices[0]
    - Bare number: ``"1"`` → look up choices[0]
    - Prefixed text: ``"A. photosynthesis"`` → ``"photosynthesis"``
    - Plain text: ``"photosynthesis"`` → ``"photosynthesis"``

    :param answer: Raw answer string from Gemma's correct_answers list.
    :param choices: The exercise's choices list (unprefixed text).
    :return: Resolved choice text.
    """
    ans = answer.strip()

    # Bare single letter → index into choices
    if len(ans) == 1 and ans.isalpha():
        idx = ord(ans.upper()) - ord("A")
        if 0 <= idx < len(choices):
            return _normalize_answer_text(choices[idx])
        return ans

    # Bare integer → 1-based index into choices
    if ans.isdigit():
        idx = int(ans) - 1
        if 0 <= idx < len(choices):
            return _normalize_answer_text(choices[idx])
        return ans

    # Prefixed or plain text
    return _normalize_answer_text(ans)


def _session_complete_banner() -> str:
    """Return the session-complete HTML banner."""
    return (
        '<div class="map-session-complete">'
        "Session complete — click Next Question to see results."
        "</div>"
    )


def _advance_and_maybe_complete(
    pstate: dict, exercises: list[dict], idx: int, feedback: str
) -> str:
    """Advance exercise_idx and append completion banner if done.

    :param pstate: Practice state dict (mutated).
    :param exercises: Full exercises list.
    :param idx: Current exercise index.
    :param feedback: Current feedback HTML.
    :return: Updated feedback HTML.
    """
    pstate["exercise_idx"] = idx + 1
    if pstate["exercise_idx"] >= len(exercises):
        feedback += _session_complete_banner()
    return feedback


def _grade_two_part_submit(
    text_answer: str,
    radio_answer: str | None,
    checkbox_answer: list[str] | None,
    pstate: dict,
    ex: dict,
    idx: int,
    exercises: list[dict],
) -> tuple:
    """Grade a two-part question (handles Part A → Part B transition).

    :return: 7-tuple of (question, textbox, radio, checkbox, feedback,
             submit_btn, pstate).
    """
    subject = pstate.get("subject", "math")
    current_part = pstate.get("current_part", "a")

    # --- Part A submitted, show Part B ---
    if current_part == "a":
        correct_a = ex["correct_answer"].strip().lower()
        if radio_answer:
            part_a_correct = _grade_mc_answer(radio_answer, ex, correct_a)
            student_ans_a = radio_answer.strip()
        else:
            student_ans_a = (text_answer or "").strip()
            part_a_correct = student_ans_a.lower() == correct_a

        pstate["part_a_answer"] = student_ans_a
        pstate["part_a_correct"] = part_a_correct
        pstate["current_part"] = "b"

        explanation_a = html.escape(ex.get("explanation", ""))
        if part_a_correct:
            part_a_fb = (
                '<div class="map-feedback-correct">'
                "<h3>Part A: Correct</h3>"
                f"<p>{explanation_a}</p></div>"
            )
        else:
            safe_correct = html.escape(ex["correct_answer"])
            part_a_fb = (
                '<div class="map-feedback-incorrect">'
                "<h3>Part A: Not quite</h3>"
                f"<p><b>Correct answer:</b> {safe_correct}</p>"
                f"<p>{explanation_a}</p></div>"
            )

        if ex.get("part_b_question") and ex.get("part_b_choices"):
            part_b_ex = {
                **ex,
                "question": ex["part_b_question"],
                "choices": ex["part_b_choices"],
            }
            question_html = _build_question_html(
                idx, ex, len(exercises), pstate=pstate, part_label="Part B"
            )
            choices_b = _format_choices(part_b_ex, subject)
            return (
                question_html,
                gr.update(visible=False, value=""),
                gr.update(
                    choices=choices_b,
                    value=None,
                    visible=True,
                    interactive=True,
                ),
                gr.update(visible=False, value=None, choices=[]),
                part_a_fb,
                gr.update(interactive=True),
                pstate,
            )
        # Fallback: no Part B choices — skip to grading
        pstate["current_part"] = "a"

    # --- Part B submitted ---
    if pstate.get("current_part") == "b" or current_part == "b":
        correct_b = (ex.get("part_b_correct") or "").strip().lower()
        if radio_answer:
            part_b_ex = {**ex, "choices": ex.get("part_b_choices") or []}
            part_b_correct = _grade_mc_answer(radio_answer, part_b_ex, correct_b)
            student_ans_b = radio_answer.strip()
        else:
            student_ans_b = (text_answer or "").strip()
            part_b_correct = student_ans_b.lower() == correct_b

        part_a_correct = pstate.get("part_a_correct", False)
        is_correct = part_a_correct and part_b_correct
        student_ans = f"A: {pstate.get('part_a_answer', '')} | B: {student_ans_b}"
        correct_display = (
            f"A: {ex['correct_answer']} | B: {ex.get('part_b_correct', '')}"
        )
        pstate["current_part"] = "a"

        _record_result(pstate, ex, student_ans, correct_display, is_correct)

        explanation = html.escape(ex.get("explanation", ""))
        if is_correct:
            feedback = (
                '<div class="map-feedback-correct">'
                "<h3>Both parts correct!</h3>"
                f"<p>{explanation}</p></div>"
            )
        else:
            feedback = (
                '<div class="map-feedback-incorrect">'
                "<h3>Not quite</h3>"
                f"<p><b>Part A correct:</b> "
                f"{html.escape(ex['correct_answer'])}<br>"
                f"<b>Part B correct:</b> "
                f"{html.escape(ex.get('part_b_correct', ''))}</p>"
                f'<p style="margin-top:0.5rem;">{explanation}</p></div>'
            )

        feedback = _advance_and_maybe_complete(pstate, exercises, idx, feedback)
        return (
            gr.update(),
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.update(interactive=False),
            feedback,
            gr.update(interactive=False),
            pstate,
        )

    # Should not reach here; fall through to MC grading
    return _grade_mc_submit(
        text_answer,
        radio_answer,
        checkbox_answer,
        pstate,
        ex,
        idx,
        exercises,
    )


def _grade_multi_select_submit(
    text_answer: str,
    radio_answer: str | None,
    checkbox_answer: list[str] | None,
    pstate: dict,
    ex: dict,
    idx: int,
    exercises: list[dict],
) -> tuple:
    """Grade a multi-select question.

    :return: 7-tuple.
    """
    selected_texts = {_extract_choice_text(c).lower() for c in (checkbox_answer or [])}
    correct_set = set()
    choices_list = ex.get("choices") or []
    for c in ex.get("correct_answers") or []:
        resolved = _resolve_answer_to_choice(c, choices_list)
        correct_set.add(resolved.lower())
    is_correct = selected_texts == correct_set
    student_ans = ", ".join(checkbox_answer or [])
    correct_display = ", ".join(ex.get("correct_answers") or [])

    _record_result(pstate, ex, student_ans, correct_display, is_correct)

    explanation = html.escape(ex.get("explanation", ""))
    if is_correct:
        feedback = (
            '<div class="map-feedback-correct">'
            "<h3>Correct</h3>"
            f"<p>{explanation}</p></div>"
        )
    else:
        feedback = (
            '<div class="map-feedback-incorrect">'
            "<h3>Not quite</h3>"
            f"<p><b>Your selections:</b> "
            f"{html.escape(student_ans)}<br>"
            f"<b>Correct answers:</b> "
            f"{html.escape(correct_display)}</p>"
            f'<p style="margin-top:0.5rem;">{explanation}</p></div>'
        )

    feedback = _advance_and_maybe_complete(pstate, exercises, idx, feedback)
    return (
        gr.update(),
        gr.update(interactive=False),
        gr.update(interactive=False),
        gr.update(interactive=False),
        feedback,
        gr.update(interactive=False),
        pstate,
    )


def _grade_sequence_submit(
    text_answer: str,
    radio_answer: str | None,
    checkbox_answer: list[str] | None,
    pstate: dict,
    ex: dict,
    idx: int,
    exercises: list[dict],
) -> tuple:
    """Grade a sequence-ordering question.

    :return: 7-tuple.
    """
    student_ans = (text_answer or "").strip()
    correct_order = ex.get("correct_order") or []

    student_items = [s.strip() for s in student_ans.split(",")]
    items = ex.get("items_to_order") or []
    reordered = []
    try:
        for num_str in student_items:
            idx_num = int(num_str) - 1
            if 0 <= idx_num < len(items):
                reordered.append(items[idx_num])
    except (ValueError, IndexError):
        reordered = student_items

    is_correct = [s.strip().lower() for s in reordered] == [
        s.strip().lower() for s in correct_order
    ]
    correct_display = ", ".join(correct_order)

    _record_result(pstate, ex, student_ans, correct_display, is_correct)

    explanation = html.escape(ex.get("explanation", ""))
    if is_correct:
        feedback = (
            '<div class="map-feedback-correct">'
            "<h3>Correct order!</h3>"
            f"<p>{explanation}</p></div>"
        )
    else:
        feedback = (
            '<div class="map-feedback-incorrect">'
            "<h3>Not quite</h3>"
            f"<p><b>Correct order:</b> "
            f"{html.escape(correct_display)}</p>"
            f'<p style="margin-top:0.5rem;">{explanation}</p></div>'
        )

    feedback = _advance_and_maybe_complete(pstate, exercises, idx, feedback)
    return (
        gr.update(),
        gr.update(interactive=False),
        gr.update(interactive=False),
        gr.update(interactive=False),
        feedback,
        gr.update(interactive=False),
        pstate,
    )


def _grade_table_submit(
    text_answer: str,
    radio_answer: str | None,
    checkbox_answer: list[str] | None,
    pstate: dict,
    ex: dict,
    idx: int,
    exercises: list[dict],
) -> tuple:
    """Grade a table-matching question.

    :return: 7-tuple.
    """
    student_ans = (text_answer or "").strip()
    match_pairs = ex.get("match_pairs") or {}
    student_items = [s.strip().lower() for s in student_ans.split(",")]
    correct_vals = [v.strip().lower() for v in match_pairs.values()]

    is_correct = student_items == correct_vals
    correct_display = ", ".join(match_pairs.values())

    _record_result(pstate, ex, student_ans, correct_display, is_correct)

    explanation = html.escape(ex.get("explanation", ""))
    if is_correct:
        feedback = (
            '<div class="map-feedback-correct">'
            "<h3>All matches correct!</h3>"
            f"<p>{explanation}</p></div>"
        )
    else:
        pairs_str = "; ".join(f"{k} \u2192 {v}" for k, v in match_pairs.items())
        feedback = (
            '<div class="map-feedback-incorrect">'
            "<h3>Not quite</h3>"
            f"<p><b>Correct matches:</b> "
            f"{html.escape(pairs_str)}</p>"
            f'<p style="margin-top:0.5rem;">{explanation}</p></div>'
        )

    feedback = _advance_and_maybe_complete(pstate, exercises, idx, feedback)
    return (
        gr.update(),
        gr.update(interactive=False),
        gr.update(interactive=False),
        gr.update(interactive=False),
        feedback,
        gr.update(interactive=False),
        pstate,
    )


def _grade_mc_submit(
    text_answer: str,
    radio_answer: str | None,
    checkbox_answer: list[str] | None,
    pstate: dict,
    ex: dict,
    idx: int,
    exercises: list[dict],
) -> tuple:
    """Grade a standard multiple-choice question.

    :return: 7-tuple.
    """
    q_type = ex.get("question_type", "multiple_choice")
    is_mc = q_type == "multiple_choice" and ex.get("choices")
    if is_mc and radio_answer:
        raw_answer = radio_answer
    else:
        raw_answer = text_answer or ""

    student_ans = raw_answer.strip()
    correct_ans = ex["correct_answer"].strip().lower()

    is_correct = False
    if student_ans:
        if is_mc:
            is_correct = _grade_mc_answer(raw_answer, ex, correct_ans)
        else:
            student_lower = student_ans.lower()
            is_correct = (
                student_lower == correct_ans
                or correct_ans in student_lower
                or student_lower in correct_ans
            )

    _record_result(pstate, ex, student_ans, ex["correct_answer"], is_correct)

    explanation = html.escape(ex["explanation"])

    if is_correct:
        feedback = (
            '<div class="map-feedback-correct">'
            "<h3>Correct</h3>"
            f"<p>{explanation}</p>"
            "</div>"
        )
    else:
        safe_answer = html.escape(student_ans)
        safe_correct = html.escape(ex["correct_answer"])
        feedback = (
            '<div class="map-feedback-incorrect">'
            "<h3>Not quite</h3>"
            f"<p><b>Your answer:</b> {safe_answer}<br>"
            f"<b>Correct answer:</b> {safe_correct}</p>"
            f'<p style="margin-top:0.5rem;">{explanation}</p>'
            "</div>"
        )

    feedback = _advance_and_maybe_complete(pstate, exercises, idx, feedback)

    return (
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        feedback,
        gr.update(interactive=False),
        pstate,
    )


def _grade_fill_blank_submit(
    text_answer: str,
    radio_answer: str | None,
    checkbox_answer: list[str] | None,
    pstate: dict,
    ex: dict,
    idx: int,
    exercises: list[dict],
) -> tuple:
    """Grade a fill-in-the-blank question.

    :return: 7-tuple.
    """
    return _grade_mc_submit(
        text_answer,
        radio_answer,
        checkbox_answer,
        pstate,
        ex,
        idx,
        exercises,
    )


_GRADERS: dict[str, callable] = {
    "multiple_choice": _grade_mc_submit,
    "multi_select": _grade_multi_select_submit,
    "two_part": _grade_two_part_submit,
    "sequence_order": _grade_sequence_submit,
    "table_matching": _grade_table_submit,
    "fill_in_the_blank": _grade_fill_blank_submit,
}


def submit_answer(
    text_answer: str,
    radio_answer: str | None,
    checkbox_answer: list[str] | None,
    pstate: dict,
):
    """Check the answer and show MAP-styled feedback.

    Dispatches to the appropriate per-type grader.

    :param text_answer: Free-response text from the textbox.
    :param radio_answer: Selected radio label (e.g. ``"A.  3/4"``), or None.
    :param checkbox_answer: Selected checkbox labels, or None.
    :param pstate: Per-client practice state dict.
    :return: 7-tuple of (question, answer_input, answer_radio,
             answer_checkbox, feedback, submit_btn, updated_pstate).
    """
    exercises = pstate["exercises"]
    idx = pstate["exercise_idx"]
    if idx >= len(exercises):
        result = _show_results(pstate)
        return (*result, pstate)

    ex = exercises[idx]
    q_type = ex.get("question_type", "multiple_choice")

    grader = _GRADERS.get(q_type, _grade_mc_submit)
    return grader(
        text_answer,
        radio_answer,
        checkbox_answer,
        pstate,
        ex,
        idx,
        exercises,
    )


def _record_result(
    pstate: dict,
    ex: dict,
    student_ans: str,
    correct_display: str,
    is_correct: bool,
) -> None:
    """Append result to pstate and save to database.

    :param pstate: Practice state dict.
    :param ex: Exercise dict.
    :param student_ans: Student's answer string.
    :param correct_display: Display string for correct answer.
    :param is_correct: Whether the answer is correct.
    """
    tier = ex.get("difficulty_tier") or 1
    concept_key = ex["concept"] if tier == 1 else f"{ex['concept']} (multi-step)"
    pstate["results"].append(
        {
            "concept": concept_key,
            "topic": ex["topic"],
            "question": ex["question"],
            "student_answer": student_ans,
            "correct_answer": correct_display,
            "is_correct": is_correct,
        }
    )

    if pstate["session_id"]:
        db = SessionLocal()
        try:
            record = ExerciseResultRecord(
                session_id=pstate["session_id"],
                concept=ex["concept"],
                topic=ex["topic"],
                question=ex["question"],
                student_answer=student_ans,
                correct_answer=correct_display,
                is_correct=is_correct,
            )
            db.add(record)
            db.commit()
        except Exception:
            logger.error("Failed to save answer to DB: %s", traceback.format_exc())
        finally:
            db.close()


def next_question(pstate: dict):
    """Move to the next question or show results.

    :return: 7-tuple of (question, answer_input, answer_radio,
             answer_checkbox, feedback, submit_btn, updated_pstate).
    """
    idx = pstate["exercise_idx"]
    if idx >= len(pstate["exercises"]):
        result = _show_results(pstate)
        return (*result, pstate)
    result = _format_exercise(idx, pstate)
    return (*result, pstate)


def _show_results(pstate: dict):
    """Show MAP-styled session results.

    :return: 6-tuple (question_html, answer_input, answer_radio,
             answer_checkbox, feedback, submit_btn). Caller appends pstate.
    """
    results = pstate["results"]
    if not results:
        return (
            "<p>No results yet.</p>",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            "",
            gr.update(interactive=False),
        )

    correct = sum(1 for r in results if r["is_correct"])
    total = len(results)
    pct = (correct / total * 100) if total > 0 else 0

    # Per-concept breakdown
    concept_scores = {}
    for r in results:
        c = r["concept"]
        if c not in concept_scores:
            concept_scores[c] = {"correct": 0, "total": 0}
        concept_scores[c]["total"] += 1
        if r["is_correct"]:
            concept_scores[c]["correct"] += 1

    # Update session in DB
    if pstate["session_id"]:
        db = SessionLocal()
        try:
            from datetime import datetime, timezone

            session = (
                db.query(PracticeSession)
                .filter(PracticeSession.id == pstate["session_id"])
                .first()
            )
            if session:
                session.correct = correct
                session.total_questions = total
                session.score_pct = pct
                session.concept_scores = concept_scores
                session.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    # Build breakdown list
    breakdown_items = ""
    for c, d in concept_scores.items():
        safe_c = html.escape(c)
        status = (
            "Correct" if d["correct"] == d["total"] else f"{d['correct']}/{d['total']}"
        )
        breakdown_items += f"<li>{safe_c}: {status}</li>"

    # Identify weak concepts for adaptive follow-up
    weak = [
        c
        for c, d in concept_scores.items()
        if d["total"] > 0 and d["correct"] / d["total"] < 0.8
    ]

    if weak and pct < 100:
        weak_list = ", ".join(html.escape(c) for c in weak)
        follow_up = (
            '<div class="map-results-followup">'
            f"You struggled with {weak_list}. Click <b>Start Practice</b> "
            "again — the next session will prioritize these concepts."
            "</div>"
        )
    else:
        follow_up = (
            '<div class="map-results-followup">'
            "All concepts at 80%+ mastery. Try increasing the question "
            "count for a challenge!"
            "</div>"
        )

    results_html = (
        '<div class="map-results-card">'
        "<h2>🎉 Session Complete!</h2>"
        f'<div class="map-score-big">{correct}/{total}</div>'
        f'<div class="map-score-pct">{pct:.0f}% correct</div>'
        "<h3>Concept Breakdown</h3>"
        f"<ul>{breakdown_items}</ul>"
        f"{follow_up}"
        "</div>"
    )

    return (
        results_html,
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        "",
        gr.update(interactive=False),
    )


def get_progress_report(student_id, subject="math", progress=gr.Progress()):
    """Generate a progress report for the student."""

    def _info(msg: str) -> str:
        return f"<p style='color:#6b7280;font-weight:600;padding:1rem 0;'>{msg}</p>"

    if not student_id:
        return _info("Register a student first.")

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == int(student_id)).first()
        if not student:
            return _info("Student not found.")

        scores = (
            db.query(Score)
            .filter(Score.student_id == student.id, Score.subject == subject)
            .all()
        )
        if not scores:
            return _info(f"No {SUBJECT_DISPLAY.get(subject, subject)} scores found.")

        latest = max(scores, key=lambda s: (s.year, SEASON_ORDER[s.season]))

        # Use cached trend if available
        cached = get_cached_analysis(student.id, db, subject)
        if cached:
            trend = cached.trend
        else:
            score_inputs = [
                ScoreInput(rit_score=s.rit_score, season=s.season, year=s.year)
                for s in scores
            ]
            trend, _ = detect_trend(score_inputs, grade=student.grade, subject=subject)

        sessions = (
            db.query(PracticeSession)
            .filter(
                PracticeSession.student_id == student.id,
                PracticeSession.subject == subject,
                PracticeSession.completed_at.isnot(None),
            )
            .all()
        )

        if not sessions:
            return _info(
                "No completed practice sessions yet. "
                "Complete a practice session first to get a report."
            )

        # Aggregate mastery
        concept_totals = {}
        for s in sessions:
            for concept, data in (s.concept_scores or {}).items():
                if concept not in concept_totals:
                    concept_totals[concept] = {"correct": 0, "total": 0}
                concept_totals[concept]["correct"] += data.get("correct", 0)
                concept_totals[concept]["total"] += data.get("total", 0)

        mastered = [
            c
            for c, d in concept_totals.items()
            if d["total"] > 0 and d["correct"] / d["total"] >= 0.8
        ]
        needs_work = [
            c
            for c, d in concept_totals.items()
            if d["total"] > 0 and d["correct"] / d["total"] < 0.8
        ]

        from src.models.schemas import SessionSummary, StudentProgress

        # Sort sessions chronologically before building summaries
        sessions = sorted(sessions, key=lambda s: s.completed_at or s.started_at)

        student_progress = StudentProgress(
            student_name=student.name,
            grade=student.grade,
            latest_rit=latest.rit_score,
            trend=trend,
            sessions=[
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
            ],
            mastered_concepts=mastered,
            needs_work_concepts=needs_work,
            subject=subject,
        )

        progress(0.5, desc="Gemma 4 E4B generating report...")
        report = generate_report(student_progress)
        subject_display = SUBJECT_DISPLAY.get(subject, subject.title())

        # Build structured data dashboard above the narrative
        total_correct = sum(s.correct for s in sessions)
        total_qs = sum(s.total_questions for s in sessions)
        overall_pct = round(total_correct / total_qs * 100) if total_qs > 0 else 0
        first_pct = sessions[0].score_pct if sessions else 0
        last_pct = sessions[-1].score_pct if sessions else 0
        growth_delta = last_pct - first_pct
        growth_arrow = "+" if growth_delta > 0 else ""
        trend_label = trend.value.title() if trend else "N/A"

        # Colour / icon helpers
        subject_emoji = {"math": "🔢", "reading": "📚", "science": "🔬"}.get(
            subject, "📋"
        )
        trend_lower = trend_label.lower()
        trend_color = {
            "growing": "green",
            "stalling": "orange",
            "declining": "red",
        }.get(trend_lower, "indigo")
        trend_icon = {
            "growing": "↑",
            "stalling": "→",
            "declining": "↓",
        }.get(trend_lower, "—")
        growth_color = (
            "green" if growth_delta > 0 else "red" if growth_delta < 0 else "indigo"
        )

        def _acc_class(pct: float) -> str:
            if pct >= 80:
                return "high"
            if pct >= 40:
                return "mid"
            return "low"

        # ── Header ────────────────────────────────────────────────────────────
        dashboard = (
            f'<div class="report-header">'
            f"  <div>"
            f'    <div class="report-header-title">'
            f"      {subject_emoji} {html.escape(subject_display)} Progress Report"
            f"    </div>"
            f'    <div class="report-header-sub">'
            f"      {html.escape(student.name)}"
            f"    </div>"
            f"  </div>"
            f'  <div class="report-header-badge">RIT {latest.rit_score}</div>'
            f"</div>"
        )

        # ── Stat cards ────────────────────────────────────────────────────────
        dashboard += (
            f'<div class="report-stat-cards">'
            f'  <div class="report-stat-card">'
            f'    <div class="report-stat-label">Trend</div>'
            f'    <div class="report-stat-value {trend_color}">{trend_icon}</div>'
            f'    <div class="report-stat-sub">{html.escape(trend_label)}</div>'
            f"  </div>"
            f'  <div class="report-stat-card">'
            f'    <div class="report-stat-label">Sessions</div>'
            f'    <div class="report-stat-value indigo">{len(sessions)}</div>'
            f'    <div class="report-stat-sub">completed</div>'
            f"  </div>"
            f'  <div class="report-stat-card">'
            f'    <div class="report-stat-label">Accuracy</div>'
            f'    <div class="report-stat-value orange">{overall_pct}%</div>'
            f'    <div class="report-stat-sub">{total_correct} / {total_qs} correct</div>'
            f"  </div>"
            f'  <div class="report-stat-card">'
            f'    <div class="report-stat-label">Growth</div>'
            f'    <div class="report-stat-value {growth_color}">'
            f"      {growth_arrow}{growth_delta:.0f}%"
            f"    </div>"
            f'    <div class="report-stat-sub">'
            f"      {first_pct:.0f}% → {last_pct:.0f}%"
            f"    </div>"
            f"  </div>"
            f"</div>"
        )

        # ── Concepts mastered ─────────────────────────────────────────────────
        mastered_pills = (
            "".join(
                f'<span class="report-pill green">✓ {html.escape(c)}</span>'
                for c in mastered
            )
            or '<span style="color:#94a3b8;font-style:italic;">None yet</span>'
        )
        dashboard += (
            f'<div class="report-section mastered">'
            f'  <div class="report-section-title">✅ Concepts Mastered</div>'
            f'  <div class="report-pill-row">{mastered_pills}</div>'
            f"</div>"
        )

        # ── Needs more work ───────────────────────────────────────────────────
        needs_pills = (
            "".join(
                f'<span class="report-pill orange">{html.escape(c)}</span>'
                for c in needs_work
            )
            or '<span style="color:#94a3b8;font-style:italic;">None yet</span>'
        )
        dashboard += (
            f'<div class="report-section needs-work">'
            f'  <div class="report-section-title">🔧 Needs More Work</div>'
            f'  <div class="report-pill-row">{needs_pills}</div>'
            f"</div>"
        )

        # ── Session history ───────────────────────────────────────────────────
        rows = ""
        for i, s in enumerate(sessions, start=1):
            pct_val = s.score_pct if s.score_pct is not None else 0
            acc_cls = _acc_class(pct_val)
            rows += (
                f"<tr>"
                f"  <td>{i}</td>"
                f"  <td>{html.escape(s.band or '')}</td>"
                f"  <td>{s.correct}/{s.total_questions}</td>"
                f'  <td><span class="report-accuracy {acc_cls}">'
                f"    {pct_val:.0f}%"
                f"  </span></td>"
                f"</tr>"
            )
        dashboard += (
            f'<div class="report-section" style="background:white;">'
            f'  <div class="report-section-title" style="color:#1e293b;">📅 Session History</div>'
            f'  <table class="report-session-table">'
            f"    <thead>"
            f"      <tr><th>#</th><th>Band</th><th>Score</th><th>Accuracy</th></tr>"
            f"    </thead>"
            f"    <tbody>{rows}</tbody>"
            f"  </table>"
            f"</div>"
        )

        # ── Narrative ─────────────────────────────────────────────────────────
        narrative_html = _md.render(report)
        dashboard += (
            f'<div class="report-narrative">'
            f'  <div class="report-narrative-title">📝 Narrative Report</div>'
            f"  {narrative_html}"
            f"</div>"
        )

        return dashboard
    finally:
        db.close()


def _get_weak_concepts(student_id: int, db, subject: str = "math") -> list[str]:
    """Find concepts where the student scored < 80%."""
    sessions = (
        db.query(PracticeSession)
        .filter(
            PracticeSession.student_id == student_id,
            PracticeSession.subject == subject,
            PracticeSession.completed_at.isnot(None),
        )
        .all()
    )

    concept_totals = {}
    for s in sessions:
        for concept, data in (s.concept_scores or {}).items():
            if concept not in concept_totals:
                concept_totals[concept] = {"correct": 0, "total": 0}
            concept_totals[concept]["correct"] += data.get("correct", 0)
            concept_totals[concept]["total"] += data.get("total", 0)

    return [
        c
        for c, d in concept_totals.items()
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
theme.set(
    block_label_background_fill="transparent",
    block_label_background_fill_dark="transparent",
    block_label_border_color="transparent",
    block_label_border_width="0px",
    block_label_padding="0px 0px 4px 0px",
    block_label_radius="0px",
    block_label_text_color="*neutral_700",
    block_label_text_weight="700",
    block_title_background_fill="transparent",
    block_title_padding="0px 0px 4px 0px",
)
theme.custom_css = """
.gradio-container { background-color: #f9fafb !important; font-family: 'Nunito', 'Inter', system-ui, sans-serif !important; }
.tabitem { border-radius: 16px !important; padding: 2rem !important; border: 1px solid #e5e7eb !important; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1) !important; margin-top: 1rem; }
.card-section { background: white; border-radius: 12px; padding: 1.5rem; border: 1px solid #f3f4f6; margin-bottom: 1rem; }
.pill { display: inline-block; padding: 5px 14px; border-radius: 9999px; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.025em; margin-right: 0.5rem; }
.pill-primary { background-color: #e0e7ff; color: #4338ca; }
.pill-secondary { background-color: #ecfdf5; color: #047857; }
.pill-neutral { background-color: #f3f4f6; color: #374151; }

/* === Global Button Styles === */
button.primary {
    background: linear-gradient(135deg, #4f46e5, #818cf8) !important;
    color: white !important;
    font-family: 'Fredoka One', cursive !important;
    font-size: 1rem !important;
    letter-spacing: 0.02em !important;
    padding: 0.65rem 1.35rem !important;
    border-radius: 12px !important;
    border: none !important;
    box-shadow: 0 4px 12px rgba(79,70,229,0.3) !important;
    transition: all 0.15s ease !important;
}
button.primary:hover { transform: translateY(-2px) !important; box-shadow: 0 6px 18px rgba(79,70,229,0.45) !important; }
button.secondary {
    background: white !important;
    color: #4f46e5 !important;
    font-family: 'Fredoka One', cursive !important;
    font-size: 1rem !important;
    letter-spacing: 0.02em !important;
    padding: 0.65rem 1.35rem !important;
    border-radius: 12px !important;
    border: 2px solid #818cf8 !important;
    box-shadow: 0 2px 6px rgba(79,70,229,0.1) !important;
    transition: all 0.15s ease !important;
}
button.secondary:hover { background: #eef2ff !important; transform: translateY(-2px) !important; box-shadow: 0 4px 12px rgba(79,70,229,0.2) !important; }
button.stop {
    background: linear-gradient(135deg, #ef4444, #dc2626) !important;
    color: white !important;
    font-family: 'Fredoka One', cursive !important;
    font-size: 1rem !important;
    letter-spacing: 0.02em !important;
    padding: 0.65rem 1.35rem !important;
    border-radius: 12px !important;
    border: none !important;
    box-shadow: 0 4px 12px rgba(220,38,38,0.3) !important;
    transition: all 0.15s ease !important;
}
button.stop:hover { transform: translateY(-2px) !important; box-shadow: 0 6px 18px rgba(220,38,38,0.45) !important; }
button.secondary.sm {
    font-family: 'Fredoka One', cursive !important;
    font-size: 0.85rem !important;
    padding: 0.4rem 0.9rem !important;
    border-radius: 10px !important;
    border: 2px solid #c7d2fe !important;
    background: #eef2ff !important;
    color: #4338ca !important;
    box-shadow: none !important;
}
button.secondary.sm:hover { background: #e0e7ff !important; transform: translateY(-1px) !important; }
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

/* === Practice Tab — Kid-Friendly Redesign === */
#map-practice-wrapper { font-family: 'Nunito', sans-serif !important; background: #f0f9ff; padding: 0 0 1.5rem 0; }
#map-practice-wrapper * { font-family: 'Nunito', sans-serif !important; }

/* Top bar: gradient header with subject emoji */
.map-topbar { background: linear-gradient(135deg, #4f46e5 0%, #38bdf8 100%); padding: 0.85rem 1.25rem; display: flex; align-items: center; color: white; border-radius: 12px 12px 0 0; margin-bottom: 0; }
.map-topbar-subject { font-family: 'Fredoka One', cursive !important; font-size: 1.15rem; letter-spacing: 0.03em; display: flex; align-items: center; gap: 0.5rem; }

/* Progress bar */
.map-progress-area { background: #e0f7ff; padding: 0.6rem 1.25rem; display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0; }
.map-progress-bar-wrap { flex: 1; background: rgba(255,255,255,0.8); border-radius: 50px; height: 12px; overflow: hidden; border: 2px solid #38bdf8; }
.map-progress-fill { height: 100%; background: linear-gradient(90deg, #4f46e5, #38bdf8); border-radius: 50px; transition: width 0.4s ease; }
.map-progress-label { font-size: 0.85rem; font-weight: 800; color: #4f46e5; white-space: nowrap; }

/* Question body */
.map-question-area { background: #ffffff; padding: 1.25rem 1.4rem 1rem; }

/* Topic chip (replaces flat banner) */
.map-topic-chip { display: inline-flex; align-items: center; gap: 0.4rem; background: linear-gradient(135deg, #e0e7ff, #dbeafe); color: #3730a3; font-size: 0.8rem; font-weight: 800; padding: 0.35rem 0.9rem; border-radius: 50px; margin-bottom: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; }

/* Question text */
.map-question-text { font-size: 1.25rem; font-weight: 700; color: #1e293b; line-height: 1.6; margin: 0 0 1rem 0; }

/* Answer choices: rounded tiles */
#map-practice-wrapper .map-radio-choices label {
    display: flex !important; align-items: center !important;
    gap: 0.75rem !important; padding: 0.75rem 1rem !important;
    border-radius: 14px !important; border: 2.5px solid #e2e8f0 !important;
    background: #f1f5f9 !important; margin-bottom: 0.55rem !important;
    font-size: 0.95rem !important; font-weight: 600 !important; color: #1e293b !important;
    cursor: pointer !important; line-height: 1.5 !important; transition: all 0.15s ease !important;
}
#map-practice-wrapper .map-radio-choices label:hover { border-color: #818cf8 !important; background: #eef2ff !important; transform: translateX(3px) !important; }
#map-practice-wrapper .map-radio-choices input[type="radio"] { width: 20px !important; height: 20px !important; accent-color: #4f46e5 !important; flex-shrink: 0 !important; }

/* Text answer input */
#map-practice-wrapper .map-text-input textarea {
    font-size: 1rem !important; padding: 0.6rem 0.8rem !important;
    border: 2.5px solid #cbd5e1 !important; border-radius: 12px !important;
    line-height: 1.5 !important; max-width: 240px !important;
}
#map-practice-wrapper .map-text-input textarea:focus { border-color: #4f46e5 !important; outline: none !important; box-shadow: 0 0 0 3px rgba(79,70,229,0.15) !important; }

/* Submit button */
#map-practice-wrapper .map-submit-btn {
    background: linear-gradient(135deg, #4f46e5, #818cf8) !important; color: #fff !important;
    font-family: 'Fredoka One', cursive !important; font-size: 1.05rem !important;
    padding: 0.8rem 1.5rem !important; border-radius: 14px !important; border: none !important;
    box-shadow: 0 4px 12px rgba(79,70,229,0.35) !important; transition: all 0.15s ease !important; letter-spacing: 0.03em !important;
}
#map-practice-wrapper .map-submit-btn:hover { transform: translateY(-2px) !important; box-shadow: 0 6px 16px rgba(79,70,229,0.45) !important; }

/* Next button */
#map-practice-wrapper .map-next-btn {
    background: #ffffff !important; color: #4f46e5 !important;
    font-family: 'Fredoka One', cursive !important; font-size: 1.05rem !important;
    border: 2.5px solid #818cf8 !important; padding: 0.8rem 1.2rem !important;
    border-radius: 14px !important; transition: all 0.15s ease !important; letter-spacing: 0.03em !important;
}
#map-practice-wrapper .map-next-btn:hover { background: #eef2ff !important; transform: translateY(-2px) !important; }

/* Start Practice button */
#map-practice-wrapper .map-start-btn {
    background: linear-gradient(135deg, #34d399, #059669) !important; color: #fff !important;
    font-family: 'Fredoka One', cursive !important; font-size: 1rem !important;
    padding: 0.75rem 1.5rem !important; border-radius: 14px !important; border: none !important;
    box-shadow: 0 4px 12px rgba(52,211,153,0.4) !important; transition: all 0.15s ease !important; letter-spacing: 0.03em !important;
}
#map-practice-wrapper .map-start-btn:hover { transform: translateY(-2px) !important; box-shadow: 0 6px 16px rgba(52,211,153,0.5) !important; }

/* Session complete */
.map-session-complete { font-family: 'Fredoka One', cursive; font-size: 1.1rem; color: #4f46e5; text-align: center; margin-top: 1rem; }

/* Results card */
.map-results-card { background: #fff; padding: 1.5rem 1.25rem; line-height: 1.6; border-radius: 16px; }
.map-results-card h2 { font-family: 'Fredoka One', cursive; color: #4f46e5; font-size: 1.4rem; border-bottom: 3px solid #e0e7ff; padding-bottom: 0.5rem; margin-bottom: 1rem; font-weight: normal; }
.map-score-big { font-family: 'Fredoka One', cursive; font-size: 3rem; color: #4f46e5; text-align: center; margin: 1rem 0 0.25rem; }
.map-score-pct { text-align: center; color: #64748b; font-size: 1rem; font-weight: 700; margin-bottom: 1rem; }
.map-results-card h3 { font-family: 'Fredoka One', cursive; color: #1e293b; font-size: 1.1rem; margin-top: 1.25rem; font-weight: normal; }
.map-results-card ul { list-style: none; padding: 0; margin: 0; }
.map-results-card li { padding: 0.6rem 0; border-bottom: 1px solid #f1f5f9; font-size: 0.95rem; color: #374151; font-weight: 600; }
.map-results-followup { background: #eef2ff; padding: 1rem 1.25rem; margin-top: 1.25rem; font-size: 0.95rem; color: #1e293b; line-height: 1.6; border-left: 4px solid #4f46e5; border-radius: 0 12px 12px 0; }

/* Scenario / passage box */
.map-scenario-box { background: linear-gradient(135deg, #fffbeb, #fef9c3); border: 2px solid #fde68a; border-radius: 14px; padding: 1rem 1.1rem; margin-bottom: 0.9rem; font-size: 1.15rem; color: #44403c; line-height: 1.7; }
.map-scenario-box .map-scenario-label { font-size: 0.72rem; font-weight: 900; color: #92400e; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.4rem; }

/* Part A / Part B labels */
.map-part-label { display: inline-block; background: linear-gradient(135deg, #4f46e5, #818cf8); color: #fff; font-family: 'Fredoka One', cursive; font-size: 0.85rem; padding: 3px 12px; border-radius: 50px; margin-bottom: 0.5rem; letter-spacing: 0.03em; }

/* Checkbox group — multi-select */
#map-practice-wrapper .map-checkbox-choices label {
    display: flex !important; align-items: center !important;
    gap: 0.75rem !important; padding: 0.75rem 1rem !important;
    border-radius: 14px !important; border: 2.5px solid #e2e8f0 !important;
    background: #f1f5f9 !important; margin-bottom: 0.55rem !important;
    font-size: 0.95rem !important; font-weight: 600 !important; color: #1e293b !important;
    cursor: pointer !important; line-height: 1.5 !important; transition: all 0.15s ease !important;
}
#map-practice-wrapper .map-checkbox-choices label:hover { border-color: #818cf8 !important; background: #eef2ff !important; }
#map-practice-wrapper .map-checkbox-choices input[type="checkbox"] { width: 20px !important; height: 20px !important; accent-color: #4f46e5 !important; flex-shrink: 0 !important; border-radius: 6px !important; }

/* Instruction + match table */
.map-instruction { font-size: 0.9rem; color: #4f46e5; font-weight: 700; margin-bottom: 0.5rem; }
.map-match-table { width: 100%; border-collapse: collapse; margin: 0.5rem 0; font-size: 0.95rem; }
.map-match-table th { background: #e0e7ff; padding: 0.5rem 0.75rem; text-align: left; border-bottom: 2px solid #818cf8; font-weight: 800; color: #3730a3; }
.map-match-table td { padding: 0.5rem 0.75rem; border-bottom: 1px solid #f1f5f9; color: #374151; font-weight: 600; }

/* === Tab & Section Header Font Sizes === */
.tab-container > button { font-family: 'Fredoka One', cursive !important; font-size: 1.1rem !important; letter-spacing: 0.02em !important; }
.prose h3 { font-size: 1.2rem !important; font-weight: 900 !important; }

/* === Report Tab === */
.report-header { background: linear-gradient(135deg, #4f46e5 0%, #38bdf8 100%); border-radius: 14px; padding: 1.25rem 1.5rem; color: white; margin-bottom: 1.25rem; display: flex; align-items: center; justify-content: space-between; }
.report-header-title { font-family: 'Fredoka One', cursive; font-size: 1.3rem; letter-spacing: 0.02em; color: white !important; }
.report-header-sub { font-size: 0.85rem; font-weight: 600; opacity: 0.85; margin-top: 0.2rem; color: white !important; }
.report-header-badge { background: rgba(255,255,255,0.2); border-radius: 50px; padding: 0.4rem 1rem; font-size: 0.85rem; font-weight: 700; white-space: nowrap; }
.report-stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin-bottom: 1.25rem; }
.report-stat-card { background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 0.85rem 1rem; text-align: center; }
.report-stat-label { font-size: 0.8rem; font-weight: 800; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.35rem; }
.report-stat-value { font-family: 'Fredoka One', cursive; font-size: 1.6rem; color: #1e293b; line-height: 1; }
.report-stat-value.green { color: #059669; } .report-stat-value.orange { color: #d97706; } .report-stat-value.indigo { color: #4f46e5; } .report-stat-value.red { color: #dc2626; }
.report-stat-sub { font-size: 0.82rem; font-weight: 700; color: #94a3b8; margin-top: 0.2rem; }
.report-section { border-radius: 14px; padding: 1rem 1.25rem; margin-bottom: 1rem; border: 1.5px solid #e2e8f0; }
.report-section.mastered { background: #f0fdf4; border-color: #86efac; }
.report-section.needs-work { background: #fffbeb; border-color: #fde68a; }
.report-section-title { font-family: 'Fredoka One', cursive; font-size: 1.2rem; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem; }
.report-section.mastered .report-section-title { color: #065f46; }
.report-section.needs-work .report-section-title { color: #92400e; }
.report-pill-row { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.report-pill { display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.4rem 1rem; border-radius: 50px; font-size: 1rem; font-weight: 700; }
.report-pill.green { background: #dcfce7; color: #166534; }
.report-pill.orange { background: #fef9c3; color: #854d0e; border: 1px solid #fde68a; }
.report-session-table { width: 100%; border-collapse: collapse; font-size: 1rem; }
.report-session-table th { background: linear-gradient(135deg, #e0e7ff, #dbeafe); color: #3730a3; font-weight: 800; padding: 0.6rem 0.85rem; text-align: left; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; }
.report-session-table th:first-child { border-radius: 8px 0 0 8px; } .report-session-table th:last-child { border-radius: 0 8px 8px 0; }
.report-session-table td { padding: 0.6rem 0.85rem; border-bottom: 1px solid #f1f5f9; font-weight: 600; color: #374151; }
.report-session-table tr:last-child td { border-bottom: none; }
.report-accuracy { display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 50px; font-size: 0.95rem; font-weight: 800; }
.report-accuracy.high { background: #dcfce7; color: #166534; }
.report-accuracy.mid  { background: #fef9c3; color: #854d0e; }
.report-accuracy.low  { background: #fee2e2; color: #991b1b; }
.report-narrative { background: #f8fafc; border: 1.5px solid #e2e8f0; border-left: 4px solid #4f46e5; border-radius: 0 14px 14px 0; padding: 1rem 1.25rem; margin-top: 1rem; font-size: 1.1rem; line-height: 1.8; color: #374151; }
.report-narrative-title { font-family: 'Fredoka One', cursive; font-size: 1.25rem; color: #4f46e5; margin-bottom: 0.75rem; }
.report-narrative p { margin: 0 0 0.6rem 0; }
.report-narrative ul, .report-narrative ol { margin: 0.25rem 0 0.6rem 1.25rem; padding: 0; }
.report-narrative li { margin-bottom: 0.3rem; }
.report-narrative strong { color: #1e293b; font-weight: 800; }
"""

custom_css = theme.custom_css

_SUBJECT_ICONS = {"math": "🔢", "reading": "📖", "science": "🔬"}


def _build_scores_tab(subject: str, student_id_state, student_dropdown):
    """Build the Scores sub-tab for a given subject. All event handlers
    are wired internally with subject captured in closures."""
    subject_display = SUBJECT_DISPLAY.get(subject, subject.title())

    gr.Markdown("### Load Existing Student")
    with gr.Row():
        load_btn = gr.Button("Load Student", variant="primary", scale=1)

    gr.Markdown("---")

    gr.Markdown("### Student Details")
    with gr.Row():
        name_input = gr.Textbox(label="Student Name", placeholder="e.g., Alex", scale=3)
        grade_input = gr.Dropdown(
            choices=["KG", "1", "2", "3", "4", "5"],
            label="Current Grade",
            value="3",
            scale=1,
        )

    gr.Markdown(
        f"### Upload {subject_display} Score Report *(optional — auto-fills scores below)*"
    )
    with gr.Row():
        score_file = gr.File(
            label="Upload MAP score image or PDF",
            file_types=[".png", ".jpg", ".jpeg", ".pdf", ".webp", ".bmp"],
            scale=3,
        )
        extract_btn = gr.Button(
            "Extract Scores with Gemma 4", variant="secondary", scale=1
        )
    extract_status = gr.Markdown("")

    gr.Markdown(f"### {subject_display} MAP Scores")
    gr.Markdown(
        "*Enter scores below or upload an image/PDF above. Add/remove rows as needed.*"
    )

    scores_state = gr.State(
        value=[{"rit": 185, "season": "winter", "year": 2025, "grade": "3"}]
    )

    @gr.render(inputs=scores_state)
    def render_score_rows(scores_list):
        rits, seasons, years, grades_at = [], [], [], []
        for i, score in enumerate(scores_list):
            with gr.Row():
                rit = gr.Number(
                    value=score.get("rit", 0),
                    label="RIT Score" if i == 0 else f"RIT Score ({i + 1})",
                    precision=0,
                    key=f"{subject}_rit_{i}",
                    interactive=True,
                )
                season = gr.Dropdown(
                    choices=["fall", "winter", "spring"],
                    value=score.get("season", "fall"),
                    label="Season",
                    key=f"{subject}_season_{i}",
                    interactive=True,
                )
                year = gr.Number(
                    value=score.get("year", 2025),
                    label="Year",
                    precision=0,
                    key=f"{subject}_year_{i}",
                    interactive=True,
                )
                grade_at = gr.Dropdown(
                    choices=["KG", "1", "2", "3", "4", "5"],
                    value=str(score.get("grade", "3")),
                    label="Grade",
                    key=f"{subject}_grade_{i}",
                    interactive=True,
                )
                rits.append(rit)
                seasons.append(season)
                years.append(year)
                grades_at.append(grade_at)

        def _collect_scores(*args) -> list[dict]:
            n = len(args) // 4
            scores_data = []
            for j in range(n):
                scores_data.append(
                    {
                        "rit": args[j],
                        "season": args[n + j],
                        "year": args[2 * n + j],
                        "grade": args[3 * n + j],
                    }
                )
            return scores_data

        def collect_and_analyze(name, grade, *args):
            scores_data = _collect_scores(*args)
            try:
                return register_student(name, grade, scores_data, subject=subject)
            except Exception as e:
                logger.error("register_and_analyze failed: %s", traceback.format_exc())
                return f"Error: {e}", "", "", None

        register_btn.click(
            fn=collect_and_analyze,
            inputs=[name_input, grade_input] + rits + seasons + years + grades_at,
            outputs=[status_output, analysis_output, student_id_state, score_chart],
        ).then(
            fn=lambda: gr.update(choices=list(get_existing_students().keys())),
            inputs=[],
            outputs=[student_dropdown],
            show_progress="hidden",
        )

    with gr.Row():
        add_row_btn = gr.Button("+ Add Score Row", variant="secondary", size="sm")
        remove_row_btn = gr.Button("- Remove Last Row", variant="secondary", size="sm")

    def add_score_row(current_scores):
        return current_scores + [
            {"rit": 0, "season": "fall", "year": 2025, "grade": "3"}
        ]

    def remove_score_row(current_scores):
        if len(current_scores) > 1:
            return current_scores[:-1]
        return current_scores

    add_row_btn.click(fn=add_score_row, inputs=[scores_state], outputs=[scores_state])
    remove_row_btn.click(
        fn=remove_score_row, inputs=[scores_state], outputs=[scores_state]
    )

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
            # Use multi-subject extraction
            all_subjects = extract_all_subjects_from_file(file_path)
        except Exception as e:
            logger.error("Score extraction failed: %s", traceback.format_exc())
            return gr.update(), gr.update(), gr.update(), f"Extraction failed: {e}"

        result = all_subjects.get(subject)
        if not result or not result.get("scores"):
            # Show what WAS found
            found_subjects = [
                f"{len(v.get('scores', []))} {SUBJECT_DISPLAY.get(k, k)}"
                for k, v in all_subjects.items()
                if v.get("scores")
            ]
            if found_subjects:
                banner = f"No {subject_display} scores found. Found: {', '.join(found_subjects)}."
            else:
                banner = (
                    "No MAP scores found in the file. Please try a clearer screenshot."
                )
            return gr.update(), gr.update(), gr.update(), banner

        new_scores = []
        for s in result["scores"]:
            new_scores.append(
                {
                    "rit": s["rit_score"],
                    "season": s["season"],
                    "year": s["year"],
                    "grade": str(s["grade"]) if s.get("grade") is not None else "3",
                }
            )

        name_update = (
            gr.update(value=result["student_name"])
            if result.get("student_name")
            else gr.update()
        )
        current_grade = result.get("grade")
        if current_grade is None and new_scores:
            first_grade = new_scores[0].get("grade")
            if first_grade is not None and str(first_grade).strip():
                current_grade = first_grade
        if current_grade is not None:
            grade_str = (
                "KG"
                if str(current_grade) == "KG" or current_grade == 0
                else str(current_grade)
            )
            grade_update = gr.update(value=grade_str)
        else:
            grade_update = gr.update()

        # Build banner showing all subjects found
        found_parts = []
        other_subjects = []
        for k, v in all_subjects.items():
            if v.get("scores"):
                found_parts.append(f"{len(v['scores'])} {SUBJECT_DISPLAY.get(k, k)}")
                if k != subject:
                    other_subjects.append(SUBJECT_DISPLAY.get(k, k))
        banner = f"Found: {', '.join(found_parts)} scores. Showing **{subject_display}** ({len(new_scores)} scores). Review and edit below, then click Analyze."
        if other_subjects:
            banner += f" Upload the same file in the **{', '.join(other_subjects)}** tab(s) to load those scores."

        return new_scores, name_update, grade_update, banner

    extract_btn.click(
        fn=extract_from_file,
        inputs=[score_file],
        outputs=[scores_state, name_input, grade_input, extract_status],
    )

    def _load_student_for_subject(selection):
        return load_student(selection, subject=subject)

    load_btn.click(
        fn=_load_student_for_subject,
        inputs=[student_dropdown],
        show_progress="hidden",
        outputs=[
            status_output,
            analysis_output,
            student_id_state,
            score_chart,
            register_btn,
            name_input,
            grade_input,
            scores_state,
        ],
    )

    return name_input, grade_input, scores_state


def _build_practice_tab(subject: str, student_id_state):
    """Build the MAP-styled Practice sub-tab for a given subject."""
    practice_state = gr.State(_empty_practice_state())

    with gr.Column(elem_id="map-practice-wrapper"):
        with gr.Row():
            num_q_input = gr.Slider(
                minimum=3,
                maximum=24,
                value=5,
                step=1,
                label="Number of Questions (default: 5)",
                scale=3,
                show_label=True,
            )
            start_btn = gr.Button(
                "▶ Start Practice!",
                variant="primary",
                scale=1,
                elem_classes=["map-start-btn"],
            )

        question_display = gr.HTML(label="Question")
        answer_radio = gr.Radio(
            choices=[],
            label="Select your answer",
            visible=False,
            interactive=True,
            elem_classes=["map-radio-choices"],
        )
        answer_checkbox = gr.CheckboxGroup(
            choices=[],
            label="Select all that apply",
            visible=False,
            interactive=True,
            elem_classes=["map-checkbox-choices"],
        )
        answer_input = gr.Textbox(
            label="Enter the answer in the box.",
            placeholder="",
            lines=1,
            visible=False,
            elem_classes=["map-text-input"],
        )
        with gr.Row(visible=False) as btn_row:
            submit_btn = gr.Button(
                "Submit Answer",
                variant="primary",
                scale=2,
                elem_classes=["map-submit-btn"],
            )
            next_btn = gr.Button(
                "Next Question",
                variant="secondary",
                scale=1,
                elem_classes=["map-next-btn"],
            )

        feedback_display = gr.HTML(label="Feedback", visible=False)

    practice_outputs = [
        question_display,
        answer_input,
        answer_radio,
        answer_checkbox,
        feedback_display,
        submit_btn,
        practice_state,
        btn_row,
    ]

    def _start(sid, nq, ps):
        result = start_practice(sid, nq, ps, subject=subject)
        has_exercises = isinstance(result[-1], dict) and bool(
            result[-1].get("exercises")
        )
        return (*result, gr.update(visible=has_exercises))

    def _submit(text_ans, radio_ans, checkbox_ans, ps):
        result = list(submit_answer(text_ans, radio_ans, checkbox_ans, ps))
        # Ensure feedback_display (index 4) is visible when it has content
        fb = result[4]
        if fb and isinstance(fb, str) and fb.strip():
            result[4] = gr.update(visible=True, value=fb)
        return (*result, gr.update())

    def _next(ps):
        result = list(next_question(ps))
        # Hide feedback when moving to next question
        result[4] = gr.update(visible=False, value="")
        # Hide button row when session results are showing
        idx = ps.get("exercise_idx", 0)
        exercises = ps.get("exercises", [])
        btn_visible = idx < len(exercises)
        return (*result, gr.update(visible=btn_visible))

    start_btn.click(
        fn=_start,
        inputs=[student_id_state, num_q_input, practice_state],
        outputs=practice_outputs,
    )

    submit_btn.click(
        fn=_submit,
        inputs=[answer_input, answer_radio, answer_checkbox, practice_state],
        outputs=practice_outputs,
    )

    next_btn.click(
        fn=_next,
        inputs=[practice_state],
        outputs=practice_outputs,
    )


def _build_report_tab(subject: str, student_id_state):
    """Build the Report sub-tab for a given subject."""
    report_btn = gr.Button("Generate Report", variant="primary")
    report_output = gr.HTML(label="Report")

    def _show_loading():
        return gr.update(
            value="<p style='color:#6b7280;font-weight:600;padding:1rem 0;'>"
            "⏳ Generating report… Please wait while Gemma 4 "
            "analyzes practice session data.</p>",
        )

    def _report(sid):
        return get_progress_report(sid, subject=subject)

    report_btn.click(
        fn=_show_loading,
        inputs=[],
        outputs=[report_output],
    ).then(
        fn=_report,
        inputs=[student_id_state],
        show_progress="hidden",
        outputs=[report_output],
    )


with gr.Blocks(
    title="MAP Accelerator",
    head='<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Fredoka+One&family=Nunito:wght@400;600;700;800;900&display=swap" rel="stylesheet">',
) as demo:
    gr.HTML("""
        <div style="text-align: center; padding: 2rem 0;">
            <h1 style="font-size: 2.5rem; font-weight: 800; color: #1e1b4b; margin-bottom: 0.5rem;">MAP Accelerator</h1>
            <p style="font-size: 1.125rem; color: #6b7280; max-width: 600px; margin: 0 auto;">Personalized practice for advanced students across Math, Reading & Science — powered by Gemma 4</p>
        </div>
    """)

    # Shared student dropdown at top level
    with gr.Row():
        student_dropdown = gr.Dropdown(
            choices=list(get_existing_students().keys()),
            label="Select Student",
            interactive=True,
            scale=3,
        )
        refresh_btn = gr.Button("Refresh List", variant="secondary", scale=1)
        delete_btn = gr.Button("Delete Student", variant="stop", scale=1)

    def refresh_student_list_btn():
        return gr.update(choices=list(get_existing_students().keys()), value=None)

    refresh_btn.click(
        fn=refresh_student_list_btn,
        inputs=[],
        outputs=[student_dropdown],
    )

    def delete_student(selection: str | None):
        """Delete the selected student after JS confirm() approval."""
        if not selection:
            gr.Warning("Please select a student first.")
            return gr.update()

        student_map = get_existing_students()
        student_id = student_map.get(selection)
        if not student_id:
            gr.Warning("Student not found.")
            return gr.update(
                choices=list(get_existing_students().keys()), value=None
            )

        db = SessionLocal()
        try:
            student = db.query(Student).filter(Student.id == int(student_id)).first()
            if student:
                db.delete(student)
                db.commit()
                gr.Info(f"Deleted {selection}.")
            else:
                gr.Warning("Student not found in database.")
        finally:
            db.close()

        return gr.update(
            choices=list(get_existing_students().keys()), value=None
        )

    delete_btn.click(
        fn=delete_student,
        inputs=[student_dropdown],
        outputs=[student_dropdown],
        js="(sel) => { if (!sel) return sel; if (!confirm('Are you sure? This will permanently delete ' + sel + ' and all their scores, practice sessions, and reports.')) { throw new Error('cancelled'); } return sel; }",
        show_progress="hidden",
    )

    # Top-level subject tabs — each subject gets its own student_id_state
    # so loading a student in one tab doesn't affect another tab's practice/report.
    with gr.Tabs():
        for subj in SUBJECTS:
            subj_display = SUBJECT_DISPLAY.get(subj, subj.title())
            subj_icon = _SUBJECT_ICONS.get(subj, "")
            with gr.Tab(f"{subj_icon} {subj_display}"):
                student_id_state = gr.State("")
                with gr.Tabs():
                    with gr.Tab("📊 Scores"):
                        _build_scores_tab(subj, student_id_state, student_dropdown)
                    with gr.Tab("🎯 Practice"):
                        _build_practice_tab(subj, student_id_state)
                    with gr.Tab("📋 Report"):
                        _build_report_tab(subj, student_id_state)


if __name__ == "__main__":
    demo.launch(server_port=7860, theme=theme, css=custom_css)
