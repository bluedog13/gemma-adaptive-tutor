# Plan: Restyle Practice Tab to Match NWEA MAP Test Interface

**Status:** Done  
**File:** `frontend/app.py` (single file, all changes)  
**Reference screenshots:** `assets/images/math/`, `assets/images/language arts reading/`, `assets/images/science/`

## Context

The Practice tab is where kids take generated questions. Currently it uses the same playful Nunito font and indigo/emerald theme as the parent-facing tabs. We want the Practice tab to feel like the actual NWEA MAP Growth test — flat, clinical, minimal, accessible.

## MAP Test Visual Targets (from actual screenshots across all 3 subjects)

| Property | MAP Style (actual) | Current |
|---|---|---|
| Font | Arial / system sans-serif, ~15-16px | Nunito (rounded/playful), ~16px |
| Instruction header | Dark teal banner (`#1b6d7c`), white text, full-width | No header |
| Question text | 15-16px, `#333333`, plain black on white | Markdown with colorful pills |
| Answer choices (MC) | Radio circles with blue outline (`#3b8bc5`), rows separated by thin `#e0e0e0` border | Typed letters in a textbox |
| Choice labels | Math/Science: `A.` `B.` `C.` `D.` — Reading: `1.` `2.` `3.` `4.` | N/A |
| Answer input (free) | Small bordered box, compact, left-aligned | Large 2-line textbox |
| Section dividers | Thin blue/cyan horizontal rule (`#3b8bc5`) | Markdown `---` |
| Background | Pure white `#ffffff`, no cards, no shadows | Card-style with shadows |
| Page background | Light gray-blue (`~#edf1f5`) behind the white question area | `#f9fafb` |
| Buttons | Simple, flat, no rounded corners | Gradient indigo |
| Overall feel | Extremely minimal, flat, clinical, high-contrast | Playful, card-heavy |

### Subject-specific patterns from screenshots

**Consistent across all subjects:**
- Same teal banner, same blue horizontal rules, same font
- Same radio button styling for single-answer MC
- Same white question area on light gray page background

**Reading-specific:**
- Passages shown in white area with numbered paragraphs (bold `1`, `2`, `3`...)
- Two-part questions (Part A / Part B) can appear side-by-side
- Passage text uses subtle light background (`~#f5f8fc`)
- Text highlight/selection supported (dashed blue outline)

**Science-specific:**
- Heavy use of images within questions (fossils, animals, diagrams)
- Some choices include images with captions below

**"Choose two/all" questions (Reading & Science):**
- Use **square checkboxes** (`[ ]`) instead of round radio buttons
- Note: our exercise generator currently only produces single-answer MC, so we won't implement checkboxes now. If we add multi-select later, use `gr.CheckboxGroup` with square checkbox styling.

## Scope

- **Changes**: Practice tab only (all subjects)
- **No changes**: Scores tab, Report tab, charts, analysis cards (parent/teacher-facing)
- **Note**: Partial code changes were made and need to be reverted first
- **Not in scope (future)**: Multi-select checkbox questions, drag-and-drop, image-based choices, two-column Part A/B layout

## Step 0: Revert partial changes

The previous implementation attempt added code based on incorrect assumptions. Before implementing this plan, revert `frontend/app.py` to the clean `develop` branch state:
```
git checkout develop -- frontend/app.py
```

## Implementation Steps

### 1. Add MAP-scoped CSS to `theme.custom_css` (~line 1360)

No extra font imports needed — MAP uses system Arial. All styles scoped under `#map-practice-wrapper`.

**Key CSS classes:**

```css
/* Container — system sans-serif, white bg, centered */
#map-practice-wrapper { font-family: Arial, Helvetica, sans-serif !important; max-width: 820px; margin: 0 auto; background: #fff; }
#map-practice-wrapper * { font-family: Arial, Helvetica, sans-serif !important; }

/* Teal instruction banner — matches MAP header bar */
.map-banner { background: #1b6d7c; color: #fff; font-size: 15px; font-weight: 400; padding: 0.6rem 1rem; margin-bottom: 0; line-height: 1.5; }

/* Question area — plain white, no card, no shadow */
.map-question-area { background: #fff; padding: 1.5rem 1.25rem 1rem; }
.map-question-text { font-size: 16px; color: #333; font-weight: 400; line-height: 1.6; margin: 0; }

/* Blue horizontal rule separator (between question and answer area) */
.map-blue-rule { border: none; border-top: 2px solid #3b8bc5; margin: 1rem 0; }

/* Progress counter — subtle, right-aligned */
.map-progress-counter { font-size: 13px; color: #666; text-align: right; margin-bottom: 0.5rem; }

/* Radio choices — plain rows with thin borders, blue radio circles */
#map-practice-wrapper .map-radio-choices label {
    display: flex !important; align-items: center !important;
    background: #fff !important; border: none !important;
    border-bottom: 1px solid #e0e0e0 !important; border-radius: 0 !important;
    padding: 0.7rem 1rem !important; margin-bottom: 0 !important;
    font-size: 15px !important; color: #333 !important;
    cursor: pointer !important; line-height: 1.5 !important; gap: 0.5rem !important;
}
#map-practice-wrapper .map-radio-choices label:first-child { border-top: 1px solid #e0e0e0 !important; }
#map-practice-wrapper .map-radio-choices label:hover { background: #f5f8fc !important; }
#map-practice-wrapper .map-radio-choices input[type="radio"] {
    width: 18px !important; height: 18px !important;
    border: 2px solid #3b8bc5 !important; accent-color: #3b8bc5 !important;
}

/* Text input — small bordered box (MAP "Enter the answer in the box" style) */
#map-practice-wrapper .map-text-input textarea {
    font-size: 15px !important; padding: 0.5rem 0.6rem !important;
    border: 1px solid #333 !important; border-radius: 2px !important;
    line-height: 1.5 !important; max-width: 200px !important;
}
#map-practice-wrapper .map-text-input textarea:focus {
    border-color: #3b8bc5 !important; outline: 2px solid #3b8bc5 !important;
}

/* Buttons — flat teal, minimal border-radius */
#map-practice-wrapper .map-submit-btn {
    background: #1b6d7c !important; color: #fff !important;
    font-size: 15px !important; font-weight: 600 !important;
    padding: 0.6rem 2rem !important; border-radius: 3px !important; border: none !important;
}
#map-practice-wrapper .map-submit-btn:hover { background: #155d6a !important; }
#map-practice-wrapper .map-next-btn {
    background: #fff !important; color: #1b6d7c !important;
    border: 1px solid #1b6d7c !important; font-size: 15px !important;
    font-weight: 600 !important; padding: 0.6rem 2rem !important; border-radius: 3px !important;
}
#map-practice-wrapper .map-next-btn:hover { background: #f0f7f8 !important; }

/* Feedback — minimal, left-border accent, no emoji */
.map-feedback-correct { background: #f0fdf4; border-left: 3px solid #22c55e; padding: 1rem 1.25rem; margin-top: 1rem; }
.map-feedback-correct h3 { color: #15803d; font-size: 16px; margin: 0 0 0.4rem 0; font-weight: 700; }
.map-feedback-correct p { color: #333; font-size: 15px; margin: 0.2rem 0; line-height: 1.6; }
.map-feedback-incorrect { background: #fef2f2; border-left: 3px solid #ef4444; padding: 1rem 1.25rem; margin-top: 1rem; }
.map-feedback-incorrect h3 { color: #dc2626; font-size: 16px; margin: 0 0 0.4rem 0; font-weight: 700; }
.map-feedback-incorrect p { color: #333; font-size: 15px; margin: 0.2rem 0; line-height: 1.6; }

/* Session complete */
.map-session-complete { font-size: 14px; color: #1b6d7c; text-align: center; margin-top: 1rem; font-weight: 600; }

/* Results */
.map-results-card { background: #fff; padding: 1.5rem 1.25rem; line-height: 1.6; }
.map-results-card h2 { color: #1b6d7c; font-size: 20px; border-bottom: 2px solid #3b8bc5; padding-bottom: 0.5rem; font-weight: 700; }
.map-score-big { font-size: 42px; font-weight: 700; color: #1b6d7c; text-align: center; margin: 1rem 0 0.25rem 0; }
.map-score-pct { text-align: center; color: #666; font-size: 15px; margin-bottom: 1rem; }
.map-results-card h3 { color: #333; font-size: 16px; margin-top: 1.25rem; font-weight: 700; }
.map-results-card ul { list-style: none; padding: 0; margin: 0; }
.map-results-card li { padding: 0.5rem 0; border-bottom: 1px solid #e0e0e0; font-size: 15px; color: #333; }
.map-results-followup { background: #f5f8fc; padding: 1rem 1.25rem; margin-top: 1.25rem; font-size: 15px; color: #333; line-height: 1.6; border-left: 3px solid #1b6d7c; }
```

### 2. Restructure `_build_practice_tab()` (~line 1607)

- Wrap everything in `gr.Column(elem_id="map-practice-wrapper")`
- Switch `question_display` from `gr.Markdown` to `gr.HTML`
- Add `gr.Radio` component (`answer_radio`) for MC, initially hidden, with `elem_classes=["map-radio-choices"]`
- Keep `gr.Textbox` (`answer_input`) for free-response, initially hidden, with `elem_classes=["map-text-input"]`
  - Change label to `"Enter the answer in the box."` (matches MAP wording)
  - Change to `lines=1` (MAP uses a small compact input)
- Switch `feedback_display` from `gr.Markdown` to `gr.HTML`
- Apply `elem_classes` to buttons: `["map-submit-btn"]`, `["map-next-btn"]`
- Update all `.click()` outputs from 5 to 6 elements (add `answer_radio`)
- Update `_submit` closure to pass both `answer_input` and `answer_radio`

### 3. Rewrite `_format_exercise()` (~line 1003)

Return MAP-styled HTML instead of Markdown:
- Subtle progress counter: `"Question 3 of 5"` right-aligned, gray
- **Teal banner** with concept name (matches MAP instruction header)
- White question area with 16px text
- **Blue horizontal rule** (`<hr class="map-blue-rule">`) separating question from answer area
- For MC: show `gr.Radio` with subject-appropriate labels:
  - Math/Science: `"A.  choice"` format (period + spaces)
  - Reading: `"1.  choice"` format (numbered)
- For free response: show textbox, hide radio
- Return 5-tuple: `(question_html, textbox_update, radio_update, feedback_clear, submit_btn_update)`

**[P2] HTML-escape all LLM-generated text** in every function that injects into `gr.HTML`. Add `import html` at the top and use `html.escape()` on every LLM-sourced string before interpolation. The full list of injection points:
- `_format_exercise()`: `ex['concept']`, `ex['question']`
- `submit_answer()`: `ex['explanation']`, `answer` (student's answer), `ex['correct_answer']`
- `_show_results()`: concept names in the breakdown list

Math/science content routinely contains `<`, `>`, `&` (e.g. `x < 4`, `a & b`) which browsers interpret as markup if unescaped.

### 4. Update `submit_answer()` (~line 1036)

- Change signature: `submit_answer(text_answer, radio_answer, pstate)`
- Determine active answer from whichever input is visible
- Parse radio selection: strip `"A.  "` or `"1.  "` prefix to extract both `letter` (e.g. `"a"`) and `choice_text` (e.g. `"3/4"`)
- **[P1] Keep letter-answer grading compatible.** Gemma sometimes returns `correct_answer: "A"` instead of the full choice text. The MC grading logic must check **all three** of these conditions (short-circuit on first `True`):
  ```python
  correct_ans = ex["correct_answer"].strip().lower()
  # 1. Direct letter match: student picked "A", answer key is "A"
  if letter == correct_ans:
      is_correct = True
  # 2. Choice text match: student picked "3/4", answer key is "3/4"
  elif choice_text == correct_ans:
      is_correct = True
  # 3. Letter-map lookup: student picked "A", resolve to choice text, compare
  elif letter in letter_map and letter_map[letter] == correct_ans:
      is_correct = True
  ```
  The critical fix is check #1 — comparing `letter == correct_ans` — which was missing in the prior attempt.
- Restyle feedback with `.map-feedback-correct` / `.map-feedback-incorrect`
- HTML-escape all LLM text in feedback (see [P2] above)
- Remove emoji — colored left borders provide the visual signal
- Session complete message: plain text, teal colored
- Return 6-tuple (add radio update)

### 5. Update `_show_results()` (~line 1136)

- Render as HTML instead of Markdown
- Teal banner header: "Session Complete"
- Large centered score (42px, teal)
- Concept breakdown as styled list with thin borders — **HTML-escape concept names** (see [P2])
- Follow-up recommendations with teal left-border accent
- Hide both answer inputs
- Return 5-tuple (caller adds pstate)

### 6. Fix all tuple returns for consistency

All return paths must match the 6-element output contract:
```
[question_display, answer_input, answer_radio, feedback_display, submit_btn, practice_state]
```

Functions to update:
- `start_practice()` — 4 error returns: 5-tuple -> 6-tuple (add hidden radio)
- `next_question()` — passes through, no logic change needed
- `_format_exercise()` — returns 5-tuple, caller adds pstate
- `_show_results()` — returns 5-tuple, caller adds pstate

## Future enhancements (not in this PR)

These MAP features require more complex Gradio components and are out of scope for now:
- **Multi-select checkbox questions** ("Choose two") — needs `gr.CheckboxGroup` with square checkbox CSS
- **Drag-and-drop interactions** (ordering, matching) — not natively supported in Gradio
- **Image-based answer choices** — needs custom HTML rendering
- **Two-column Part A / Part B layout** — needs CSS grid within HTML component
- **Passage display with numbered paragraphs** — needs HTML rendering for reading passages
- **Text highlight/selection in passages** — needs JavaScript interaction

## Verification

1. `just app` — launch Gradio frontend
2. Register a student with scores in the Scores tab
3. Go to Practice tab, start a session
4. Verify against screenshots in `assets/images/`:
   - Arial font (not Nunito) in practice area
   - Dark teal banner with concept name
   - 16px question text on white background
   - Blue horizontal rule separator
   - MC questions: plain radio buttons with `A.`/`B.` (math/science) or `1.`/`2.` (reading) labels
   - Free-response: small compact text input box
   - Flat teal buttons (no gradient, no rounded corners)
   - Feedback with left-border accent (no emoji)
   - Results page with teal headings and large score
5. Switch to Scores/Report tabs — verify they still use Nunito/indigo styling
6. `just test` — run existing tests to check nothing broke
