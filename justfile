# MAP Accelerator justfile

# Default: list available recipes
default:
    @just --list

# Install dependencies
install:
    uv sync

# Run the Gradio frontend (primary UI)
app:
    uv run python -m frontend

# Run the FastAPI backend
api:
    uv run uvicorn src.api.main:app --reload

# Run all tests
test *args:
    uv run pytest {{ args }}

# Run a single test file or test
test-one path:
    uv run pytest {{ path }} -v

# Lint with ruff
lint:
    uv run ruff check src/ frontend/

# Fix lint issues
lint-fix:
    uv run ruff check --fix src/ frontend/

# Format code
fmt:
    uv run ruff format src/ frontend/

# Check formatting without changing files
fmt-check:
    uv run ruff format --check src/ frontend/

# Lint + format check
check: lint fmt-check

# Start Ollama with Gemma 4 E4B
ollama:
    ollama run gemma4:e4b

# Pull the Gemma 4 model (first-time setup)
pull-model:
    ollama pull gemma4:e4b

# Start Ollama via Docker and pull the model
ollama-docker:
    docker compose up -d ollama
    @echo "Waiting for Ollama to start..."
    @sleep 3
    docker compose exec ollama ollama pull gemma4:e4b
    @echo "Gemma 4 E4B ready. Ollama running at http://localhost:11434"

# Run everything via Docker (Ollama + app)
docker:
    docker compose up --build

# Stop all Docker services
docker-stop:
    docker compose down

# Delete the SQLite database and start fresh
reset-db:
    rm -f map_accelerator.db
    @echo "Database deleted. It will be recreated on next app start."

# Full setup: install deps + pull model
setup: install pull-model
    @echo "Setup complete. Run 'just app' to start."
