#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/radxa/sci-exp"
cd "${PROJECT_ROOT}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi
export PYTHONPATH="${PROJECT_ROOT}/src"

if [[ -z "${SCI_EXP_METER_HOST:-}" ]]; then
  echo "缺少SCI_EXP_METER_HOST；必须设置为运行ESP32采集器的Windows电脑局域网IP。" >&2
  exit 4
fi

REQUIRED_FILES=(
  "data/processed/protocols.jsonl"
  "data/splits_stratified_v2/test_op.jsonl"
  "data/splits_stratified_v2/test_ch.jsonl"
  "data/splits_stratified_v2/正式400条分层六分区清单_v2.0.json"
  "models/risk_model.json"
  "models/resource_profile.json"
  "models/calibration_thresholds.json"
  "bin/llama-server"
)
for path in "${REQUIRED_FILES[@]}"; do
  if [[ ! -e "${path}" ]]; then
    echo "缺少正式实验前置文件: ${path}" >&2
    exit 4
  fi
done

for split in data/splits_stratified_v2/test_op.jsonl data/splits_stratified_v2/test_ch.jsonl; do
  if ! "${PYTHON}" -c 'import json,sys; rows=[json.loads(x) for x in open(sys.argv[1],encoding="utf-8") if x.strip()]; raise SystemExit(0 if rows and all(r.get("final_evaluation_eligible") is True and r.get("dataset_role") != "development_gold" for r in rows) else 1)' "$split"; then
    echo "拒绝正式测试：${split}仍是development gold或final_evaluation_eligible不为true。" >&2
    exit 5
  fi
done

IDLE_BASELINE_SECONDS="${SCI_EXP_IDLE_BASELINE_SECONDS:-60}"
"${PYTHON}" scripts/发送功率实验标记.py \
  --event idle_start --run-key preformal_idle \
  --host "${SCI_EXP_METER_HOST}" --port 8765
sleep "${IDLE_BASELINE_SECONDS}"
"${PYTHON}" scripts/发送功率实验标记.py \
  --event idle_end --run-key preformal_idle \
  --host "${SCI_EXP_METER_HOST}" --port 8765

"${PYTHON}" -m sci_exp.cli device-info \
  --output results/radxa_device_info_formal_v1.0.json

if [[ ! -x "bin/llama-server" ]]; then
  echo "bin/llama-server存在但不可执行" >&2
  exit 4
fi

"${PYTHON}" -m sci_exp.cli validate \
  --protocols data/processed/protocols.jsonl \
  --queries data/splits_stratified_v2/test_op.jsonl
"${PYTHON}" -m sci_exp.cli validate \
  --protocols data/processed/protocols.jsonl \
  --queries data/splits_stratified_v2/test_ch.jsonl

"${PYTHON}" -m sci_exp.cli run \
  --config configs/radxa.experiment.json \
  --output results/radxa_test_op_runs.jsonl
"${PYTHON}" -m sci_exp.cli run \
  --config configs/radxa.challenge.json \
  --output results/radxa_test_ch_runs.jsonl

echo "Radxa test_op/test_ch全配置运行完成；这些输出仍需盲法安全判定和资源预处理。"
