# Gemma Adaptive Tutor

**Every advanced student deserves a learning path that moves as fast as they do.**

Built for the [Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon) | Track: **Future of Education**

---

## The Problem

Over **13 million students** in the US take the MAP Growth assessment (by NWEA) every year. These standardized tests produce detailed RIT scores that pinpoint exactly where each student sits on the learning continuum — what they've mastered, what they're developing, and what they're ready to learn next.

But here's the gap: **the data exists, and nobody acts on it.**

These assessments produce dense PDF reports full of scores, percentiles, and growth projections — but no tools exist to automatically turn that data into personalized learning plans. Without that bridge, advanced learners often plateau. Their growth stalls, their percentiles decline, and their potential goes unrealized.

The problem isn't a lack of data. It's a lack of a system that **reads the data, understands it, and does something with it**.

## Why This Matters

This isn't a hypothetical. As a parent of an advanced elementary student, I watched the pattern repeat every year: high scores in the fall, steady decline by spring, reset the next year. The MAP data clearly showed what my child was ready to learn — but there was no easy way for anyone to turn those scores into a personalized plan.

Gemma Adaptive Tutor is the system I wished existed: one that takes the scores parents and teachers already have, and turns them into a personalized learning path — instantly, privately, and at no cost.

## The Solution

Gemma Adaptive Tutor bridges this gap. It takes the MAP scores that schools already have, and uses **Gemma 4 E4B** to automate what no existing tool does: analyze each student's trajectory, benchmark them against national norms, identify exactly what they're ready to learn next, and generate personalized practice at that level.

Gemma 4 powers every stage of the pipeline:

| Stage | What Happens | How Gemma 4 Is Used |
|-------|-------------|---------------------|
| **Ingest** | Scores entered manually or extracted from PDF/image uploads | Gemma 4 vision extracts scores from report screenshots and scanned documents |
| **Benchmark** | Student performance mapped against NWEA 2025 national norms | Percentile estimation and conditional growth projections contextualize each score |
| **Analyze** | Growth trends detected across seasons and grade levels | Gemma 4 reasons over longitudinal data to classify trends (growing, stalling, declining) and surface actionable insights |
| **Generate** | Personalized exercises created at the student's "Introduce" band | Gemma 4 produces curriculum-aligned problems across six MAP-authentic question formats |
| **Adapt** | Per-concept mastery tracked with an 80% threshold | Weak concepts automatically prioritized in the next practice session |
| **Report** | Teacher/parent dashboards with narrative insights | Gemma 4 generates personalized narrative reports grounded in the student's data |

### Subjects Supported

Mathematics, Reading, and Science — grades 2 through 5.

### MAP-Authentic Question Formats

Multiple choice, multi-select, two-part error analysis, sequence ordering, table matching, and fill-in-the-blank — mirroring the real MAP test experience so students build familiarity alongside mastery.

---

## Getting Started

### Prerequisites

- [just](https://github.com/casey/just) command runner (optional but recommended)

**Option A — Local:** Python 3.12+ and [Ollama](https://ollama.ai)

**Option B — Docker:** [Docker](https://docs.docker.com/get-docker/) (no Python or Ollama install needed)

### Option A: Run Locally

```bash
# Install dependencies and pull the Gemma 4 model
just setup

# Start Ollama with Gemma 4 E4B (in a separate terminal)
just ollama

# Launch the app
just app
```

### Option B: Run with Docker

```bash
# Build and start everything (Ollama + app) — one command
just docker
```

The app container automatically waits for Ollama, pulls the Gemma 4 model on first run, and starts the tutor. No local Python or Ollama install required.

To stop:

```bash
just docker-stop
```

Either way, the app will be available at **http://localhost:7860**.

A demo student with scores, practice sessions, and exercise results is included in the database so you can explore the full experience immediately.

### Manual Setup (without just)

```bash
uv sync
ollama pull gemma4:e4b
ollama run gemma4:e4b   # in a separate terminal
uv run python -m frontend
```

### All Commands

```bash
just setup              # Install deps + pull Gemma 4 model
just app                # Run Gradio frontend (localhost:7860)
just api                # Run FastAPI backend
just ollama             # Start Ollama with Gemma 4 (local)
just ollama-docker      # Start Ollama via Docker + pull model
just docker             # Run everything via Docker (Ollama + app)
just docker-stop        # Stop all Docker services
just lint               # Ruff lint check
just fmt                # Ruff format
just check              # Lint + format check
just reset-db           # Delete SQLite DB for fresh start
```

---

## Architecture

```text
Score Input (manual / PDF / image)
        │
        ▼
  RIT Band Mapping ──► Reinforce / Develop / Introduce bands
        │
        ▼
  National Benchmarking ──► Percentile rank + conditional growth projection
        │
        ▼
  Gemma 4 Trend Analysis ──► Growth classification + actionable insights
        │
        ▼
  Exercise Generation ──► Personalized problems at the "Introduce" level
        │
        ▼
  Student Answers ──► Per-concept mastery tracking
        │
        ▼
  Weak Concepts (<80%) ──► Fed back into next session
        │
        ▼
  Teacher/Parent Report ──► Dashboard + Gemma-generated narrative
```

### Project Structure

```text
gemma-adaptive-tutor/
├── frontend/
│   └── app.py                     # Gradio UI — three tabs: Scores, Practice, Reports
├── src/
│   ├── api/main.py                # FastAPI REST API (alternative entry point)
│   ├── tools/
│   │   ├── curriculum.py          # RIT-to-band mapping + Gemma trend analysis
│   │   ├── exercise_generator.py  # Gemma exercise generation + report narratives
│   │   └── score_extractor.py     # PDF/image score extraction (regex + Gemma vision)
│   ├── models/
│   │   ├── database.py            # SQLAlchemy models (Student, Score, Session, etc.)
│   │   └── schemas.py             # Pydantic validation for all inputs/outputs
│   ├── data/                      # RIT-to-concept mappings (Math, Reading, Science)
│   ├── prompts.py                 # All Gemma 4 prompt templates
│   └── constants.py               # Model config, NWEA 2025 norms tables
├── map_accelerator.db             # Demo database with sample student data
├── justfile                       # Task runner
└── pyproject.toml                 # Dependencies and project config
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **AI Model** | Gemma 4 E4B via Ollama (runs entirely locally — no data leaves the machine) |
| **Frontend** | Gradio with MAP-styled, kid-friendly interface |
| **Backend** | Python 3.12, FastAPI |
| **Database** | SQLite + SQLAlchemy (zero-config persistence) |
| **Norms Data** | NWEA 2025 MAP Growth Norms Technical Manual (student-level percentiles, conditional growth) |

---

## Demo Walkthrough

1. **Enter scores** — Type in a student's MAP RIT scores by grade and season, or upload a screenshot of their MAP report and let Gemma 4 vision extract the scores automatically.
2. **See the analysis** — Gemma benchmarks the student against 2025 national norms, classifies their growth trend, and identifies the exact concepts they're ready to learn next.
3. **Practice** — The student gets personalized exercises at their "Introduce" level, in MAP-authentic formats they'll see on the real test. Concepts they struggle with (<80% correct) automatically come back in the next session.
4. **Review the report** — Teachers and parents get a dashboard with percentile charts, growth projections, and a Gemma-generated narrative summarizing the student's trajectory and next steps.

The entire pipeline — from raw scores to personalized practice to narrative reports — runs locally on Gemma 4 E4B. **No student data ever leaves the machine.**

---

## Data Sources

All percentile and growth data is sourced from the **2025 MAP Growth Norms Technical Manual** (Version 2025.1.0, HMH/NWEA), using student-level achievement and growth tables. The model runs locally via Ollama — **no student data is sent to external services**.

## License

Apache 2.0
