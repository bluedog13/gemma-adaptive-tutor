"""Curriculum mapper — maps RIT scores to Develop/Introduce bands."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from src.constants import DATA_DIR, MODEL
from src.models.schemas import BandInfo, CurriculumResult, ScoreInput, Trend

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
from src.prompts import build_trend_prompt

logger = logging.getLogger("map_accelerator")

_curriculum_cache: dict[str, dict] = {}


def _load_curriculum(subject: str = "math") -> dict:
    """Load and cache the RIT-to-concept mapping for a subject.

    :param subject: One of ``"math"``, ``"reading"``, ``"science"``.
    :return: Parsed JSON curriculum dict.
    :raises ValueError: If *subject* is not supported or data file is missing.
    """
    from src.constants import SUBJECTS

    if subject not in SUBJECTS:
        raise ValueError(
            f"Unsupported subject '{subject}'. Must be one of: {SUBJECTS}"
        )
    global _curriculum_cache
    if subject not in _curriculum_cache:
        path = DATA_DIR / f"rit_to_concept_{subject}_2plus.json"
        if not path.exists():
            raise ValueError(
                f"Curriculum data file not found for subject '{subject}': {path}"
            )
        with open(path) as f:
            _curriculum_cache[subject] = json.load(f)
    return _curriculum_cache[subject]


def _score_to_band_key(rit_score: int, subject: str = "math") -> str | None:
    """Find the band key (e.g. '181-190') that contains this RIT score."""
    data = _load_curriculum(subject)
    for band_key in data["bands"]:
        low, high = band_key.split("-")
        if int(low) <= rit_score <= int(high):
            return band_key
    return None


def _next_band_key(band_key: str, subject: str = "math") -> str | None:
    """Get the band key one level above."""
    data = _load_curriculum(subject)
    keys = list(data["bands"].keys())
    try:
        idx = keys.index(band_key)
        if idx + 1 < len(keys):
            return keys[idx + 1]
    except ValueError:
        pass
    return None


def _band_key_to_info(band_key: str, subject: str = "math") -> BandInfo:
    """Convert a band dict entry to a BandInfo schema."""
    data = _load_curriculum(subject)
    band = data["bands"].get(band_key, {})
    return BandInfo(
        band=band_key,
        building_on_prior=band.get("building_on_prior", []),
        topics=band.get("topics", {}),
        additional_learning_continuum_topics=band.get(
            "additional_learning_continuum_topics", []
        ),
    )


def _sort_scores(scores: list[ScoreInput]) -> list[ScoreInput]:
    """Sort scores in chronological order (winter=Jan, spring=Apr, fall=Sep)."""
    _CHRONO = {"winter": 0, "spring": 1, "fall": 2}
    return sorted(scores, key=lambda s: (s.year, _CHRONO[str(s.season.value)]))


def _build_timeline(
    sorted_scores: list[ScoreInput], grade: int = 3, subject: str = "math"
) -> str:
    """Build a readable score timeline with computed metrics."""
    from src.constants import estimate_percentile, NWEA_CONDITIONAL_GROWTH

    lines = []
    for i, s in enumerate(sorted_scores):
        season_str = str(s.season.value)
        entry = f"{season_str.capitalize()} {s.year}: RIT {s.rit_score}"
        if i > 0:
            prev = sorted_scores[i - 1]
            delta = s.rit_score - prev.rit_score
            sign = "+" if delta >= 0 else ""
            entry += f" ({sign}{delta} from prior)"
        lines.append(entry)

    timeline = " → ".join(lines)

    # Add key computed comparisons
    if len(sorted_scores) >= 2:
        first = sorted_scores[0]
        last = sorted_scores[-1]
        total_growth = last.rit_score - first.rit_score
        timeline += f"\n\nTotal growth: {total_growth} RIT points over {len(sorted_scores)} test sessions"

        # Find same-season comparisons (e.g. winter-to-winter)
        season_groups: dict[str, list[ScoreInput]] = {}
        for s in sorted_scores:
            season_groups.setdefault(str(s.season.value), []).append(s)
        for season_name, group in season_groups.items():
            if len(group) >= 2:
                earliest = group[0]
                latest = group[-1]
                yoy = latest.rit_score - earliest.rit_score
                timeline += (
                    f"\n{season_name.capitalize()}-to-{season_name.capitalize()} growth: "
                    f"{earliest.rit_score} ({earliest.year}) → {latest.rit_score} ({latest.year}) = "
                    f"{'+' if yoy >= 0 else ''}{yoy} RIT over {latest.year - earliest.year} year(s)"
                )

        # Detect spring-to-fall drops (sawtooth pattern)
        for i in range(1, len(sorted_scores)):
            curr = sorted_scores[i]
            prev = sorted_scores[i - 1]
            if str(prev.season.value) == "spring" and str(curr.season.value) == "fall":
                drop = curr.rit_score - prev.rit_score
                if drop < 0:
                    timeline += (
                        f"\nNOTE: Score DROPPED {abs(drop)} points from "
                        f"Spring {prev.year} ({prev.rit_score}) to Fall {curr.year} ({curr.rit_score}) "
                        f"when entering new grade"
                    )

        # Fall-to-spring actual vs expected growth comparison
        fall_scores = season_groups.get("fall", [])
        spring_scores = season_groups.get("spring", [])
        if fall_scores and spring_scores:
            timeline += "\n\nActual vs Expected Growth (compared to peers who started at the same level):"
            for fall_s in fall_scores:
                matching_spring = [
                    sp for sp in spring_scores if sp.year == fall_s.year + 1
                ]
                if not matching_spring:
                    continue
                spring_s = matching_spring[0]
                actual_growth = spring_s.rit_score - fall_s.rit_score

                school_year_grade = max(0, min(grade - (last.year - fall_s.year), 5))
                if str(last.season.value) in ("winter", "spring"):
                    school_year_grade = max(
                        0, min(grade - (last.year - fall_s.year - 1), 5)
                    )

                fall_pct = estimate_percentile(
                    fall_s.rit_score, school_year_grade, "fall", subject
                )
                cond_growth = NWEA_CONDITIONAL_GROWTH[subject].get(
                    school_year_grade,
                    NWEA_CONDITIONAL_GROWTH[subject].get(3, {}),
                )

                pct_brackets = sorted(cond_growth.keys())
                nearest_bracket = min(pct_brackets, key=lambda p: abs(p - fall_pct))
                expected = cond_growth[nearest_bracket]

                diff = actual_growth - expected
                diff_str = f"{'+' if diff >= 0 else ''}{diff}"
                timeline += (
                    f"\n  Grade {school_year_grade} ({fall_s.year}-{spring_s.year}): "
                    f"Grew {actual_growth} RIT (Fall {fall_s.rit_score} → Spring {spring_s.rit_score}). "
                    f"Students nationally who started at the {fall_pct}th percentile grew ~{expected} RIT. "
                    f"Difference: {diff_str} RIT."
                )
                if diff < 0:
                    timeline += " ⚠ BELOW expected growth for similar-level peers."
                elif diff > 2:
                    timeline += " ✓ ABOVE expected growth for similar-level peers."

    return timeline


def detect_trend(
    scores: list[ScoreInput], grade: int = 3, subject: str = "math"
) -> tuple[Trend | None, str | None]:
    """Use Gemma 4 to analyze growth trend from MAP scores."""
    if len(scores) < 2:
        logger.info("detect_trend: skipping — fewer than 2 scores")
        return None, None

    import ollama

    sorted_scores = _sort_scores(scores)
    timeline = _build_timeline(sorted_scores, grade, subject)
    latest = sorted_scores[-1]
    latest_rit = latest.rit_score
    latest_season = (
        str(latest.season.value)
        if hasattr(latest.season, "value")
        else str(latest.season)
    )

    logger.info(
        "detect_trend: grade=%s, latest_rit=%s, season=%s, subject=%s",
        grade,
        latest_rit,
        latest_season,
        subject,
    )

    prompt = build_trend_prompt(grade, timeline, latest_rit, latest_season, subject)

    logger.info("detect_trend: calling Gemma 4 (%s)...", MODEL)
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
        options={"temperature": 0},
    )
    logger.info("detect_trend: Gemma 4 response received")

    raw = response.message.content.strip()
    logger.info("detect_trend: raw response (first 500 chars): %s", raw[:500])

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("detect_trend: JSON parse failed (%s), attempting repair", e)
        parsed = {}
        for key in (
            "trend",
            "where_they_stand",
            "growth_pattern",
            "what_this_means",
            "recommendation",
        ):
            m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            if m:
                parsed[key] = m.group(1)
        if not parsed.get("trend"):
            logger.error("detect_trend: repair failed, raw: %s", raw[:500])
            return Trend("stalling"), "- **Error:** Could not parse trend analysis"
        logger.info("detect_trend: repaired — extracted %d fields", len(parsed))

    logger.info("detect_trend: parsed response — trend=%s", parsed.get("trend"))

    trend_value = parsed.get("trend", "stalling")
    trend = Trend(trend_value)

    bullets = []
    if parsed.get("where_they_stand"):
        bullets.append(f"- **Where they stand:** {parsed['where_they_stand']}")
    if parsed.get("growth_pattern"):
        bullets.append(f"- **Growth pattern:** {parsed['growth_pattern']}")
    if parsed.get("what_this_means"):
        bullets.append(f"- **What this means:** {parsed['what_this_means']}")
    if parsed.get("recommendation"):
        bullets.append(f"- **Recommendation:** {parsed['recommendation']}")
    analysis = "\n".join(bullets) if bullets else parsed.get("analysis", "")

    return trend, analysis


def get_cached_analysis(
    student_id: int, db: "Session", subject: str = "math"
) -> CurriculumResult | None:
    """Load cached analysis from DB if it exists.

    :param student_id: Student primary key.
    :param db: SQLAlchemy session.
    :param subject: Subject to look up.
    :return: CurriculumResult or None if no cache.
    """
    from src.models.database import StudentAnalysis

    row = (
        db.query(StudentAnalysis)
        .filter(
            StudentAnalysis.student_id == student_id,
            StudentAnalysis.subject == subject,
        )
        .first()
    )
    if row is None:
        return None

    develop = BandInfo(**row.develop_band_json)
    introduce = BandInfo(**row.introduce_band_json)
    trend = Trend(row.trend) if row.trend else None
    return CurriculumResult(
        rit_score=row.latest_rit,
        develop_band=develop,
        introduce_band=introduce,
        trend=trend,
        trend_detail=row.trend_detail,
        subject=subject,
    )


def get_cached_scores_hash(
    student_id: int, db: "Session", subject: str = "math"
) -> str | None:
    """Return the scores_hash for a cached analysis, or None.

    :param student_id: Student primary key.
    :param db: SQLAlchemy session.
    :param subject: Subject to look up.
    :return: Hex digest string or None.
    """
    from src.models.database import StudentAnalysis

    row = (
        db.query(StudentAnalysis)
        .filter(
            StudentAnalysis.student_id == student_id,
            StudentAnalysis.subject == subject,
        )
        .first()
    )
    return row.scores_hash if row else None


def save_analysis_cache(
    student_id: int,
    curriculum_result: CurriculumResult,
    scores_hash: str,
    grade: int,
    db: "Session",
    subject: str = "math",
) -> None:
    """Upsert a StudentAnalysis row for the given student and subject.

    :param student_id: Student primary key.
    :param curriculum_result: The analysis result to cache.
    :param scores_hash: SHA-256 hash of current scores.
    :param grade: Student grade.
    :param db: SQLAlchemy session.
    :param subject: Subject for this analysis.
    """
    from datetime import datetime, timezone

    from src.models.database import StudentAnalysis

    row = (
        db.query(StudentAnalysis)
        .filter(
            StudentAnalysis.student_id == student_id,
            StudentAnalysis.subject == subject,
        )
        .first()
    )
    values = {
        "trend": curriculum_result.trend.value if curriculum_result.trend else None,
        "trend_detail": curriculum_result.trend_detail,
        "develop_band": curriculum_result.develop_band.band,
        "develop_band_json": curriculum_result.develop_band.model_dump(),
        "introduce_band": curriculum_result.introduce_band.band,
        "introduce_band_json": curriculum_result.introduce_band.model_dump(),
        "latest_rit": curriculum_result.rit_score,
        "scores_hash": scores_hash,
        "grade": grade,
        "analyzed_at": datetime.now(timezone.utc),
    }
    if row:
        for k, v in values.items():
            setattr(row, k, v)
    else:
        row = StudentAnalysis(student_id=student_id, subject=subject, **values)
        db.add(row)
    db.commit()


def map_rit_to_curriculum(
    rit_score: int,
    scores: list[ScoreInput] | None = None,
    grade: int = 3,
    subject: str = "math",
) -> CurriculumResult:
    """Map a RIT score to its Develop and Introduce bands."""
    develop_key = _score_to_band_key(rit_score, subject)

    if develop_key is None:
        data = _load_curriculum(subject)
        keys = list(data["bands"].keys())
        first_low = int(keys[0].split("-")[0])

        if rit_score < first_low:
            develop_key = keys[0]
        else:
            develop_key = keys[-1]

    introduce_key = _next_band_key(develop_key, subject)
    if introduce_key is None:
        introduce_key = develop_key

    trend, trend_detail = (
        detect_trend(scores, grade, subject) if scores else (None, None)
    )

    return CurriculumResult(
        rit_score=rit_score,
        develop_band=_band_key_to_info(develop_key, subject),
        introduce_band=_band_key_to_info(introduce_key, subject),
        trend=trend,
        trend_detail=trend_detail,
        subject=subject,
    )
