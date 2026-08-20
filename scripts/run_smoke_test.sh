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
"$PYTHON" -m unittest discover -s tests -v
"$PYTHON" -m sci_exp.cli smoke --config configs/radxa.smoke.json
