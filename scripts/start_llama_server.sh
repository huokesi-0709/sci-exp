#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/radxa/sci-exp"
LLAMA_SERVER="$PROJECT_ROOT/bin/llama-server"
MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/models/qwen1_5-0_5b-chat-q4_k_m.gguf}"

if [ ! -x "$LLAMA_SERVER" ]; then
  echo "Missing executable: $LLAMA_SERVER" >&2
  exit 2
fi
if [ ! -f "$MODEL_PATH" ]; then
  echo "Missing GGUF model: $MODEL_PATH" >&2
  exit 2
fi

exec "$LLAMA_SERVER" \
  --model "$MODEL_PATH" \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096 \
  --threads "$(nproc)"
