# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.12 application for a local Gemma-powered adaptive tutor. The Gradio UI lives in `frontend/`, with `frontend/app.py` as the primary interface. Core code is under `src/`: `src/api/` contains the FastAPI backend, `src/tools/` contains curriculum mapping, exercise generation, and score extraction, `src/models/` holds SQLAlchemy and Pydantic models, and `src/data/` stores RIT-to-concept JSON mappings. Shared prompts and constants are in `src/prompts.py` and `src/constants.py`. Assets and docs belong in `assets/`, `docs/`, and `resources/`. The demo SQLite database is `map_accelerator.db`.

## Build, Test, and Development Commands

Use `just` recipes when available:

- `just install`: run `uv sync` and install project dependencies.
- `just setup`: install dependencies and pull the local Gemma model.
- `just app`: start the Gradio app at `http://localhost:7860`.
- `just api`: start the FastAPI backend.
- `just docker`: run the app plus Ollama with Docker Compose.
- `just test`: run pytest.
- `just check`: run Ruff linting and formatting checks.
- `just fmt`: format Python files with Ruff.

Without `just`, use `uv run python -m frontend`, `uv run pytest`, and `uv run ruff check src/ frontend/ tests/`.

## Coding Style & Naming Conventions

Use Ruff for linting and formatting. Keep Python code idiomatic, typed where practical, and organized by responsibility. Use 4-space indentation, `snake_case` for functions and variables, `PascalCase` for Pydantic and SQLAlchemy classes, and uppercase names for constants. Keep prompts centralized in `src/prompts.py`; avoid scattering model instructions across UI or API code.

## Testing Guidelines

Place tests in `tests/` and name files `test_*.py`. Prefer focused unit tests for `src/tools/` parsing, curriculum mapping, and exercise generation helpers, plus API tests for `src/api/` behavior. Run `just test` before submitting changes. For async code, use `pytest-asyncio`, already listed as a dev dependency.

## Commit & Pull Request Guidelines

Recent commits use short imperative messages such as `Refine README messaging` and `Update demo database`. Follow that style: concise, present-tense summaries with details in the body when needed. Pull requests should describe the change, mention affected modules, link issues, and include screenshots for UI changes. Call out edits to `map_accelerator.db`, prompts, or bundled data because they affect demo behavior.

## Security & Configuration Tips

Do not commit private student reports, screenshots, or logs. Sample score report images were removed from tracking, so keep sensitive files out of the repo. Prefer local Ollama execution for privacy, and document new environment variables in `README.md`.
