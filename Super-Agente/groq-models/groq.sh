#!/bin/bash
# Groq LLM Launcher
# Usage: ./groq.sh [model] [prompt]

MODEL="${1:-llama-3.3-70b-versatile}"
PROMPT="$2"

cd "$(dirname "$0")"

if [ -z "$PROMPT" ]; then
    # Interactive mode
    python3 groq_llm.py --interactive -m "$MODEL"
else
    # Single prompt mode
    python3 groq_llm.py -m "$MODEL" -p "$PROMPT"
fi
