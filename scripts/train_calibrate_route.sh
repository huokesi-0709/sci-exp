#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/radxa/sci-exp"
cd "$PROJECT_ROOT"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi
export PYTHONPATH="$PROJECT_ROOT/src"

STAGE="${1:-}"
if [[ -z "$STAGE" ]]; then
  echo "用法: bash scripts/train_calibrate_route.sh <train-runs|fit-models|calibration-runs|calibrate|route-test>" >&2
  exit 2
fi

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "缺少阶段输入: $1" >&2
    exit 4
  fi
}

require_meter() {
  if [[ -z "${SCI_EXP_METER_HOST:-}" ]]; then
    echo "运行阶段必须设置SCI_EXP_METER_HOST。" >&2
    exit 4
  fi
}

case "$STAGE" in
  train-runs)
    require_meter
    "$PYTHON" -m sci_exp.cli run \
      --config configs/radxa.experiment.json \
      --queries data/splits_stratified_v2/train.jsonl \
      --output results/radxa_train_runs.jsonl
    echo "复制Radxa运行日志回Windows，与INA226日志合并为results/radxa_train_runs_with_energy.jsonl，并完成train_adjudication.jsonl。"
    ;;
  fit-models)
    require_file results/radxa_train_runs_with_energy.jsonl
    require_file data/annotations/train_adjudication.jsonl
    "$PYTHON" -m sci_exp.cli apply-adjudication \
      --input results/radxa_train_runs_with_energy.jsonl \
      --labels data/annotations/train_adjudication.jsonl \
      --output results/radxa_train_adjudicated.jsonl
    "$PYTHON" -m sci_exp.cli train-risk \
      --input results/radxa_train_adjudicated.jsonl \
      --output models/risk_model.json
    "$PYTHON" -m sci_exp.cli profile-resources \
      --input results/radxa_train_runs_with_energy.jsonl \
      --output models/resource_profile.json
    ;;
  calibration-runs)
    require_meter
    require_file models/risk_model.json
    require_file models/resource_profile.json
    "$PYTHON" -m sci_exp.cli run \
      --config configs/radxa.experiment.json \
      --queries data/splits_stratified_v2/cal_op.jsonl \
      --output results/radxa_calibration_runs.jsonl
    echo "完成Gold Calibration盲审后生成data/annotations/calibration_adjudication.jsonl。"
    ;;
  calibrate)
    require_file results/radxa_calibration_runs.jsonl
    require_file data/annotations/calibration_adjudication.jsonl
    require_file models/risk_model.json
    "$PYTHON" -m sci_exp.cli apply-adjudication \
      --input results/radxa_calibration_runs.jsonl \
      --labels data/annotations/calibration_adjudication.jsonl \
      --output results/radxa_calibration_adjudicated.jsonl
    "$PYTHON" -m sci_exp.cli score-risk \
      --input results/radxa_calibration_adjudicated.jsonl \
      --model models/risk_model.json \
      --output results/radxa_calibration_scores.jsonl
    "$PYTHON" -m sci_exp.cli calibrate \
      --input results/radxa_calibration_scores.jsonl \
      --output models/calibration_thresholds.json \
      --alpha 0.05 --delta 0.05
    ;;
  route-test)
    require_meter
    require_file models/risk_model.json
    require_file models/resource_profile.json
    require_file models/calibration_thresholds.json
    "$PYTHON" -m sci_exp.cli route \
      --config configs/radxa.experiment.json \
      --queries data/splits_stratified_v2/test_op.jsonl \
      --output results/radxa_test_op_routed_runs.jsonl
    "$PYTHON" -m sci_exp.cli route \
      --config configs/radxa.challenge.json \
      --queries data/splits_stratified_v2/test_ch.jsonl \
      --output results/radxa_test_ch_routed_runs.jsonl
    ;;
  *)
    echo "未知阶段: $STAGE" >&2
    exit 2
    ;;
esac
