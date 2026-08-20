#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/radxa/sci-exp"
cd "$PROJECT_ROOT"

if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi

export PYTHONPATH="$PROJECT_ROOT/src"
if [[ -z "${SCI_EXP_METER_HOST:-}" ]]; then
  echo "缺少SCI_EXP_METER_HOST；必须指向Windows功率采集电脑。" >&2
  exit 4
fi
"$PYTHON" -m sci_exp.cli validate \
  --protocols data/processed/protocols.jsonl \
  --queries data/splits_stratified_v2/test_op.jsonl
"$PYTHON" -m sci_exp.cli run --config configs/radxa.experiment.json
