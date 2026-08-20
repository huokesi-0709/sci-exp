#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/radxa/sci-exp"
cd "$PROJECT_ROOT"
mkdir -p results

if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi

export PYTHONPATH="$PROJECT_ROOT/src"
"$PYTHON" -m sci_exp.cli device-info --output results/radxa_device_info.json

{
  uname -a
  printf '\nCPU\n'
  lscpu
  printf '\nMEMORY\n'
  free -h
  printf '\nKERNEL\n'
  cat /proc/version
  printf '\nCPU GOVERNORS AND FREQUENCIES\n'
  for path in /sys/devices/system/cpu/cpu*/cpufreq; do
    [ -d "$path" ] || continue
    printf '%s governor=' "$path"
    cat "$path/scaling_governor" 2>/dev/null || true
    printf ' cur_khz='
    cat "$path/scaling_cur_freq" 2>/dev/null || true
    printf ' max_khz='
    cat "$path/scaling_max_freq" 2>/dev/null || true
  done
  printf '\nTHERMAL ZONES\n'
  for path in /sys/class/thermal/thermal_zone*; do
    [ -d "$path" ] || continue
    printf '%s type=' "$path"
    cat "$path/type" 2>/dev/null || true
    printf ' temp='
    cat "$path/temp" 2>/dev/null || true
  done
  printf '\nCOOLING DEVICES\n'
  for path in /sys/class/thermal/cooling_device*; do
    [ -d "$path" ] || continue
    printf '%s type=' "$path"
    cat "$path/type" 2>/dev/null || true
    printf ' cur_state='
    cat "$path/cur_state" 2>/dev/null || true
    printf ' max_state='
    cat "$path/max_state" 2>/dev/null || true
  done
} > results/radxa_device_info.txt

echo "Device information written to results/"
