#!/bin/sh
set -e

echo "Waiting for Ollama at ${OLLAMA_HOST}..."
until curl -sf "${OLLAMA_HOST}/" > /dev/null 2>&1; do
    sleep 2
done
echo "Ollama is ready."

echo "Checking for gemma4:e4b model..."
if ! curl -sf "${OLLAMA_HOST}/api/tags" | grep -q "gemma4"; then
    echo "Pulling gemma4:e4b (this may take a few minutes on first run)..."
    curl -sf "${OLLAMA_HOST}/api/pull" -d '{"name": "gemma4:e4b"}' > /dev/null
    echo "Model pulled successfully."
else
    echo "Model already available."
fi

echo "Starting Gemma Adaptive Tutor..."
exec uv run python -m frontend
