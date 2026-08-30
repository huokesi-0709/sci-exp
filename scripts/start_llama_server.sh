#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/radxa/sci-exp"
LLAMA_SERVER="$PROJECT_ROOT/bin/llama-server"
# E1的候选运行时资产保存在Git外的Radxa模型缓存中。可用MODEL_PATH覆盖，
# 但不得在未更新清单和重新进行dry-run的情况下改回旧下载GGUF。
MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/models/qwen1_5-0_5b-chat-official-4d14e384-q4_k_m-r2.gguf}"

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
  --no-cache-prompt \
  --cache-ram 0 \
  --no-cache-idle-slots \
  --threads "$(nproc)"
