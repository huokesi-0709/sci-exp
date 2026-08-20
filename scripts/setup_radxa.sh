#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/radxa/sci-exp"
cd "$PROJECT_ROOT"
mkdir -p results

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate
if compgen -G "wheelhouse/*" > /dev/null; then
  python -m pip install --no-index --find-links wheelhouse -e '.[research,hardware,dense]'
elif [ "${SCI_EXP_ALLOW_NETWORK_SETUP:-0}" = "1" ]; then
  python -m pip install -e '.[research,hardware,dense]'
fi
SITE_PACKAGES="$(python -c 'import site; print(site.getsitepackages()[0])')"
printf '%s\n' "$PROJECT_ROOT/src" > "$SITE_PACKAGES/sci_exp_local.pth"
python -c 'import numpy, scipy, sklearn, pandas, psutil, serial, sentence_transformers' || {
  echo "依赖不完整。提供ARM64 wheelhouse后重跑，或仅在联网准备阶段设置 SCI_EXP_ALLOW_NETWORK_SETUP=1。" >&2
  exit 3
}
python -m sci_exp.cli device-info --output results/radxa_device_info.json

echo "Radxa environment ready at $PROJECT_ROOT"
