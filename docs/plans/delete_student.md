# Plan: Delete Student from UI

## Context

There is currently no way to remove a student from the app. Once registered, a student stays in the dropdown forever. We need a delete button in the UI with a confirmation step, backed by proper cascading deletion of all related records.

## Status: Done

## Files to Modify

1. **`src/models/database.py`** — Add cascade deletes to Student relationships
2. **`frontend/app.py`** — Add delete button + confirmation + handler
3. **`src/api/main.py`** — Add `DELETE /students/{student_id}` endpoint
4. **`tests/`** — Add test for deletion logic

## Database Changes (`src/models/database.py`)

Add `cascade="all, delete-orphan"` to all three Student relationships so SQLAlchemy auto-deletes child records:

- `Student.scores` relationship (currently no cascade)
- `Student.sessions` relationship (currently no cascade)
- `Student.analysis` relationship (currently no cascade)

This handles the full chain: deleting a Student cascades to Scores, PracticeSessions, and StudentAnalysis. For ExerciseResultRecords (children of PracticeSession), add cascade to `PracticeSession.results` as well.

## Frontend Changes (`frontend/app.py`)

- Add a **"Delete Student"** button next to the existing student dropdown and "Refresh List" button at the top of the UI (~line 2696)
- The button should be styled with `variant="stop"` (red) to signal destructive action
- On click: show a **confirmation dialog** — Gradio doesn't have native confirm dialogs, so use a two-step pattern:
  1. First click reveals a confirmation row: "Are you sure? This will permanently delete [Name] and all their scores, practice sessions, and reports." with **Confirm Delete** and **Cancel** buttons
  2. Confirm click performs the actual deletion
- After deletion: refresh the student dropdown, clear all displayed data, show a success message via `gr.Info()`
- If no student is selected, show `gr.Warning("Please select a student first")`

### Handler function

Add `delete_student(student_key, subject)` that:
1. Looks up student by the dropdown key
2. Deletes the Student record (cascade handles children)
3. Returns updated dropdown choices + cleared state

## API Changes (`src/api/main.py`)

Add endpoint:
```
DELETE /students/{student_id}
```
- Query the student, return 404 if not found
- Delete the student (cascade handles children)
- Commit transaction
- Return `{"message": "Student deleted"}`

## Verification

1. `just test` — all existing tests pass
2. `just app` — launch UI, register a student with scores, run a practice session, then delete the student and confirm:
   - Student disappears from dropdown
   - UI state clears
   - Refreshing the page confirms student is gone
   - No orphaned records in SQLite (`just reset-db` not needed)
3. `just api` — test `DELETE /students/{id}` via curl
