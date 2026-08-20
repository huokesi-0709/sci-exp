#!/usr/bin/env bash
set -euo pipefail

echo "Candidate hwmon power inputs:"
find /sys/class/hwmon -maxdepth 2 -type f -name 'power*_input' -print 2>/dev/null || true

echo
echo "Candidate power-supply inputs:"
find /sys/class/power_supply -maxdepth 2 -type f \
  \( -name 'power_now' -o -name 'current_now' -o -name 'voltage_now' \) \
  -print 2>/dev/null || true

echo
echo "Do not configure a path until its unit and rail coverage are verified."
