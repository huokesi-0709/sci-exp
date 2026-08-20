from __future__ import annotations

import argparse
import json
import signal
import time


def main() -> int:
    parser = argparse.ArgumentParser(description="E6低CPU内存headroom压力进程")
    parser.add_argument("--mb", required=True, type=int)
    parser.add_argument("--duration-seconds", type=float, default=1800.0)
    parser.add_argument("--touch-interval-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if args.mb < 64:
        raise SystemExit("--mb至少64；正式值按设备可用内存探索结果冻结")
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    block = bytearray(args.mb * 1024 * 1024)
    for index in range(0, len(block), 4096):
        block[index] = 1
    print(json.dumps({"allocated_mb": args.mb, "pid": __import__("os").getpid()}, ensure_ascii=False), flush=True)
    started = time.monotonic()
    while running and time.monotonic() - started < args.duration_seconds:
        # Touch one page per interval so the reservation remains resident without
        # introducing a competing CPU workload into the energy measurement.
        block[int(time.monotonic()) % len(block)] ^= 1
        time.sleep(max(1.0, args.touch_interval_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
