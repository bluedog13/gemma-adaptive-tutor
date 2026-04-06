"""Score extraction from images and PDFs using Gemma 4 vision capabilities."""

import json
import logging
import re
import tempfile
from pathlib import Path

import fitz
import ollama

from src.constants import MODEL

logger = logging.getLogger("map_accelerator")


def _build_vision_prompt(subject: str = "Math") -> str:
    """Build a vision extraction prompt for a specific subject.

    :param subject: Subject to extract (e.g. "Math", "Reading", "Science").
    :return: Complete vision prompt string.
    """
    other_subjects = ", ".join(
        s for s in ["Math", "Reading", "Science", "Language Usage"] if s != subject
    )
    return (
        "You are analyzing a screenshot or photo of an NWEA MAP Growth score report.\n\n"
        f"This report contains tables of test scores. Look for the {subject.upper()} "
        "section table.\n"
        "Each row has: Term/Year, Grade, RIT Score (+/- Std Err), and other columns.\n\n"
        "IMPORTANT FORMAT DETAILS:\n"
        "- Term abbreviations: WI = winter, FA = fall, SP = spring\n"
        "- Year abbreviations: 26 = 2026, 25 = 2025, 24 = 2024, 23 = 2023, etc.\n"
        "  So WI26 = winter 2026, FA25 = fall 2025, SP24 = spring 2024\n"
        "- RIT scores appear as three numbers like '193-196-199' — the MIDDLE number\n"
        "  is the actual RIT score (the others are the standard error range)\n"
        "- Grade may show as 02, 01, KG (kindergarten=0), etc.\n\n"
        f"Extract ALL {subject} scores from the table. Do NOT include scores from "
        f"{other_subjects}.\n"
        "Return a JSON object:\n"
        "{\n"
        '  "student_name": "student name if visible, or empty string",\n'
        '  "grade": current grade level as integer (or null),\n'
        '  "scores": [\n'
        "    {\n"
        '      "rit_score": <the MIDDLE number from the RIT Score column>,\n'
        '      "season": "fall" or "winter" or "spring",\n'
        '      "year": <four-digit year, e.g. 2025>,\n'
        '      "grade": <grade as integer, KG=0>\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        f"- Extract EVERY row from the {subject} scores table ONLY\n"
        "- The RIT score is ALWAYS the MIDDLE of the three numbers\n"
        "- Convert term codes: WI->winter, FA->fall, SP->spring\n"
        "- Convert 2-digit years to 4-digit: 26->2026, 25->2025, 24->2024, 23->2023\n"
        "- Convert grades: KG->0, 01->1, 02->2, etc.\n"
        "- Return ONLY valid JSON\n\n"
        "JSON:"
    )


def _build_text_prompt(text: str, subject: str = "Math") -> str:
    """Build a text extraction prompt for a specific subject.

    :param text: Raw text extracted from the PDF.
    :param subject: Subject to extract scores for (e.g. "Math", "Reading", "Science").
    :return: Complete prompt string.
    """
    return (
        "You are parsing extracted text from an NWEA MAP Growth score report.\n\n"
        f"Below is the raw text from the PDF. Find ONLY the {subject.upper()} section "
        f"and extract ALL score rows from that table. STOP when the {subject.upper()} "
        "section ends — do NOT include scores from other subjects like "
        + ", ".join(
            s for s in ["Math", "Reading", "Science", "Language Usage"] if s != subject
        )
        + ".\n\n"
        "IMPORTANT FORMAT DETAILS:\n"
        "- Term abbreviations: WI = winter, FA = fall, SP = spring\n"
        "- Year abbreviations: 26 = 2026, 25 = 2025, 24 = 2024, 23 = 2023, etc.\n"
        "- RIT scores appear as three numbers like '193-196-199' — the MIDDLE number\n"
        "  is the actual RIT score (the others are the standard error range)\n"
        "- Grade may show as 02, 01, KG (kindergarten=0), etc.\n\n"
        "Return a JSON object with keys: student_name (string), grade (integer or null), "
        "and scores (array of objects with rit_score, season, year, grade).\n\n"
        "Example: A row showing 'WI26  02  193-196-199' means:\n"
        '  rit_score=196, season="winter", year=2026, grade=2\n\n'
        "Example: A row showing 'FA23  KG  167-170-173' means:\n"
        '  rit_score=170, season="fall", year=2023, grade=0\n\n'
        "Rules:\n"
        f"- Extract EVERY row from the {subject} scores table ONLY\n"
        "- Sort scores from most recent to oldest\n"
        "- The RIT score is ALWAYS the MIDDLE of the three numbers\n"
        "- Convert term codes: WI->winter, FA->fall, SP->spring\n"
        "- Convert 2-digit years to 4-digit: 26->2026, 25->2025, 24->2024, 23->2023\n"
        "- Convert grades: KG->0, 01->1, 02->2, etc.\n"
        "- Return ONLY valid JSON, no markdown formatting\n\n"
        f"--- REPORT TEXT ---\n{text}\n--- END ---\n\nJSON:"
    )


def _parse_gemma_response(content: str) -> dict:
    """Parse and normalize Gemma's JSON response into a scores dict.

    :param content: Raw JSON string from Gemma.
    :return: Dict with ``student_name``, ``grade``, and ``scores``.
    """
    # Strip markdown code fences if present
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # Remove opening ```json or ``` and closing ```
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    parsed = json.loads(cleaned)

    result: dict = {
        "student_name": parsed.get("student_name", ""),
        "grade": parsed.get("grade"),
        "scores": [],
    }

    for score in parsed.get("scores", []):
        season = str(score.get("season", "")).lower().strip()
        if season in ("autumn",):
            season = "fall"
        if season not in ("fall", "winter", "spring"):
            continue

        try:
            rit = int(score["rit_score"])
            year = int(score["year"])
        except (KeyError, ValueError, TypeError):
            continue

        if not (100 <= rit <= 350):
            continue

        grade_at_test = score.get("grade")
        if grade_at_test is not None:
            try:
                grade_at_test = int(grade_at_test)
            except (ValueError, TypeError):
                grade_at_test = None

        result["scores"].append(
            {
                "rit_score": rit,
                "season": season,
                "year": year,
                "grade": grade_at_test,
            }
        )

    return result


def _extract_from_single_image(image_path: str, subject: str = "Math") -> dict:
    """Send a single image to Gemma 4 and parse the response.

    :param image_path: Path to an image file (PNG/JPG).
    :param subject: Subject to extract (e.g. "Math", "Reading", "Science").
    :return: Parsed scores dict.
    """
    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": _build_vision_prompt(subject),
                "images": [image_path],
            }
        ],
        format="json",
    )

    content = (response.message.content or "").strip()
    logger.info("Gemma vision response (%s): %s", subject, content[:500])
    return _parse_gemma_response(content)


def _extract_from_text(text: str, subject: str = "Math") -> dict:
    """Send extracted PDF text to Gemma 4 for parsing (no vision needed).

    :param text: Raw text extracted from PDF pages.
    :param subject: Subject to extract scores for.
    :return: Parsed scores dict.
    """
    prompt = _build_text_prompt(text, subject)
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )

    content = (response.message.content or "").strip()
    logger.info("Gemma text extraction response: %s", content[:500])
    return _parse_gemma_response(content)


_SEASON_MAP = {"WI": "winter", "FA": "fall", "SP": "spring"}

# Matches rows like: WI26\n02\n193-196-199  or  FA23\nKG\n167-170-173
_SCORE_ROW_RE = re.compile(
    r"(WI|FA|SP)(\d{2})\n"  # term code + 2-digit year
    r"(\d{2}|KG)\n"  # grade (02, 01, KG)
    r"(\d+)-(\d+)-(\d+)"  # low-middle-high RIT range
)


def _parse_scores_regex(text: str, subject: str = "Math") -> dict:
    """Parse NWEA MAP scores from raw PDF text using regex.

    :param text: Raw text extracted from PDF pages.
    :param subject: Subject section to extract (e.g. "Math", "Reading", "Science").
    :return: Dict with ``student_name``, ``grade``, and ``scores``, or empty
             scores list if the subject section wasn't found.
    """
    # Extract student name (appears on the line before "Student ID:")
    name_match = re.search(r"\n(.+?)\nStudent ID:", text)
    student_name = name_match.group(1).strip() if name_match else ""

    # Find the subject section — text between "Math:" header and next subject header
    subject_headers = [
        r"Math: Math",
        r"Language Arts: Reading",
        r"Science: Science",
    ]
    # Build pattern to isolate the target subject section
    subject_pattern = None
    for header in subject_headers:
        if subject.lower() in header.lower():
            subject_pattern = header
            break

    if not subject_pattern:
        logger.warning("Unknown subject: %s", subject)
        return {"student_name": student_name, "grade": None, "scores": []}

    # Find start of target section
    section_start = text.find(subject_pattern)
    if section_start == -1:
        logger.warning("Subject section '%s' not found in PDF text", subject)
        return {"student_name": student_name, "grade": None, "scores": []}

    # Find end: next subject header or end of text
    section_text = text[section_start:]
    other_headers = [h for h in subject_headers if h != subject_pattern]
    section_end = len(section_text)
    for h in other_headers:
        idx = section_text.find(h)
        if idx > 0:
            section_end = min(section_end, idx)
    section_text = section_text[:section_end]

    logger.info("Subject section (%s): %d chars", subject, len(section_text))

    # Extract all score rows from the section
    scores: list[dict] = []
    for match in _SCORE_ROW_RE.finditer(section_text):
        term_code, year_short, grade_str, _, middle, _ = match.groups()

        season = _SEASON_MAP.get(term_code, "")
        year = 2000 + int(year_short)
        rit = int(middle)
        grade = "KG" if grade_str == "KG" else int(grade_str)

        scores.append(
            {
                "rit_score": rit,
                "season": season,
                "year": year,
                "grade": grade,
            }
        )

    # Scores are already in report order (most recent first) — preserve it

    # Infer current grade from most recent score
    current_grade = scores[0]["grade"] if scores else None

    logger.info("Regex extracted %d %s scores", len(scores), subject)
    return {
        "student_name": student_name,
        "grade": current_grade,
        "scores": scores,
    }


def _pdf_to_text(pdf_path: str) -> str:
    """Extract raw text from all pages of a PDF.

    :param pdf_path: Path to the PDF file.
    :return: Concatenated text from all pages.
    """
    doc = fitz.open(pdf_path)
    pages_text: list[str] = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = str(page.get_text())
        if text.strip():
            pages_text.append(text)
            logger.info("PDF page %d: %d chars of text", page_num + 1, len(text))
    doc.close()
    return "\n\n".join(pages_text)


def _pdf_to_images(pdf_path: str) -> list[str]:
    """Convert each page of a PDF to a temporary PNG file.

    :param pdf_path: Path to the PDF file.
    :return: List of temporary image file paths.
    """
    doc = fitz.open(pdf_path)
    image_paths: list[str] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Render at 2x resolution for better OCR
        pix = page.get_pixmap(dpi=300)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        pix.save(tmp.name)
        image_paths.append(tmp.name)
        logger.info("Converted PDF page %d to %s", page_num + 1, tmp.name)

    doc.close()
    return image_paths


def _merge_results(results: list[dict]) -> dict:
    """Merge extraction results from multiple pages.

    :param results: List of parsed score dicts (one per page).
    :return: Single merged dict with deduplicated scores.
    """
    merged: dict = {
        "student_name": "",
        "grade": None,
        "scores": [],
    }

    seen_scores: set[tuple[int, str, int]] = set()

    for r in results:
        if r.get("student_name") and not merged["student_name"]:
            merged["student_name"] = r["student_name"]
        if r.get("grade") is not None and merged["grade"] is None:
            merged["grade"] = r["grade"]

        for s in r.get("scores", []):
            key = (s["rit_score"], s["season"], s["year"])
            if key not in seen_scores:
                seen_scores.add(key)
                merged["scores"].append(s)

    # Sort most recent first
    from src.constants import SEASON_ORDER

    merged["scores"].sort(
        key=lambda s: (s["year"], SEASON_ORDER.get(s["season"], 0)),
        reverse=True,
    )

    return merged


def extract_scores_from_file(file_path: str) -> dict:
    """Extract MAP scores from an uploaded image or PDF.

    :param file_path: Path to the uploaded file (image or PDF).
    :return: Dict with keys ``student_name``, ``grade``, and ``scores``.
    :raises json.JSONDecodeError: If Gemma returns unparseable output.
    :raises ValueError: If the file type is not supported.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    logger.info("Extracting scores from file: %s (type: %s)", file_path, suffix)

    if suffix == ".pdf":
        # Extract text from PDF
        text = _pdf_to_text(file_path)
        if text.strip():
            logger.info("Extracted %d chars of text from PDF", len(text))

            # Try regex parsing first (fastest, most accurate)
            result = _parse_scores_regex(text)
            if result["scores"]:
                logger.info("Regex extracted %d scores", len(result["scores"]))
                return result
            logger.warning("Regex found no scores, falling back to Gemma text mode")

            # Fall back to Gemma text mode
            result = _extract_from_text(text)
            if result["scores"]:
                logger.info(
                    "Gemma text extraction got %d scores", len(result["scores"])
                )
                return result
            logger.warning(
                "Gemma text extraction returned no scores, falling back to vision"
            )

        # Fallback: render pages as images and use vision
        image_paths = _pdf_to_images(file_path)
        if not image_paths:
            raise ValueError("PDF has no pages")

        results = []
        for img_path in image_paths:
            try:
                results.append(_extract_from_single_image(img_path))
            except Exception:
                logger.warning(
                    "Failed to extract from page: %s", img_path, exc_info=True
                )

        if not results:
            raise ValueError("Could not extract scores from any PDF page")

        merged = _merge_results(results)
        logger.info(
            "Extracted %d scores from %d PDF pages (vision fallback)",
            len(merged["scores"]),
            len(image_paths),
        )
        return merged

    elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"):
        result = _extract_from_single_image(file_path)
        logger.info("Extracted %d scores from image", len(result["scores"]))
        return result

    else:
        raise ValueError(
            f"Unsupported file type: {suffix}. Please upload a PNG, JPG, or PDF file."
        )


_SUBJECT_KEYS = {
    "Math": "math",
    "Reading": "reading",
    "Science": "science",
}


def extract_all_subjects_from_file(file_path: str) -> dict[str, dict]:
    """Extract MAP scores for all subjects found in an uploaded file.

    :param file_path: Path to the uploaded file (image or PDF).
    :return: Dict keyed by subject (e.g. ``{"math": {scores...}, "reading": {scores...}}``).
             Only subjects with scores are included.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    logger.info("Extracting all subjects from file: %s (type: %s)", file_path, suffix)

    results: dict[str, dict] = {}
    errors: list[Exception] = []

    if suffix == ".pdf":
        text = _pdf_to_text(file_path)
        if text.strip():
            for display_name, subject_key in _SUBJECT_KEYS.items():
                try:
                    result = _parse_scores_regex(text, display_name)
                    if result["scores"]:
                        results[subject_key] = result
                        logger.info(
                            "Regex extracted %d %s scores",
                            len(result["scores"]),
                            subject_key,
                        )
                        continue
                except Exception as e:
                    errors.append(e)
                    logger.warning(
                        "Regex extraction failed for %s",
                        subject_key,
                        exc_info=True,
                    )

                # Fall back to Gemma text mode for this subject
                try:
                    result = _extract_from_text(text, display_name)
                    if result["scores"]:
                        results[subject_key] = result
                        logger.info(
                            "Gemma text extracted %d %s scores",
                            len(result["scores"]),
                            subject_key,
                        )
                except Exception as e:
                    errors.append(e)
                    logger.warning(
                        "Gemma text extraction failed for %s",
                        subject_key,
                        exc_info=True,
                    )

        # For any subjects still missing after text extraction, render pages
        # as images and try per-subject vision extraction.  Accumulate
        # results across pages and merge (a subject's scores may span pages).
        missing_subjects = {
            dn: sk for dn, sk in _SUBJECT_KEYS.items() if sk not in results
        }
        if missing_subjects:
            image_paths = _pdf_to_images(file_path)
            # Collect per-page results for each subject
            page_results: dict[str, list[dict]] = {
                sk: [] for sk in missing_subjects.values()
            }
            for img_path in image_paths:
                for display_name, subject_key in missing_subjects.items():
                    try:
                        result = _extract_from_single_image(img_path, display_name)
                        if result["scores"]:
                            page_results[subject_key].append(result)
                            logger.info(
                                "Vision fallback extracted %d %s scores from PDF page",
                                len(result["scores"]),
                                subject_key,
                            )
                    except Exception as e:
                        errors.append(e)
                        logger.warning(
                            "Vision fallback failed for %s on page %s",
                            subject_key,
                            img_path,
                            exc_info=True,
                        )
            # Merge multi-page results per subject
            for subject_key, page_list in page_results.items():
                if page_list:
                    results[subject_key] = _merge_results(page_list)

    elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"):
        # Vision mode — try each subject
        for display_name, subject_key in _SUBJECT_KEYS.items():
            try:
                result = _extract_from_single_image(file_path, display_name)
                if result["scores"]:
                    results[subject_key] = result
                    logger.info(
                        "Vision extracted %d %s scores",
                        len(result["scores"]),
                        subject_key,
                    )
            except Exception as e:
                errors.append(e)
                logger.warning(
                    "Vision extraction failed for %s",
                    subject_key,
                    exc_info=True,
                )

    else:
        raise ValueError(
            f"Unsupported file type: {suffix}. Please upload a PNG, JPG, or PDF file."
        )

    # If no scores were found but errors occurred, surface the failure
    # instead of silently returning an empty dict.
    if not results and errors:
        raise RuntimeError(
            f"Score extraction failed for all subjects. Last error: {errors[-1]}"
        ) from errors[-1]

    logger.info(
        "Extracted subjects: %s",
        {k: len(v.get("scores", [])) for k, v in results.items()},
    )
    return results
