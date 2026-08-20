from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sci_exp.telemetry import read_sample  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="记录Radxa SoC温度、频率、内存和cooling state")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duration-seconds", type=float, default=600.0)
    parser.add_argument("--interval-seconds", type=float, default=0.2)
    parser.add_argument("--phase", default="discovery")
    args = parser.parse_args()
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        while running and time.monotonic() - started < args.duration_seconds:
            sample = read_sample([], 1.0)
            value = {
                "schema_version": "radxa-hardware-state-v1.0",
                "phase": args.phase,
                "host_epoch_ns": time.time_ns(),
                "elapsed_seconds": time.monotonic() - started,
                "device_temperature_c": sample.temperature_c,
                "available_memory_mb": sample.available_memory_mb,
                "load_1m": sample.load_1m,
                "cpu_frequency_mhz": sample.cpu_frequency_mhz,
                "cooling_state": sample.cooling_state,
                "process_rss_mb": sample.process_rss_mb,
            }
            handle.write(json.dumps(value, ensure_ascii=False) + "\n")
            handle.flush()
            time.sleep(max(0.05, args.interval_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
