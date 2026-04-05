# Plan: MAP-Style Question Formats for Exercise Generator

**Status:** Draft
**Reference screenshots:** `assets/images/math/`, `assets/images/language arts reading/`, `assets/images/science/`

## Context

The user has sample NWEA MAP test screenshots showing the actual question formats used across Math, Science, and Language Arts: Reading. Currently, Gemma generates generic questions (basic MC, word problems, fill-in-the-blank). The goal is to update the prompts and UI so generated questions **match the style/format of real MAP test questions**, making practice feel authentic.

**Key constraint:** Gemma outputs text, not images. Many MAP questions use visuals (coins, base-10 blocks, shapes, arrays, protractors, diagrams). We handle this by describing visuals in text (e.g., "A set of base-10 blocks shows 4 hundreds flats, 3 tens rods, and 2 ones cubes").

**Band mapping:** We do NOT try to tag the sample screenshots to specific RIT bands. We adopt the FORMAT/STYLE of the questions and let the existing band-to-concept mapping determine the content.

## MAP Question Formats Observed (from screenshots)

### Math
| Format | Example | Text-achievable? |
|--------|---------|-----------------|
| Standard MC (4 options) | "Which number do the blocks represent?" | Yes (describe blocks in text) |
| Multi-select | "Choose all shapes divided into four-fourths" | Yes |
| Fill-in-the-blank | "What is the total? Enter the answer in the box." | Yes (already supported) |
| Error analysis (two-part) | "Which option explains Taj's mistake?" + "What is the correct answer?" | Yes |
| Visual-described MC | Coins, arrays, base-10 blocks | Yes (describe in words) |

### Science
| Format | Example | Text-achievable? |
|--------|---------|-----------------|
| Scenario + multi-select | "Which designs reduce warming? Choose two." | Yes |
| Table matching | Before/after heating → "Reversible? Yes/No" | Yes |
| Sequence ordering | "What are the stages of the life cycle?" | Yes |
| Pattern prediction | Moon phases → predict missing day | Yes (describe in text) |
| Standard MC with scenario | Fossils → "What were conditions?" | Yes |

### Reading
| Format | Example | Text-achievable? |
|--------|---------|-----------------|
| Passage + Part A/Part B | "What is the lesson?" then "Which detail supports Part A?" | Yes |
| Passage + multi-select | "How are Dad's ideas different? Choose two." | Yes |
| Sentence selection | "Choose the sentence that tells how bats differ from birds" | Yes |
| Sequence completion | Procedural text with missing step | Yes |
| Main idea MC | Paragraph + "What is the main idea?" | Yes (already supported) |

## Implementation Plan

### Step 1: Update Exercise schema (`src/models/schemas.py`)

Add optional fields to the `Exercise` class for new question structures:

```python
# For multi-select ("Choose two")
num_correct: int | None = None            # how many to pick (e.g. 2)
correct_answers: list[str] | None = None  # list of correct answers

# For two-part / error analysis (Part A + Part B)
part_b_question: str | None = None
part_b_choices: list[str] | None = None
part_b_correct: str | None = None

# For sequence ordering
items_to_order: list[str] | None = None   # shuffled items
correct_order: list[str] | None = None    # correct sequence

# For table matching
match_pairs: dict[str, str] | None = None   # {item: correct_category}
match_options: list[str] | None = None      # pool of category labels

# For scenario/passage context
scenario: str | None = None                 # longer context text shown above the question
```

All fields default to `None` -- fully backward-compatible with existing data.

### Step 2: Update prompts (`src/prompts.py`)

Replace `_EXERCISE_TYPE_GUIDANCE` for each subject with MAP-format-specific instructions. Key changes:

**Math** -- new question types: `multiple_choice`, `multi_select`, `fill_in_the_blank`, `two_part` (covers error analysis). Add instructions to describe visuals in text (blocks, arrays, coins, shapes). Provide JSON field mapping for each type.

**Reading** -- new question types: `passage_two_part`, `passage_multi_select`, `sentence_selection`, `sequence_completion`, `main_idea_mc`. ALL reading questions must include a `scenario` field with a 4-8 sentence passage. Part A/Part B structure uses `part_b_*` fields.

**Science** -- new question types: `scenario_multi_select`, `table_matching`, `sequence_order`, `pattern_prediction`, `multiple_choice`. ALL science questions must include a `scenario` field. Matching uses `match_pairs`/`match_options`. Ordering uses `items_to_order`/`correct_order`.

Update the JSON schema documentation in `build_exercise_prompt()` to list all optional fields so Gemma knows the full contract.

### Step 3: Update exercise parser (`src/tools/exercise_generator.py`)

In the `generate_exercises()` parsing loop (~line 56-75), extract all new optional fields from each exercise dict and pass them to the `Exercise` constructor. Apply the same nested-list normalization for list fields.

### Step 4: Update Gradio UI (`frontend/app.py`)

**4a. Add a CheckboxGroup component** to `_build_practice_tab()` for multi-select questions (alongside existing Radio and Textbox).

**4b. Expand `_format_exercise()`** (currently line 1014) to handle new question types:
- `multi_select` -- show CheckboxGroup with "Choose {num_correct}" instruction
- `two_part` -- show Part A first (as MC or fill-in), track sub-state in `pstate["current_part"]`
- `sequence_order` -- show shuffled items with labels, ask student to type correct order
- `table_matching` -- render as labeled items with dropdown/radio for each
- Any type with `scenario` -- render scenario text in a styled container above the question

**4c. Expand `submit_answer()`** (currently line 1061) to handle:
- Multi-select: compare set of selected answers against `correct_answers`
- Two-part: on Part A submit, store answer and advance to Part B; on Part B submit, compute combined correctness and advance to next exercise
- Sequence order: compare submitted order against `correct_order`
- Table matching: compare each submitted pair against `match_pairs`

**4d. Update the output tuple** -- `_format_exercise` currently returns a 5-tuple. Adding CheckboxGroup makes it 6. Update all return sites: `_format_exercise`, `submit_answer`, `next_question`, `_show_results`, `start_practice`.

**4e. Add CSS** for scenario/passage containers (`.map-scenario-box`), Part A/B labels, and matching table layout.

### Step 5: End-to-end testing

1. Run `just app` and generate exercises for each subject
2. Verify Gemma outputs valid JSON with new fields populated
3. Verify each question type renders correctly in the UI
4. Verify answer checking works for multi-select, two-part, ordering, matching
5. Verify backward compatibility -- old question types still work

## Files to Modify

| File | Change |
|------|--------|
| `src/models/schemas.py` | Add optional fields to `Exercise` |
| `src/prompts.py` | Rewrite `_EXERCISE_TYPE_GUIDANCE` per subject, update JSON schema docs |
| `src/tools/exercise_generator.py` | Parse new fields in exercise loop |
| `frontend/app.py` | Add CheckboxGroup, expand `_format_exercise`, `submit_answer`, `_show_results`, CSS |

## Risks

- **Gemma output consistency** -- Gemma may not always produce well-structured two-part or matching JSON. Mitigation: fall back to simple MC rendering if required fields are missing.
- **UI tuple size change** -- Adding CheckboxGroup changes the output contract for all practice functions. Must update all return sites in one coordinated change.
- **Two-part state management** -- Need sub-state tracking (`pstate["current_part"]`). Reset on each new exercise.
