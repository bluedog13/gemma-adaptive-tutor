# Plan: Image-Based Score Extraction

**Status:** Implemented (testing with real PDF)
**Created:** 2026-04-04

## Goal

Allow users to upload an image (screenshot/photo) or PDF of NWEA MAP score reports. The app parses the file and auto-populates score fields. Also remove the current 3-score limit — support as many scores as the image contains.

## Why

- Parents/teachers often have score reports as PDFs or screenshots — manual entry is tedious and error-prone
- The app currently caps at 3 scores, but students may have 6+ semesters of history
- More data points = better trend analysis and charting

## Implementation (Actual)

### 1. `src/tools/score_extractor.py` — NEW file

Three-tier extraction strategy for PDFs:

1. **Regex parsing** (instant, 100% accurate) — `_parse_scores_regex()` uses `re.compile` to match `(WI|FA|SP)(\d{2})\n(\d{2}|KG)\n(\d+)-(\d+)-(\d+)` patterns in PyMuPDF-extracted text. Extracts the MIDDLE number from the RIT triplet. Scopes to a single subject section (default "Math") by finding section boundaries between subject headers.
2. **Gemma text mode** — `_extract_from_text()` sends raw PDF text to Gemma as a plain text prompt (no vision). Fallback if regex finds no matches (non-standard PDF format).
3. **Gemma vision mode** — `_extract_from_single_image()` renders PDF pages as images at 300 DPI and sends to Gemma with vision. Last resort for scanned PDFs with no extractable text.

For image uploads (.png/.jpg), only vision mode is used.

**Key functions:**
- `extract_scores_from_file(file_path)` — main entry point, dispatches by file type
- `_pdf_to_text(pdf_path)` — PyMuPDF `page.get_text()` for all pages
- `_parse_scores_regex(text, subject="Math")` — regex parser, parameterized by subject for future Science/Reading support
- `_build_text_prompt(text, subject)` — builds Gemma text prompt scoped to a subject
- `_extract_from_text(text, subject)` — Gemma text mode extraction
- `_extract_from_single_image(image_path)` — Gemma vision extraction
- `_pdf_to_images(pdf_path)` — renders pages at 300 DPI via PyMuPDF
- `_merge_results(results)` — deduplicates scores from multi-page PDFs (vision fallback)
- `_parse_gemma_response(content)` — normalizes Gemma JSON, strips markdown code fences, validates RIT range (100-350), normalizes seasons

### 2. `src/models/schemas.py`

- Removed `max_length=3` from `StudentInput.scores` field
- Changed description to `"MAP scores (one or more)"`

### 3. `frontend/app.py` — Major UI refactor

**Replaced 3 fixed score rows with `@gr.render` + `gr.State` pattern:**
- `scores_state = gr.State(value=[...])` holds list of score dicts
- `@gr.render(inputs=scores_state)` dynamically renders score rows with proper dropdowns (Season, Grade)
- Add/Remove buttons modify the state list, triggering re-render
- `register_btn.click()` wired INSIDE `@gr.render` to read dynamic component values at submit time

**Why not `gr.Dataframe`:** Gradio 6's Dataframe has bugs with dynamic row addition ("Add Row" button doesn't work reliably, grid doesn't resize). The `@gr.render` pattern gives full control over each row's components (dropdowns for Season/Grade instead of free-text).

**Grade display:** Uses "KG" instead of "0" for kindergarten. `_grade_to_int()` helper converts "KG" → 0 internally wherever integer grade is needed.

**Image/PDF upload section:**
- `gr.File` component accepts .png, .jpg, .jpeg, .pdf, .webp, .bmp
- "Extract Scores with Gemma 4" button triggers extraction
- Auto-fills student name, current grade, and all score rows
- Status message shows count of extracted scores

**`register_student(name, grade, scores_data: list[dict])`** — takes 3 args instead of 14 positional args. Iterates score dicts, normalizes, validates.

**`load_student()`** — returns list of dicts for scores_state instead of flat field tuple.

**Removed `auto_calc_grades()`** — grade is either from the report or computed during analysis.

### 4. `frontend/__main__.py` — NEW entry point

```python
from frontend.app import custom_css, demo, theme
demo.launch(server_port=7860, theme=theme, css=custom_css)
```

Theme/CSS moved to `launch()` due to Gradio 6 deprecation of passing them to `Blocks()`.

### 5. Other changes

- `justfile` — `app` recipe updated to `uv run python -m frontend`
- `pyproject.toml` — added `pymupdf` dependency
- `.vscode/launch.json` — debug configurations for Gradio and FastAPI

## Files Changed

| File | Change |
|------|--------|
| `src/tools/score_extractor.py` | **New** — 3-tier extraction: regex → Gemma text → Gemma vision |
| `src/models/schemas.py` | Remove `max_length=3` from `StudentInput.scores` |
| `frontend/app.py` | Replace fixed score rows with `@gr.render` + State; image upload; refactor `register_student`, `load_student`; KG grade support |
| `frontend/__main__.py` | **New** — entry point with theme/css in `launch()` |
| `frontend/__init__.py` | **New** — empty init |
| `justfile` | Updated `app` recipe |
| `pyproject.toml` | Added `pymupdf` |
| `.vscode/launch.json` | **New** — debug configs |

## Key Design Decisions

- **Regex-first for PDFs**: PyMuPDF extracts clean text from NWEA PDFs. Regex parsing is instant, 100% accurate, and avoids LLM hallucinations. Gemma is only used as fallback.
- **Subject parameterization**: `_parse_scores_regex(text, subject="Math")` and `_build_text_prompt(text, subject)` accept a subject parameter. Today defaults to "Math"; ready for Science/Reading when needed.
- **@gr.render over gr.Dataframe**: Dataframe has Gradio 6 bugs with dynamic rows. `@gr.render` gives full control with proper dropdowns.
- **Scores in report order**: Regex parser preserves PDF document order (most recent first) rather than re-sorting, matching what users see on the paper report.
- **KG not 0**: Grade dropdowns show "KG" for kindergarten. `_grade_to_int()` handles conversion internally.
- **Prompt in extractor, not prompts.py**: The vision/text prompts are tightly coupled to the extraction logic and response parsing.

## Gotchas

### Gemma vision accuracy on dense tables
Gemma 4 E4B's vision mode struggles with dense NWEA tables: extracts wrong RIT values (takes last number in triplet instead of middle), misreads seasons, misses rows, and conflates data from Math/Reading/Science sections. **Always prefer text extraction over vision for PDFs.**

### PyMuPDF text extraction format
`page.get_text()` returns text with newlines between table cells, not tabs or spaces. The regex pattern depends on this: `(WI|FA|SP)(\d{2})\n(\d{2}|KG)\n(\d+)-(\d+)-(\d+)`. If NWEA changes their PDF layout, this regex will break — fall back to Gemma text mode.

### Python `.format()` and JSON curly braces
The text extraction prompt contains JSON examples with `{}`. Using `.format(text=text)` on such a string causes `KeyError` because Python interprets `{` as format placeholders. Solution: use string concatenation or a builder function, not `.format()`.

### `grade=0` is falsy in Python
Kindergarten grade is 0, which is falsy. Any check like `if grade:` or `if s.get("grade"):` will skip kindergarten scores. Always use `is not None` checks: `if s.get("grade") is not None`.

### Gradio 6 `@gr.render` re-render loop
Adding `.change()` handlers on components inside `@gr.render` that update the render's input state causes an infinite loop (change → state update → re-render → new components → change fires again). Solution: wire `register_btn.click()` INSIDE the render block to read component values only at submit time, not on every change.

### Gradio 6 theme/CSS deprecation
Passing `theme=` or `css=` to `gr.Blocks()` is deprecated in Gradio 6. Must pass to `demo.launch(theme=theme, css=custom_css)` instead. This required creating `frontend/__main__.py` as the entry point.

### SEASON_ORDER is calendar, not school-year
`SEASON_ORDER` in constants.py uses calendar order (spring=0, fall=1, winter=2). This means sorting by `(year, SEASON_ORDER)` descending puts winter first within a year, but the NWEA report shows winter-fall-spring within a school year. For display order, preserve document order from the PDF rather than re-sorting.

### Markdown code fences in Gemma JSON output
Gemma often wraps JSON responses in ` ```json ... ``` ` markdown blocks. `json.loads()` will crash on these. The `_parse_gemma_response()` function strips code fences before parsing.

### `max(1, grade)` clamps KG to grade 1
Several places used `max(1, ...)` when clamping grades, which prevented grade 0 (KG) from being used for norms lookup. The chart's expected growth line, `_grade_for_score()`, `estimate_percentile()`, and norm band annotations all needed `max(0, ...)` instead.

### Expected line was aspirational, not normative
The original expected (green) line assumed a student should maintain their exact starting percentile rank forever. This is wrong — NWEA norms are *descriptive* (what students actually do), and high-percentile students nationally show lower growth than median students. A 99th-percentile KG student does NOT typically stay at 99th by grade 2. Fixed by changing the expected line to use `estimate_percentile()` to find the starting percentile, clamp to available data (5th-95th), then look up what students at that percentile level *actually score* at each subsequent grade/season. The line now shows national norms for same-level peers, not an idealized trajectory. Label changed from "Expected" to "{pct}th pct norm: {rit}".

### Percentile season mismatch
`estimate_percentile()` and `_build_norms_context()` defaulted to "fall" season regardless of when the latest score was taken. A Winter RIT of 196 at grade 2 is ~83rd percentile (Winter norms), not ~93rd (Fall norms). Fixed by threading the `season` parameter through `detect_trend()` → `build_trend_prompt()` → `_build_norms_context()`.

### Gemma trend analysis too positive
Gemma would say "strong growth" even when a student had zero net growth over 9 months (sawtooth: 196 → 193 → 196). Fixed by: (1) adding explicit rules to the prompt about honesty, (2) computing and including actual vs expected growth comparisons in the timeline fed to Gemma, (3) flagging sawtooth patterns in the timeline data.

## Other Changes

### `src/constants.py` — KG norms data
Added grade 0 (KG) to `NWEA_NORMS`, `NWEA_PERCENTILES`, and `NWEA_CONDITIONAL_GROWTH` from official NWEA 2025 Technical Manual (Tables A.1, B.1, B.3, B.5). Changed all `max(1, grade)` to `max(0, grade)` in `estimate_percentile()` and `get_percentile_cutoffs()`.

### `src/prompts.py` — Season-aware norms and honest analysis
- `_build_norms_context()` and `build_trend_prompt()` now accept a `season` parameter for correct percentile lookup
- Prompt includes conditional growth context: compares student growth against peers who started at the same percentile level nationally
- Explicit analysis rules: flag sawtooth, detect stalling, be honest about zero net growth

### `src/tools/curriculum.py` — Timeline and trend improvements
- `_sort_scores()` uses chronological order (`winter=0, spring=1, fall=2`) instead of `SEASON_ORDER`
- `_build_timeline()` now includes: delta from prior score, total growth, same-season comparisons, spring-to-fall drop detection, and fall-to-spring actual vs expected growth comparison
- `detect_trend()` passes correct season to prompt builder

## Future Extensions

- **Science/Reading extraction**: Change `subject` parameter from `"Math"` to `"Science"` or `"Reading"`. Regex and text prompts already parameterized.
- **Multi-student PDFs**: Current regex extracts one student. Could extend to detect multiple student sections.
- **Confidence scoring**: Compare regex and Gemma results to flag discrepancies.
