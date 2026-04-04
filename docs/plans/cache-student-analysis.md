# Plan: Cache Student Analysis Results

**Status:** Done
**Created:** 2026-04-04

## Context

Every time a student is loaded or analyzed, the app calls Gemma 4 (`detect_trend()`) which takes ~30 seconds. The result is deterministic for a given set of scores. The user wants instant loading with a "Re-analyze" button to force a fresh Gemma call.

## Approach

Add a `StudentAnalysis` table to SQLite that stores the serialized analysis results. On load, retrieve cached analysis and render instantly. On register/analyze, cache the result. A "Re-analyze" button forces a fresh Gemma call.

## Changes

### 1. `src/models/database.py` — New `StudentAnalysis` model + hash utility

- New table `student_analyses`: `id`, `student_id` (FK, unique), `trend`, `trend_detail`, `develop_band`, `develop_band_json` (JSON), `introduce_band`, `introduce_band_json` (JSON), `latest_rit`, `scores_hash`, `grade`, `analyzed_at`
- One row per student (upsert pattern)
- `scores_hash` = SHA-256 hash of sorted `(rit, season, year, grade)` tuples — detects when scores change
- Add `analysis` relationship to `Student` model (`uselist=False`)
- Add `compute_scores_hash(scores, grade)` utility function
- `create_all()` auto-creates the new table on startup (no migration needed)

### 2. `src/tools/curriculum.py` — Cache read/write functions

- `get_cached_analysis(student_id, db) -> CurriculumResult | None` — queries `StudentAnalysis`, reconstructs `CurriculumResult` from stored JSON
- `save_analysis_cache(student_id, curriculum_result, scores_hash, grade, db)` — upserts `StudentAnalysis` row

### 3. `frontend/app.py` — Main UI changes

**Extract `_build_analysis_html(name, grade, curriculum)`** — move the ~100 lines of HTML template code from `register_student()` into a shared helper. Both `register_student()` and `load_student()` will use it.

**Modify `register_student(name, grade, scores_data, force_refresh=False)`:**
- After upserting Student + Scores, compute `scores_hash`
- If `force_refresh=False` and a fresh cache exists (matching hash), use cached `CurriculumResult` — no Gemma call
- If `force_refresh=True` or no cache or stale cache: run `map_rit_to_curriculum()` (Gemma call), then `save_analysis_cache()`
- Call `_build_analysis_html()` + `create_score_chart()`

**Modify `load_student(selection)`:**
- After querying Student + Scores, query `StudentAnalysis` for cached result
- If cache exists and hash matches: render cached analysis + chart instantly (no Gemma)
- If cache exists but stale: show cached + warning banner "Scores changed, click Re-analyze"
- If no cache: show message "Click Analyze to run analysis"

**Add "Re-analyze" button:**
- New button next to "Analyze" in the UI
- Calls `register_student(force_refresh=True)` — always re-runs Gemma and updates cache

**Update `start_practice()`:**
- Check cache before calling `map_rit_to_curriculum()` (avoids duplicate 30s Gemma call)

**Update `get_progress_report()`:**
- Use cached trend instead of calling `detect_trend()` directly

## Data Flow

```
Register/Analyze (no cache):  scores → Gemma 4 (~30s) → cache to DB → render
Register/Analyze (cached):    scores → hash match? → load from DB (<1s) → render
Load student:                 query DB → cached analysis → render (<1s)
Re-analyze:                   scores → force Gemma 4 (~30s) → update cache → render
```

## Edge Cases

- **First run after deploy:** No `student_analyses` table → `create_all()` creates it. Existing students have no cache until first analysis.
- **Grade change without score change:** Include `grade` in `scores_hash` so cache detects this.
- **Chart:** Always regenerate from cached data (matplotlib is sub-second). Don't cache the image.
- **Score deletion/replacement:** `register_student()` already replaces all scores. Hash will change → stale cache detected.

## Files to Modify

| File | Change |
|------|--------|
| `src/models/database.py` | Add `StudentAnalysis` model, `compute_scores_hash()`, relationship on `Student` |
| `src/tools/curriculum.py` | Add `get_cached_analysis()`, `save_analysis_cache()` |
| `frontend/app.py` | Extract `_build_analysis_html()`, modify `register_student()` + `load_student()`, add Re-analyze button, update `start_practice()` + `get_progress_report()` |

## Verification

1. Register a new student with scores → analysis runs (Gemma call), cached to DB
2. Load that student → analysis + chart appear instantly (no Gemma call, check logs)
3. Click Re-analyze → Gemma runs again, results update
4. Change a score and click Analyze → detects stale cache, re-runs Gemma
5. Start practice → no duplicate Gemma call (uses cache)
6. `just reset-db` → fresh start, table recreated automatically
