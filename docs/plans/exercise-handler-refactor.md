# Plan: Refactor Exercise Display & Grading into Per-Type Handlers

**Status:** Done  
**Files:** `frontend/app.py`

---

## Context

`_format_exercise()` and `submit_answer()` in `frontend/app.py` are large functions with chained `if q_type == ...` blocks. Each question type (multiple_choice, multi_select, two_part, sequence_order, table_matching) has its own display logic and grading logic interleaved. This makes it hard to debug (e.g. the Q5 looping bug where a sequence_order question fell through incorrectly) and risky to modify one type without breaking another.

## Goal

Extract each question type into a self-contained formatter + grader pair. The main functions become simple dispatchers.

## Design

### Formatter protocol

Each formatter takes `(idx, ex, total, pstate)` and returns the standard 6-tuple:
```python
(question_html, textbox_update, radio_update, checkbox_update, feedback_clear, submit_btn_update)
```

### Grader protocol

Each grader takes `(text_answer, radio_answer, checkbox_answer, pstate, ex, idx, exercises)` and returns the standard 7-tuple:
```python
(question_update, textbox_update, radio_update, checkbox_update, feedback, submit_btn_update, pstate)
```

### Dispatch tables

```python
_FORMATTERS: dict[str, Callable] = {
    "multiple_choice": _format_mc,
    "multi_select": _format_multi_select,
    "two_part": _format_two_part,
    "sequence_order": _format_sequence,
    "table_matching": _format_table,
    "fill_in_the_blank": _format_fill_blank,
}

_GRADERS: dict[str, Callable] = {
    "multiple_choice": _grade_mc_submit,
    "multi_select": _grade_multi_select_submit,
    "two_part": _grade_two_part_submit,
    "sequence_order": _grade_sequence_submit,
    "table_matching": _grade_table_submit,
    "fill_in_the_blank": _grade_fill_blank_submit,
}
```

### Main functions become dispatchers

```python
def _format_exercise(idx, pstate):
    ex = pstate["exercises"][idx]
    q_type = ex.get("question_type", "multiple_choice")
    formatter = _FORMATTERS.get(q_type, _format_mc)
    return formatter(idx, ex, len(pstate["exercises"]), pstate)

def submit_answer(text_answer, radio_answer, checkbox_answer, pstate):
    ex = pstate["exercises"][pstate["exercise_idx"]]
    q_type = ex.get("question_type", "multiple_choice")
    grader = _GRADERS.get(q_type, _grade_mc_submit)
    return grader(text_answer, radio_answer, checkbox_answer, pstate, ex, ...)
```

## Steps

1. Extract `_format_mc()` and `_grade_mc_submit()` from the existing MC blocks
2. Extract `_format_multi_select()` and `_grade_multi_select_submit()`
3. Extract `_format_two_part()` and `_grade_two_part_submit()` — this is the most complex due to Part A/B state
4. Extract sequence_order and table_matching handlers (lower priority — currently demoted to MC)
5. Extract fill_in_the_blank handler
6. Replace `_format_exercise()` body with dispatch lookup
7. Replace `submit_answer()` body with dispatch lookup
8. Move shared helpers (`_build_question_html`, `_format_choices`, `_grade_mc_answer`, `_record_result`, `_show_results`) above the handler functions

## Shared helpers (no change needed)

- `_build_question_html()` — builds topbar + progress bar + topic chip + question text
- `_format_choices()` — adds A/B/C/D or 1/2/3/4 prefixes
- `_grade_mc_answer()` — normalizes and compares MC answers
- `_record_result()` — appends to pstate results and saves to DB
- `_show_results()` — renders session-complete summary

## Edge cases

- **two_part state:** Part A/B transition uses `pstate["current_part"]`. The grader must handle both parts and only call `_record_result` after Part B.
- **Fallback:** Unknown question types should fall back to `_format_mc` / `_grade_mc_submit` rather than crashing.
- **Return tuple size:** All formatters must return exactly 6 items, all graders exactly 7 items. The `_start`, `_submit`, `_next` wrappers add `btn_row` as the 8th.

## Testing

- Run `just test` after each extraction step
- Manual test: generate exercises, verify each question type renders and grades correctly
- Verify two_part Part A → Part B transition still works
