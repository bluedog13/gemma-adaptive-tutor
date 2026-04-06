# Plan: Enrich Generate Report with Practice Test Scores

**Status:** Done

## Context

The "Generate Report" feature produces a progress report via Gemma 4, but currently doesn't include actual practice test scores. The `StudentProgress.sessions` is hardcoded to `[]`, so Gemma only sees aggregated mastered/needs-work concepts with no session details. This results in a generic, low-value report. Additionally, Gemma outputs placeholder text like "Dear [Parent/Teacher Name]".

**Goal:** Pass per-session practice test data to the report prompt so Gemma can write a data-driven, personalized report showing improvement trajectory and per-session performance.

## Files to Modify

### 1. `frontend/app.py` — `get_progress_report()` (~line 2106-2117)

**Change:** Sort sessions chronologically, then build `SessionSummary` objects from the DB `sessions` query (already fetched at line 2073) instead of hardcoding `sessions=[]`.

**Important:** SQLite does not guarantee row order from `.all()`, so sessions must be explicitly sorted by `completed_at` (or `started_at` as fallback) before numbering them. This ensures the "Session 1, Session 2, ..." labels in the prompt match chronological order, and Gemma can accurately describe improvement trends.

```python
# Sort sessions chronologically before building summaries
sessions = sorted(sessions, key=lambda s: s.completed_at or s.started_at)

# Before
sessions=[],

# After — build from the sorted DB sessions
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
```

Add `SessionSummary` to the import on line 2106.

### 2. `src/api/main.py` — `get_progress()` (~line 378-386)

**Change:** Apply the same chronological sort to the API report path. The `.all()` query at line 378 also has no `order_by`, so the shared `generate_report()` flow would receive out-of-order sessions.

```python
# Sort sessions chronologically before building summaries
sessions = sorted(sessions, key=lambda s: s.completed_at or s.started_at)
```

Add this line after the `.all()` query and before the concept aggregation loop.

### 3. `src/tools/exercise_generator.py` — `generate_report()` (~line 405-424)

**Change:** Format per-session details into a concise text summary and pass to prompt builder.

- Build a list of one-line session summaries: `"Session 1 (Band 191-200): 4/5 (80%) — concepts: unit_cube 2/2, tenths 2/3"`
- Pass as a new `session_details: list[str]` parameter to `build_report_prompt()`

### 4. `src/prompts.py` — `build_report_prompt()` (~line 315-348)

**Changes:**
- Add `session_details: list[str] | None = None` parameter
- Include session details section in prompt when available
- Add instruction: "Do NOT use placeholder text like [Parent/Teacher Name]. Start directly with the report content."
- Update report instructions to reference practice session performance

## Prompt Design

Keep session data concise to stay within Gemma 4B context limits. Format:

```
Practice session results:
- Session 1 (Band 191-200): 4/5 (80%) — unit_cube 2/2, tenths 2/3
- Session 2 (Band 191-200): 5/5 (100%) — hundredths 3/3, rates 2/2
```

Update the report writing instructions to:
1. Reference specific practice session scores and improvement trends
2. Highlight per-concept growth across sessions
3. Keep warm, actionable tone

## Verification

1. Run `just app`, load an existing student with completed practice sessions
2. Click "Generate Report" in the Report tab
3. Confirm the report references actual practice scores, session-by-session trends, and concept-level detail
4. Confirm no "Dear [Parent/Teacher Name]" placeholder text
5. Run `just test` to ensure no regressions
