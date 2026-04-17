FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY src/ src/
COPY frontend/ frontend/
COPY map_accelerator.db ./
COPY entrypoint.sh ./

ENV OLLAMA_HOST=http://ollama:11434

EXPOSE 7860

ENTRYPOINT ["./entrypoint.sh"]
