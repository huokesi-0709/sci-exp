from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Sequence


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def validate_run_id(value: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "run_id只能包含字母、数字、下划线、点、冒号和连字符，长度1到80"
        )
    return value


@dataclass(frozen=True)
class ExchangeResult:
    request: str
    response: str
    rtt_ms: float


class Esp32PowerSync:
    def __init__(
        self,
        device: str = "/dev/ttyS2",
        baud: int = 115200,
        timeout: float = 2.0,
    ) -> None:
        self.device = device
        self.baud = baud
        self.timeout = timeout
        self._serial = None

    def __enter__(self) -> "Esp32PowerSync":
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "缺少pyserial；在Radxa项目环境执行: pip install -e '.[hardware]'"
            ) from exc
        self._serial = serial.Serial(
            port=self.device,
            baudrate=self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
            write_timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def exchange(self, request: str, expected: str) -> ExchangeResult:
        if self._serial is None:
            raise RuntimeError("UART尚未打开")
        started = time.perf_counter()
        self._serial.write((request + "\n").encode("ascii"))
        self._serial.flush()
        deadline = started + self.timeout
        received: list[str] = []
        while time.perf_counter() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue
            try:
                line = raw.decode("ascii").strip()
            except UnicodeDecodeError:
                continue
            if not line:
                continue
            received.append(line)
            if line == expected:
                return ExchangeResult(
                    request=request,
                    response=line,
                    rtt_ms=(time.perf_counter() - started) * 1000.0,
                )
            if line.startswith("ERROR,"):
                raise RuntimeError(f"ESP32拒绝命令: {line}")
        detail = ", ".join(received) if received else "没有收到任何响应"
        raise TimeoutError(
            f"等待 {expected!r} 超时（{self.timeout:.3f}s）；已收到: {detail}"
        )

    def hello(self) -> ExchangeResult:
        return self.exchange("HELLO", "ACK,HELLO")

    def arm(self, run_id: str) -> ExchangeResult:
        validate_run_id(run_id)
        return self.exchange(f"ARM,{run_id}", f"READY,{run_id}")

    def start(self, run_id: str) -> ExchangeResult:
        validate_run_id(run_id)
        return self.exchange(f"START,{run_id}", f"ACK_START,{run_id}")

    def stop(self, run_id: str) -> ExchangeResult:
        validate_run_id(run_id)
        return self.exchange(f"STOP,{run_id}", f"DONE,{run_id}")


def result_dict(value: ExchangeResult) -> dict[str, object]:
    return {
        "request": value.request,
        "response": value.response,
        "rtt_ms": value.rtt_ms,
    }


def print_result(value: ExchangeResult) -> None:
    print(json.dumps(result_dict(value), ensure_ascii=False))


def run_wrapped_command(
    client: Esp32PowerSync,
    run_id: str,
    command: Sequence[str],
) -> int:
    if not command:
        raise ValueError("run子命令需要在 -- 后提供要执行的命令")
    arm = client.arm(run_id)
    start = client.start(run_id)
    command_started_ns = time.time_ns()
    completed: subprocess.CompletedProcess[bytes] | None = None
    stop: ExchangeResult | None = None
    try:
        completed = subprocess.run(list(command), check=False)
    finally:
        stop = client.stop(run_id)
    report = {
        "schema": "ina226-uart-wrapped-run-v1.0",
        "run_id": run_id,
        "command": list(command),
        "command_started_epoch_ns": command_started_ns,
        "returncode": completed.returncode if completed is not None else None,
        "arm": result_dict(arm),
        "start": result_dict(start),
        "stop": result_dict(stop),
    }
    print(json.dumps(report, ensure_ascii=False))
    return completed.returncode if completed is not None else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Radxa ZERO 3W通过UART控制ESP32-S3 INA226实验边界"
    )
    parser.add_argument("--device", default="/dev/ttyS2")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=2.0)
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("hello", help="验证UART双向通信")
    for action in ("arm", "start", "stop"):
        command_parser = subparsers.add_parser(action)
        command_parser.add_argument("--run-id", required=True, type=validate_run_id)

    run_parser = subparsers.add_parser(
        "run", help="ARM/START后执行命令，并在命令结束时STOP"
    )
    run_parser.add_argument("--run-id", required=True, type=validate_run_id)
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with Esp32PowerSync(args.device, args.baud, args.timeout) as client:
            if args.action == "hello":
                print_result(client.hello())
                return 0
            if args.action == "arm":
                print_result(client.arm(args.run_id))
                return 0
            if args.action == "start":
                print_result(client.start(args.run_id))
                return 0
            if args.action == "stop":
                print_result(client.stop(args.run_id))
                return 0
            command = list(args.command)
            if command and command[0] == "--":
                command = command[1:]
            return run_wrapped_command(client, args.run_id, command)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
