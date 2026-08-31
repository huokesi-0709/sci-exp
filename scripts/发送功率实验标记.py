from __future__ import annotations

import argparse
import json
import socket
import time


def main() -> int:
    parser = argparse.ArgumentParser(description="向INA226采集器发送实验边界标记")
    parser.add_argument(
        "--event",
        required=True,
        choices=[
            "query_start",
            "query_end",
            "idle_start",
            "idle_end",
            "note",
            "collector_stop",
        ],
    )
    parser.add_argument("--run-key", required=True)
    parser.add_argument("--query-id", default="")
    parser.add_argument("--configuration", default="")
    parser.add_argument("--repetition", type=int, default=0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    value = {
        "schema": "ina226-marker-v1.0",
        "event": args.event,
        "run_key": args.run_key,
        "query_id": args.query_id,
        "configuration": args.configuration,
        "repetition": args.repetition,
        "sender_epoch_ns": time.time_ns(),
        "sender_monotonic_ns": time.monotonic_ns(),
    }
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(2.0)
        client.sendto(payload, (args.host, args.port))
        acknowledgement, _ = client.recvfrom(4096)
        ack = json.loads(acknowledgement.decode("utf-8"))
        if (
            not isinstance(ack, dict)
            or ack.get("type") != "marker_ack"
            or ack.get("event") != args.event
            or ack.get("run_key") != args.run_key
        ):
            raise SystemExit("功率采集器返回了不匹配的ACK")
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
