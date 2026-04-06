# Plan: Kid-Friendly UI Redesign (Playful & Colourful)

**Status:** Done  
**File:** `frontend/app.py` (single file, all CSS changes)  
**Prototype:** `prototype_ui.html` (side-by-side before/after, approved by Gautam)

---

## Context

The current UI is clean and professional but feels clinical for a grades 2–5 audience. Fonts are too small and plain, the colour scheme is muted, and buttons/cards lack the warmth that keeps young learners engaged. The goal is to make the app feel inviting and fun without sacrificing readability or usability.

This redesign targets the **Practice tab** primarily (the student-facing screen), with supporting changes to the **tab bar** and **global typography**. The Scores and Report tabs (parent/teacher-facing) are out of scope.

**Reference:** Agreed design direction is *Playful & Colourful*. See `prototype_ui.html` for the approved visual target.

---

## Design Decisions (agreed in prototype review)

| Element | Decision |
|---|---|
| Stars widget | Removed — not needed |
| Streak badge | Removed — no daily tracking in app |
| Post-answer feedback card | Not added — app goes straight to next question |
| Fonts | Fredoka One (headings, tabs, buttons) + Nunito 700+ (body) |
| Colour palette | Indigo → sky gradient header; yellow passage card; rounded indigo tiles for choices |
| Progress indicator | Visual bar with "X of Y" label, replaces plain right-aligned counter |

---

## Scope

- **In scope:** CSS changes inside `theme.custom_css` in `frontend/app.py`
- **In scope:** HTML strings returned by `_format_exercise()` and `_show_results()` (class names / structure)
- **Not in scope:** Scores tab, Report tab, matplotlib charts, any Python logic, database, API

---

## Current CSS to replace

All styles scoped under `#map-practice-wrapper` (lines ~2007–2059 of `frontend/app.py`) replicate the clinical NWEA MAP test aesthetic: Arial font, flat dark-teal buttons, thin border rows. These will be replaced with the kid-friendly equivalents below.

The global `theme` definition (~line 1966) already imports Nunito via Google Fonts and sets it as the primary font — no change needed there. We will add a Fredoka One import alongside it.

---

## Implementation Steps

### 1. Add Fredoka One to the Google Fonts import

In `theme.custom_css`, the existing `@import` line is:
```css
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');
```

Replace with:
```css
@import url('https://fonts.googleapis.com/css2?family=Fredoka+One&family=Nunito:wght@400;600;700;800;900&display=swap');
```

---

### 2. Replace `#map-practice-wrapper` CSS block

Remove all existing styles under the comment `/* === MAP Practice Tab — scoped under #map-practice-wrapper === */` and replace with:

```css
/* === Practice Tab — Kid-Friendly Redesign === */

/* Reset container */
#map-practice-wrapper {
  font-family: 'Nunito', sans-serif !important;
  background: #f0f9ff;
  padding: 0 0 1.5rem 0;
}
#map-practice-wrapper * { font-family: 'Nunito', sans-serif !important; }

/* Top bar: gradient header with subject + student name */
.map-topbar {
  background: linear-gradient(135deg, #4f46e5 0%, #38bdf8 100%);
  padding: 0.85rem 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: white;
  border-radius: 16px 16px 0 0;
}
.map-topbar-subject {
  font-family: 'Fredoka One', cursive !important;
  font-size: 1.15rem;
  letter-spacing: 0.03em;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Progress bar */
.map-progress-area {
  background: #e0f7ff;
  padding: 0.6rem 1.25rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0;
}
.map-progress-bar-wrap {
  flex: 1;
  background: rgba(255,255,255,0.8);
  border-radius: 50px;
  height: 12px;
  overflow: hidden;
  border: 2px solid #38bdf8;
}
.map-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4f46e5, #38bdf8);
  border-radius: 50px;
  transition: width 0.4s ease;
}
.map-progress-label {
  font-size: 0.85rem;
  font-weight: 800;
  color: #4f46e5;
  white-space: nowrap;
}

/* Question body area */
.map-question-area {
  background: #ffffff;
  padding: 1.25rem 1.4rem 1rem;
}

/* Topic chip (replaces teal banner) */
.map-topic-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: linear-gradient(135deg, #e0e7ff, #dbeafe);
  color: #3730a3;
  font-size: 0.8rem;
  font-weight: 800;
  padding: 0.35rem 0.9rem;
  border-radius: 50px;
  margin-bottom: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* Passage card: warm yellow */
.map-passage-card {
  background: linear-gradient(135deg, #fffbeb, #fef9c3);
  border: 2px solid #fde68a;
  border-radius: 14px;
  padding: 0.85rem 1rem;
  margin-bottom: 0.9rem;
}
.map-passage-label {
  font-size: 0.72rem;
  font-weight: 900;
  letter-spacing: 0.08em;
  color: #92400e;
  text-transform: uppercase;
  margin-bottom: 0.4rem;
}
.map-passage-text {
  font-size: 0.95rem;
  line-height: 1.7;
  color: #44403c;
}

/* Question text */
.map-question-text {
  font-size: 1.05rem;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.6;
  margin-bottom: 1rem;
}

/* Answer choices: rounded tiles with letter bubbles */
#map-practice-wrapper .map-radio-choices label {
  display: flex !important;
  align-items: center !important;
  gap: 0.75rem !important;
  padding: 0.75rem 1rem !important;
  border-radius: 14px !important;
  border: 2.5px solid #e2e8f0 !important;
  background: #f1f5f9 !important;
  margin-bottom: 0.55rem !important;
  font-size: 0.95rem !important;
  font-weight: 600 !important;
  color: #1e293b !important;
  cursor: pointer !important;
  transition: all 0.15s ease !important;
  line-height: 1.5 !important;
}
#map-practice-wrapper .map-radio-choices label:hover {
  border-color: #818cf8 !important;
  background: #eef2ff !important;
  transform: translateX(3px) !important;
}
#map-practice-wrapper .map-radio-choices input[type="radio"] {
  width: 20px !important;
  height: 20px !important;
  accent-color: #4f46e5 !important;
  flex-shrink: 0 !important;
}

/* Text answer input */
#map-practice-wrapper .map-text-input textarea {
  font-size: 1rem !important;
  padding: 0.6rem 0.8rem !important;
  border: 2.5px solid #cbd5e1 !important;
  border-radius: 12px !important;
  line-height: 1.5 !important;
  max-width: 240px !important;
}
#map-practice-wrapper .map-text-input textarea:focus {
  border-color: #4f46e5 !important;
  outline: none !important;
  box-shadow: 0 0 0 3px rgba(79,70,229,0.15) !important;
}

/* Submit button */
#map-practice-wrapper .map-submit-btn {
  background: linear-gradient(135deg, #4f46e5, #818cf8) !important;
  color: #fff !important;
  font-family: 'Fredoka One', cursive !important;
  font-size: 1.05rem !important;
  padding: 0.8rem 1.5rem !important;
  border-radius: 14px !important;
  border: none !important;
  box-shadow: 0 4px 12px rgba(79,70,229,0.35) !important;
  transition: all 0.15s ease !important;
  letter-spacing: 0.03em !important;
}
#map-practice-wrapper .map-submit-btn:hover {
  transform: translateY(-2px) !important;
  box-shadow: 0 6px 16px rgba(79,70,229,0.45) !important;
}

/* Next button */
#map-practice-wrapper .map-next-btn {
  background: #ffffff !important;
  color: #4f46e5 !important;
  font-family: 'Fredoka One', cursive !important;
  font-size: 1.05rem !important;
  border: 2.5px solid #818cf8 !important;
  padding: 0.8rem 1.2rem !important;
  border-radius: 14px !important;
  transition: all 0.15s ease !important;
  letter-spacing: 0.03em !important;
}
#map-practice-wrapper .map-next-btn:hover {
  background: #eef2ff !important;
  transform: translateY(-2px) !important;
}

/* Start Practice button */
#map-practice-wrapper .map-start-btn {
  background: linear-gradient(135deg, #34d399, #059669) !important;
  color: #fff !important;
  font-family: 'Fredoka One', cursive !important;
  font-size: 1rem !important;
  padding: 0.75rem 1.5rem !important;
  border-radius: 14px !important;
  border: none !important;
  box-shadow: 0 4px 12px rgba(52,211,153,0.4) !important;
  transition: all 0.15s ease !important;
  letter-spacing: 0.03em !important;
  width: 100% !important;
}
#map-practice-wrapper .map-start-btn:hover {
  transform: translateY(-2px) !important;
  box-shadow: 0 6px 16px rgba(52,211,153,0.5) !important;
}

/* Session complete */
.map-session-complete {
  font-family: 'Fredoka One', cursive;
  font-size: 1.1rem;
  color: #4f46e5;
  text-align: center;
  margin-top: 1rem;
}

/* Results card */
.map-results-card { background: #fff; padding: 1.5rem 1.25rem; line-height: 1.6; border-radius: 16px; }
.map-results-card h2 {
  font-family: 'Fredoka One', cursive;
  color: #4f46e5;
  font-size: 1.4rem;
  border-bottom: 3px solid #e0e7ff;
  padding-bottom: 0.5rem;
  margin-bottom: 1rem;
}
.map-score-big { font-family: 'Fredoka One', cursive; font-size: 3rem; color: #4f46e5; text-align: center; margin: 1rem 0 0.25rem; }
.map-score-pct { text-align: center; color: #64748b; font-size: 1rem; font-weight: 700; margin-bottom: 1rem; }
.map-results-card h3 { font-family: 'Fredoka One', cursive; color: #1e293b; font-size: 1.1rem; margin-top: 1.25rem; }
.map-results-card ul { list-style: none; padding: 0; margin: 0; }
.map-results-card li {
  padding: 0.6rem 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 0.95rem;
  color: #374151;
  font-weight: 600;
}
.map-results-followup {
  background: #eef2ff;
  padding: 1rem 1.25rem;
  margin-top: 1.25rem;
  font-size: 0.95rem;
  color: #1e293b;
  line-height: 1.6;
  border-left: 4px solid #4f46e5;
  border-radius: 0 12px 12px 0;
}
```

---

### 3. Update HTML emitted by `_format_exercise()`

The function currently emits a `<div class="map-banner">` header. Replace with the new structure:

```python
# OLD
header_html = f'<div class="map-banner">{concept}</div>'

# NEW
subject_emoji = {"math": "🔢", "language arts: reading": "📚", "science": "🔬"}.get(subject.lower(), "📖")
header_html = f"""
<div class="map-topbar">
  <span class="map-topbar-subject">{subject_emoji} {subject_display}</span>
</div>
<div class="map-progress-area">
  <div class="map-progress-bar-wrap">
    <div class="map-progress-fill" style="width:{progress_pct}%"></div>
  </div>
  <span class="map-progress-label">{current_q} of {total_q}</span>
</div>
<div class="map-question-area">
  <div class="map-topic-chip">{html.escape(concept)}</div>
"""
```

For questions with a passage, replace the `READ THE PASSAGE` label style with:
```python
passage_html = f"""
<div class="map-passage-card">
  <div class="map-passage-label">📖 Read This First</div>
  <p class="map-passage-text">{html.escape(passage_text)}</p>
</div>
"""
```

Question text wrapper:
```python
question_html = f'<p class="map-question-text">{html.escape(question_text)}</p>'
```

> **Note:** `progress_pct`, `current_q`, `total_q`, and `student_name` will need to be threaded through from practice state. `pstate` already contains `exercise_idx` and `exercises` list, so `current_q = pstate["exercise_idx"] + 1` and `total_q = len(pstate["exercises"])`.

---

### 4. Update `_build_practice_tab()` button `elem_classes`

```python
# Start Practice button
gr.Button("▶ Start Practice!", elem_classes=["map-start-btn"])

# Submit Answer button
gr.Button("✅ Submit Answer", elem_classes=["map-submit-btn"])

# Next Question button
gr.Button("Next →", elem_classes=["map-next-btn"])
```

---

### 5. Update Practice tab `gr.Tab` label

```python
# OLD
with gr.Tab("Practice"):

# NEW
with gr.Tab("🎯 Practice"):
```

Similarly update Scores and Report tabs for consistency:
```python
with gr.Tab("📊 Scores"):
with gr.Tab("📋 Report"):
```

---

## Files Changed

| File | Change |
|---|---|
| `frontend/app.py` | CSS block replacement (~lines 2007–2059), `_format_exercise()` HTML structure, button `elem_classes`, tab labels |

No other files touched.

---

---

## Follow-on: Tab & Section Header Font Sizes

**Status:** Done  
**Prototype:** `prototype_fonts.html` (side-by-side before/after, approved by Gautam)

### What changes

| Element | Before | After |
|---|---|---|
| Subject tabs (Math / Reading / Science) | 0.875rem · Nunito 700 | 1.05rem · Fredoka One |
| Inner tabs (Scores / Practice / Report) | 0.875rem · Nunito 700 | 0.975rem · Fredoka One |
| Section headers (`###` in Scores tab) | 1rem · Nunito 800 | 1.2rem · Nunito 900 |

### Implementation

Three CSS rules appended to `theme.custom_css` in `frontend/app.py`. No Python changes needed.

```css
/* Tab labels — all levels (Gradio 6 uses .tab-button) */
.tab-button {
    font-family: 'Fredoka One', cursive !important;
    font-size: 1.05rem !important;
    letter-spacing: 0.02em !important;
}

/* Section headers in Scores tab */
.prose h3 {
    font-size: 1.2rem !important;
    font-weight: 900 !important;
}
```

### Verification

1. `just app` — launch Gradio
2. Check subject tabs: Math / Language Arts: Reading / Science are larger and in Fredoka One
3. Check inner tabs: Scores / Practice / Report are slightly larger and in Fredoka One
4. Check Scores tab: "Load Existing Student", "Student Details", "Add Score" headers are visibly larger
5. Confirm Report and analysis card headers are unaffected

---

## Verification

1. `just app` — launch Gradio
2. Go to Practice tab:
   - Tab bar shows emoji labels in Fredoka One font
   - Top bar shows gradient header with subject emoji and student name
   - Progress bar fills correctly as questions advance
   - Passage displays in yellow card with "📖 Read This First" label
   - Answer choices are rounded tiles that highlight on hover/select
   - Submit button is indigo gradient; Next button is white with indigo border
   - Start Practice button is green gradient
3. Complete a session — verify results card uses Fredoka One headings and large indigo score
4. Switch to Scores / Report tabs — verify they are **unchanged** (Nunito/indigo)
5. `just test` — all existing tests pass
