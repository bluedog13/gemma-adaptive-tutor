# MAP Accelerator

**Personalized learning paths for advanced students who are left waiting.**

A Gemma 4-powered adaptive tutor that reads MAP (NWEA) scores, identifies the next band of concepts a student is ready for, and generates personalized challenges — so no student plateaus while the classroom catches up.

Built for the [Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon) | Track: Future of Education

## The Problem

Advanced students consistently lose their edge — not because they stop learning, but because the system stops challenging them. MAP test data shows a repeating pattern: high percentile at the start of each year, steady decline as the teacher focuses on students who need to catch up, then reset the next year.

## The Solution

MAP Accelerator uses Gemma 4's native function calling, multimodal input, and extended reasoning to:

1. **Analyze** MAP scores and identify where a student sits on the learning continuum
2. **Identify** the next band of concepts the student is ready for
3. **Generate** personalized exercises at the right difficulty level
4. **Track** progress and adapt the learning path
5. **Report** actionable insights to teachers and parents

## Tech Stack

- **Backend:** Python + FastAPI
- **Model:** Gemma 4 E4B (via Ollama, runs locally)
- **Frontend:** Gradio / Streamlit
- **Database:** SQLite

## Project Structure

```
map-accelerator/
├── README.md
├── PLAN.md                    # Project plan, architecture, timeline
├── docs/
│   ├── competition/           # Hackathon rules, evaluation criteria
│   ├── story/                 # Problem narrative, writeup drafts
│   └── architecture.md        # Technical architecture document
├── src/
│   ├── api/                   # FastAPI endpoints
│   ├── agents/                # Gemma 4 agent orchestration
│   ├── tools/                 # Function calling tools (curriculum, exercises, etc.)
│   ├── models/                # Data models and schemas
│   └── data/                  # MAP learning continuum data, RIT band mappings
├── frontend/                  # Gradio / Streamlit UI
├── tests/                     # Unit and integration tests
├── assets/
│   └── images/                # Cover image, diagrams, screenshots
├── scripts/                   # Setup, deployment, data processing scripts
├── config/                    # Model config, app settings
└── requirements.txt
```

## Setup

```bash
uv sync
uv run python -m src.api.main
```

## License

Apache 2.0
