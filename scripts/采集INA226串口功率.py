from __future__ import annotations

import argparse
import json
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="采集ESP32-S3 INA226 NDJSON功率流")
    parser.add_argument("--serial", required=True, help="例如COM6或/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--marker-host", default="127.0.0.1")
    parser.add_argument("--marker-port", type=int, default=8765)
    parser.add_argument("--sync-interval", type=float, default=10.0)
    parser.add_argument("--no-auto-start", action="store_true")
    return parser.parse_args()


def add_host_time(value: dict[str, Any]) -> dict[str, Any]:
    # SYNC replies echo the epoch timestamp embedded in the request.  Preserve it
    # before attaching the collector receive timestamp; otherwise the original
    # request time is silently overwritten and E0 cannot estimate synchronization
    # round-trip time.
    if value.get("type") == "sync_ack" and "host_epoch_ns" in value:
        value = {
            **value,
            "sync_request_epoch_ns": value["host_epoch_ns"],
        }
    return {
        **value,
        "host_epoch_ns": time.time_ns(),
        "host_monotonic_ns": time.monotonic_ns(),
    }


def split_complete_lines(
    pending: bytes, received: bytes
) -> tuple[list[bytes], bytes]:
    """Keep partial serial records until their terminating newline arrives."""
    buffer = pending + received
    complete: list[bytes] = []
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        complete.append(line.rstrip(b"\r"))
    return complete, buffer


def main() -> int:
    args = parse_args()
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("缺少pyserial：请安装项目hardware可选依赖") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    running = True

    def stop_handler(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    marker_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    marker_socket.setblocking(False)
    marker_socket.bind((args.marker_host, args.marker_port))
    serial_port = serial.Serial(args.serial, args.baud, timeout=0.05)
    time.sleep(1.5)
    serial_port.reset_input_buffer()

    def send(command: str) -> None:
        serial_port.write((command.strip() + "\n").encode("ascii"))
        serial_port.flush()

    send("META")
    send(f"SYNC {time.time_ns()}")
    if not args.no_auto_start:
        send("START")

    next_sync = time.monotonic() + args.sync_interval
    counts = {
        "sample": 0,
        "environment": 0,
        "marker": 0,
        "invalid": 0,
        "invalid_serial": 0,
        "invalid_marker": 0,
        "partial_serial_at_shutdown": 0,
    }
    serial_pending = b""
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        session = add_host_time(
            {
                "type": "collector_session",
                "schema": "ina226-sht31-collector-v2.0",
                "serial_port": args.serial,
                "baud": args.baud,
                "marker_host": args.marker_host,
                "marker_port": args.marker_port,
            }
        )
        handle.write(json.dumps(session, ensure_ascii=False) + "\n")
        handle.flush()

        def record_invalid(source: str, raw: bytes, exc: Exception) -> None:
            """Preserve bounded diagnostics instead of silently discarding bad input."""
            source_count = f"invalid_{source}"
            counts["invalid"] += 1
            counts[source_count] += 1
            diagnostic = add_host_time(
                {
                    "type": "collector_invalid",
                    "source": source,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "byte_length": len(raw),
                    "preview_hex": raw[:64].hex(),
                }
            )
            handle.write(json.dumps(diagnostic, ensure_ascii=False) + "\n")
            handle.flush()

        while running:
            if time.monotonic() >= next_sync:
                send(f"SYNC {time.time_ns()}")
                next_sync = time.monotonic() + args.sync_interval

            try:
                packet, address = marker_socket.recvfrom(65535)
            except BlockingIOError:
                packet = b""
                address = ("", 0)
            if packet:
                try:
                    marker = json.loads(packet.decode("utf-8"))
                    if not isinstance(marker, dict):
                        raise ValueError("marker must be an object")
                    marker = add_host_time(
                        {
                            **marker,
                            "type": "marker",
                            "marker_sender": f"{address[0]}:{address[1]}",
                        }
                    )
                    marker_name = str(marker.get("event", "marker"))
                    run_key = str(marker.get("run_key", ""))
                    send(f"MARK {marker_name}:{run_key}")
                    handle.write(json.dumps(marker, ensure_ascii=False) + "\n")
                    handle.flush()
                    counts["marker"] += 1
                    acknowledgement = json.dumps(
                        {
                            "type": "marker_ack",
                            "event": marker.get("event"),
                            "run_key": marker.get("run_key"),
                            "collector_epoch_ns": marker["host_epoch_ns"],
                            "collector_monotonic_ns": marker["host_monotonic_ns"],
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")
                    marker_socket.sendto(acknowledgement, address)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    record_invalid("marker", packet, exc)

            received = serial_port.read(serial_port.in_waiting or 1)
            if not received:
                continue
            complete_lines, serial_pending = split_complete_lines(serial_pending, received)
            for raw in complete_lines:
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw.decode("utf-8").strip())
                    if not isinstance(value, dict):
                        raise ValueError("serial row must be an object")
                    value = add_host_time(value)
                    handle.write(json.dumps(value, ensure_ascii=False) + "\n")
                    if value.get("type") == "sample":
                        counts["sample"] += 1
                    elif value.get("type") == "environment":
                        counts["environment"] += 1
                    if counts["sample"] % 20 == 0:
                        handle.flush()
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    record_invalid("serial", raw, exc)

        if serial_pending.strip():
            # Ctrl+C can arrive after the first byte of the next NDJSON record.
            # This bounded tail is not evidence of link corruption: it never
            # formed a complete record and falls outside the already marked
            # query intervals. Preserve it for audit without invalidating the
            # complete serial rows collected before shutdown.
            counts["partial_serial_at_shutdown"] += 1
            shutdown_partial = add_host_time(
                {
                    "type": "collector_shutdown_partial",
                    "source": "serial",
                    "byte_length": len(serial_pending),
                    "preview_hex": serial_pending[:64].hex(),
                }
            )
            handle.write(json.dumps(shutdown_partial, ensure_ascii=False) + "\n")
            handle.flush()

    try:
        send("STOP")
    finally:
        serial_port.close()
        marker_socket.close()
    print(json.dumps({"output": str(args.output), **counts}, ensure_ascii=False))
    return 0 if counts["sample"] > 0 and counts["invalid"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
