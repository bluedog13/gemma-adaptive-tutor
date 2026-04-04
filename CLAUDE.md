# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MAP Accelerator is a Gemma 4-powered adaptive math tutor for advanced students (grades 2-5) who plateau because classrooms don't challenge them. It ingests NWEA MAP RIT scores, maps them to curriculum bands, generates personalized exercises via Gemma 4, tracks progress, and produces teacher/parent reports.

Built for the Kaggle Gemma 4 Good Hackathon (Future of Education track).

## Commands

This project uses [just](https://github.com/casey/just) as a command runner. Run `just` to see all available recipes.

```bash
just setup          # install deps + pull Gemma 4 model (first time)
just app            # run Gradio frontend (localhost:7860)
just api            # run FastAPI backend
just test           # run all tests
just test-one PATH  # run a single test file/function
just lint           # ruff lint check
just fmt            # ruff format
just check          # lint + format check
just reset-db       # delete SQLite DB for fresh start
```

**Prerequisite:** Gemma 4 E4B must be running locally via Ollama (`just ollama`). The model name is configured in `src/constants.py` as `MODEL`.

## Architecture

### Two entry points, shared core

- **`frontend/app.py`** — Gradio UI (primary). Three-tab interface: score entry/analysis, practice sessions, progress reports. Calls tools directly (no API layer). Uses module-level globals for session state.
- **`src/api/main.py`** — FastAPI REST API (alternative). Same functionality exposed as endpoints. SQLite DB initialized on startup via lifespan handler.

Both entry points use the same core modules:

### Core modules

- **`src/tools/curriculum.py`** — Maps RIT scores to Develop/Introduce bands using `src/data/rit_to_concept_math_2plus.json`. Calls Gemma 4 for trend analysis (`detect_trend`). Bands are 10-RIT-point ranges (e.g., "181-190").
- **`src/tools/exercise_generator.py`** — Calls Gemma 4 to generate exercises for a given band. Also generates teacher reports. All LLM calls go through `ollama.chat()`.
- **`src/prompts.py`** — All Gemma 4 prompt templates. Includes NWEA national norms context (percentiles, conditional growth data) embedded in prompts for grounded analysis.
- **`src/constants.py`** — Model name, data paths, NWEA 2025 norms tables (mean RIT, percentiles, conditional growth by grade). Data sourced from the official 2025 MAP Growth Norms Technical Manual. See `docs/nwea_2025_norms_analysis.md` for sourcing details.
- **`src/models/schemas.py`** — Pydantic models for all inputs/outputs. Key types: `ScoreInput`, `BandInfo`, `CurriculumResult`, `Exercise`, `ExerciseSet`, `SessionSummary`, `StudentProgress`.
- **`src/models/database.py`** — SQLAlchemy models (Student, Score, PracticeSession, ExerciseResultRecord). SQLite at `map_accelerator.db`. DB file is gitignored.

### Data flow

Score input → `map_rit_to_curriculum()` (band lookup + Gemma trend analysis) → `generate_exercises()` (Gemma creates problems for Introduce band) → student answers → results tracked per-concept → weak concepts (<80%) fed back into next exercise generation session.

## Key Design Decisions

- **Season ordering** uses calendar order (`spring=0, fall=1, winter=2`), not school-year order. This is intentional — see `SEASON_ORDER` in constants.
- **Mastery threshold** is 80% correct per concept. Below 80% = "needs work" and gets priority in next exercise generation.
- **Gemma 4 responses** are parsed as JSON. The exercise generator handles both array and object responses from the model, and normalizes nested list choices.
- **Grade-at-test computation** (`_grade_for_score` in `frontend/app.py`) accounts for school year boundaries: spring of year Y = school year (Y-1)-Y.

## NWEA Norms Data

All percentile and growth data in `src/constants.py` is sourced from the **2025 MAP Growth Norms Technical Manual** (Version 2025.1.0, HMH/NWEA):
- **PDF:** https://www.nwea.org/resource-center/white-paper/88182/MAP-Growth-Norms_NWEA_Technical-Manual.pdf/
- **Tables used:** A.1 (Mean & SD), B.1/B.3/B.5 (Achievement Percentiles — Fall/Winter/Spring, Student-level)
- **Analysis doc:** `docs/nwea_2025_norms_analysis.md` — full sourcing, validation, and integration details
- **Important:** Always use **student-level** tables (not school-level). When NWEA publishes updated norms, follow the same process documented in the analysis doc.

## Plan Documents

Implementation plans live in `docs/plans/`. These capture design decisions, file-change lists, and edge cases for features before (and during) development.

- **Before starting a feature**, check if a plan doc exists and read it.
- **When the approach changes** during implementation (new file added, design decision reversed, edge case discovered), update the plan doc to reflect reality.
- **When a feature is complete**, update the plan's `Status` field to `Done`.

## Style Rules

- PEP 8 with 88-char line length (Ruff/Black standard)
- Double quotes for strings
- Type hints required on all function signatures
- Modern Python generics (`dict[str, Any]` not `Dict[str, Any]`)
- Sphinx-style docstrings (`:param`, `:return`, `:raises`)
- Imports grouped: stdlib, third-party, local (separated by blank lines)
