# Plan: Multi-Subject Support (Math, Science, Language Arts: Reading)

## Context

MAP Accelerator currently supports Math only. The user wants to extend it to 3 subjects — Math, Science, and Language Arts: Reading — so all MAP-tested subjects are covered. A single MAP report upload should populate all subjects found, and each subject gets its own workspace with scores, practice, and reports.

**Decisions made:**
- UI: Top-level subject tabs (Math / Science / Reading), each containing Scores/Practice/Report sub-tabs
- Data: Real NWEA 2025 norms and RIT-to-concept mappings for all 3 subjects
- DB: Fresh database required (`just reset-db` before first run). No migration for old schemas — pre-production hackathon project
- Score upload: Per-subject tab upload. Multi-subject PDFs extract all subjects but only populate the current tab; banner directs users to re-upload in other tabs
- Subject validation: `Subject` enum enforced at API boundary (Pydantic rejects invalid values with 422)

---

## Risk Mitigations

### 1. Constants restructuring (silent breakage risk)
Adding `subject` as the outermost key changes every call site from `NWEA_PERCENTILES[grade]` to `NWEA_PERCENTILES["math"][grade]`. A missed call site would silently get a nested dict instead of a value.

**Mitigation:** Before changing the data structures, grep all usages of each constant (`NWEA_NORMS`, `NWEA_PERCENTILES`, `NWEA_MEAN_RIT`, `EXPECTED_GROWTH`, `NWEA_CONDITIONAL_GROWTH`, `estimate_percentile`, `get_percentile_cutoffs`) and update every call site in a single pass. Run `just test` immediately after to catch any misses.

### 2. Frontend tripling (maintenance cost)
Three subject tabs means three copies of the Scores/Practice/Report UI. Bug fixes applied to one subject's UI could be missed in the others.

**Mitigation:** Each builder function (`build_scores_tab`, `build_practice_tab`, `build_report_tab`) creates the UI components *and* wires all event handlers internally. The `subject` string is captured in closures so the same function logic works for all 3 subjects. Called once per subject in a loop — bug fixes go in the builder function, not in 3 places.

### 3. Score extractor (missing subjects in PDF)
Not all MAP reports include all 3 subjects. The plan must handle missing subject sections gracefully.

**Mitigation:** `extract_all_subjects_from_file()` returns only subjects that were actually found — e.g. `{"math": {scores...}, "reading": {scores...}}` if science is absent. The frontend shows a banner for what was found ("Found 7 Math scores, 6 Reading scores") and silently skips missing subjects. No errors for absent sections.

### 4. `db/cleanup.sh` — SQL injection and subject awareness
Codex review flagged SQL injection via unescaped shell interpolation and non-transactional deletes. The script also lacks subject awareness.

**Mitigation:** Delete `db/cleanup.sh`. The `just reset-db` recipe already handles full database resets, and per-student cleanup can be done through the app or a Python script with proper parameterized queries if needed later.

---

## Phase 1: Schemas & Database

### `src/models/schemas.py`
- Add `Subject` enum: `math`, `reading`, `science`
- Add `subject: Subject` field to: `ScoreInput` (enum-validated, default `Subject.MATH`), `CurriculumResult`, `SessionSummary`, `StudentProgress`
- Add `SUBJECT_DISPLAY` mapping: `{"math": "Math", "reading": "Language Arts: Reading", "science": "Science"}`

### `src/models/database.py`
- Add `subject = Column(String, nullable=False, default="math")` to: `Score`, `PracticeSession`, `StudentAnalysis`
- Add `UniqueConstraint("student_id", "subject", "season", "year")` to `Score` for idempotent upserts
- Change `StudentAnalysis` unique constraint from `student_id` alone to composite `(student_id, subject)`
- Update `Student.analysis` relationship from `uselist=False` to `uselist=True` (one analysis per subject)
- `init_db()` uses plain `create_all()` — fresh DB required (run `just reset-db` if upgrading)

---

## Phase 2: Constants & Curriculum Data

### `src/constants.py`
- Restructure all norms dicts to be subject-keyed: `NWEA_NORMS[subject][grade][season]`
- Same for `NWEA_PERCENTILES`, `NWEA_MEAN_RIT`, `EXPECTED_GROWTH`, `NWEA_CONDITIONAL_GROWTH`
- All three subjects use official 2025 NWEA Technical Manual data:
  - Math: Tables A.1, B.1, B.3, B.5
  - Reading: Tables A.3, B.7, B.9, B.11
  - Science: Tables A.7, B.19, B.21, B.23 (grades 2-5 only, no K/1)
- Update `estimate_percentile()` and `get_percentile_cutoffs()` to accept `subject` parameter
- Grade fallback uses `min(subj_pcts.keys())` — grade 0 for math/reading, grade 2 for science
- **Validated:** 18 data points across all 3 subjects checked against a real NWEA student report — 17/18 within range, 16/18 within ±2 of report middle. See `docs/plans/nwea_2025_norms_analysis.md` §6.

### `src/data/rit_to_concept_reading_2plus.json` (new)
- Same JSON structure as math file. Reading continuum topics: Literary Text (key ideas, craft/structure), Informational Text (key ideas, craft/structure), Foundational Skills, Language/Writing
- Source: NWEA RIT-to-concept documents for Reading

### `src/data/rit_to_concept_science_2plus.json` (new)
- Same JSON structure. Science topics: Life Science, Earth/Space Science, Physical Science, Scientific Inquiry
- Source: NWEA RIT-to-concept documents for Science

---

## Phase 3: Core Logic

### `src/tools/curriculum.py`
- Replace single `_curriculum_cache` with `_curriculum_cache: dict[str, dict]` keyed by subject
- `_load_curriculum(subject)` loads `rit_to_concept_{subject}_2plus.json`
- Add `subject` parameter to: `_score_to_band_key()`, `_next_band_key()`, `_band_key_to_info()`, `map_rit_to_curriculum()`, `detect_trend()`
- Cache functions filter by `(student_id, subject)` instead of just `student_id`

### `src/prompts.py`
- `_build_norms_context(grade, latest_rit, season, subject)` — use `NWEA_NORMS[subject]`
- `build_trend_prompt()` — change "MAP Math" to "MAP {subject_display}"
- `build_exercise_prompt()` — adapt tutor role and exercise types per subject:
  - Math: word problems, multiple choice, fill-in-the-blank (current)
  - Reading: passages with comprehension questions, vocabulary in context
  - Science: concept questions, experiment-based scenarios, diagram interpretation
- `build_report_prompt()` — include subject name in report context

### `src/tools/exercise_generator.py`
- Add `subject` parameter to `generate_exercises()`, pass through to prompt builder
- `generate_report()` — extract subject from progress object

### `src/tools/score_extractor.py`
- Add `extract_all_subjects_from_file(file_path) -> dict[str, dict]` — calls extraction once per subject, returns only subjects that had scores (e.g. `{"math": {scores...}, "reading": {scores...}}` if science is absent)
- The existing `_parse_scores_regex` and `_build_text_prompt` already accept a subject parameter — call them once per subject
- Replace `_VISION_PROMPT` constant with `_build_vision_prompt(subject)` function — returns per-subject prompts in the format `_parse_gemma_response()` expects
- Image uploads iterate over all subjects via `_extract_from_single_image(file_path, display_name)`
- PDF vision fallback accumulates results per subject across pages and merges via `_merge_results()` (handles multi-page scanned reports)

---

## Phase 4: Frontend

### `frontend/app.py`
- **Top-level structure:** 3 subject tabs (Math, Science, Reading), each containing 3 sub-tabs (Scores, Practice, Report)
- **Refactor approach:** Extract current tab content into builder functions:
  - `build_scores_tab(subject)` — creates UI *and* wires all event handlers internally. Subject is captured in closures.
  - `build_practice_tab(subject)` — same pattern, self-contained with event wiring.
  - `build_report_tab(subject)` — same pattern.
  - Called once per subject in a loop: `for subj in SUBJECTS: build_scores_tab(subj)`. Bug fixes go in the builder, not 3 places.
- Each subject tab gets its own set of `gr.State` variables for: exercises, exercise index, session ID, band, RIT, results
- **Score extraction UX:** When a PDF is uploaded in any subject's Scores tab, extract all subjects via `extract_all_subjects_from_file()`. Populate the current tab's scores. Show a banner listing what was found ("Found 7 Math scores, 6 Reading scores") and directing the user to upload in other tabs for those subjects. Missing subjects are silently skipped — no errors.
- Thread `subject` through all backend calls: `map_rit_to_curriculum(subject=...)`, `generate_exercises(subject=...)`, etc.
- `create_score_chart()` — pass subject to `get_percentile_cutoffs()` for correct norms

### Per-client practice state (Gradio `gr.State`, not module globals):
Each practice tab creates its own `gr.State(_empty_practice_state())` holding exercises, index, session ID, band, RIT, and results. This state flows through `start_practice`, `submit_answer`, and `next_question` as an input/output parameter, preventing cross-client/cross-tab corruption.

### Per-subject student state:
Each subject tab gets its own `student_id_state = gr.State("")` so loading a student in one subject doesn't affect another subject's practice/report.

---

## Phase 5: API Layer

### `src/api/main.py`
- Add `subject: Subject = Subject.MATH` query parameter to all endpoints (enum-validated)
- Filter DB queries by subject: `.filter(Score.subject == subject)`, `.filter(PracticeSession.subject == subject)`
- Add `POST /students/{id}/scores` endpoint for adding scores to existing students
- Score upserts use SQLite `INSERT ... ON CONFLICT DO UPDATE` on `(student_id, subject, season, year)` for atomicity
- Per-score grade-at-test computed from current grade and season/year offset (mirrors frontend `_grade_for_score` logic)
- `POST /students` rejects duplicate names with 409, directing to the scores endpoint
- Thread `student.grade` through `map_rit_to_curriculum()` and `detect_trend()` calls

---

## Phase 6: Testing & Verification

1. Delete `db/cleanup.sh` (see Risk Mitigation #4)
2. `just reset-db` — drop and recreate tables with new subject columns
3. Grep all constant usages to confirm every call site has been updated (Risk Mitigation #1)
4. `just test` — fix any broken tests
5. `just check` — lint/format
6. `just app` — verify 3 subject tabs render correctly
7. Test Math flow end-to-end (should work identically to before)
8. Upload a multi-subject MAP report PDF — verify scores populate per subject
9. Upload a single-subject report — verify missing subjects handled gracefully (Risk Mitigation #3)
10. Test Reading and Science exercise generation with Gemma 4

---

## Files Modified (in order)

| File | Change |
|------|--------|
| `src/models/schemas.py` | Add `Subject` enum, add `subject` field to schemas |
| `src/models/database.py` | Add `subject` column to Score, PracticeSession, StudentAnalysis |
| `src/constants.py` | Restructure norms to subject-keyed dicts, add Reading + Science norms |
| `src/data/rit_to_concept_reading_2plus.json` | **New** — Reading curriculum bands |
| `src/data/rit_to_concept_science_2plus.json` | **New** — Science curriculum bands |
| `src/tools/curriculum.py` | Subject-parameterized loading, mapping, caching |
| `src/prompts.py` | Subject-aware prompt templates |
| `src/tools/exercise_generator.py` | Pass subject through to prompts |
| `src/tools/score_extractor.py` | Multi-subject extraction function |
| `frontend/app.py` | Subject tabs, refactored builder functions, per-subject state |
| `src/api/main.py` | Subject query parameter on endpoints |
| `db/cleanup.sh` | **Delete** — SQL injection risk, replaced by `just reset-db` |

## Status
Done
