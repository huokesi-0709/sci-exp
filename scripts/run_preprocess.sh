#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "用法: bash scripts/run_preprocess.sh <查询JSONL> [seed] [训练增强副本数0..2] [preserve]" >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUERY_PATH="$1"
SEED="${2:-42}"
AUGMENT_COPIES="${3:-0}"
PRESERVE="${4:-}"

if [[ "${QUERY_PATH}" != /* ]]; then
  QUERY_PATH="${PROJECT_ROOT}/${QUERY_PATH}"
fi

export PYTHONPATH="${PROJECT_ROOT}/src"
ARGS=(
  -m sci_exp.cli preprocess-queries
  --input "${QUERY_PATH}"
  --output-directory "${PROJECT_ROOT}/data"
  --seed "${SEED}"
  --augment-train-copies "${AUGMENT_COPIES}"
  --fail-on-quarantine
)
if [[ "${PRESERVE}" == "preserve" ]]; then
  ARGS+=(--preserve-existing-splits)
fi
python3 "${ARGS[@]}"
