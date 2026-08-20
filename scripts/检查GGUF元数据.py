#!/usr/bin/env python3
"""仅使用Python标准库读取GGUF头部与键值元数据。"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import BinaryIO, Any


SCALARS: dict[int, str] = {
    0: "<B",
    1: "<b",
    2: "<H",
    3: "<h",
    4: "<I",
    5: "<i",
    6: "<f",
    7: "<?",
    10: "<Q",
    11: "<q",
    12: "<d",
}


def read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise EOFError(f"GGUF提前结束：需要{size}字节，实际读取{len(data)}字节")
    return data


def read_scalar(stream: BinaryIO, value_type: int) -> Any:
    if value_type not in SCALARS:
        raise ValueError(f"不支持的GGUF标量类型：{value_type}")
    fmt = SCALARS[value_type]
    return struct.unpack(fmt, read_exact(stream, struct.calcsize(fmt)))[0]


def read_string(stream: BinaryIO) -> str:
    length = struct.unpack("<Q", read_exact(stream, 8))[0]
    return read_exact(stream, length).decode("utf-8", errors="replace")


def read_value(stream: BinaryIO, value_type: int) -> Any:
    if value_type == 8:
        return read_string(stream)
    if value_type == 9:
        element_type = struct.unpack("<I", read_exact(stream, 4))[0]
        length = struct.unpack("<Q", read_exact(stream, 8))[0]
        values = [read_value(stream, element_type) for _ in range(length)]
        return values
    return read_scalar(stream, value_type)


def read_metadata(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        magic = read_exact(stream, 4)
        if magic != b"GGUF":
            raise ValueError(f"不是GGUF文件：magic={magic!r}")
        version = struct.unpack("<I", read_exact(stream, 4))[0]
        tensor_count = struct.unpack("<Q", read_exact(stream, 8))[0]
        metadata_count = struct.unpack("<Q", read_exact(stream, 8))[0]
        metadata: dict[str, Any] = {}
        for _ in range(metadata_count):
            key = read_string(stream)
            value_type = struct.unpack("<I", read_exact(stream, 4))[0]
            metadata[key] = read_value(stream, value_type)
    return {
        "path": str(path.resolve()),
        "file_size_bytes": path.stat().st_size,
        "gguf_version": version,
        "tensor_count": tensor_count,
        "metadata_count": metadata_count,
        "metadata": metadata,
    }


def summarize_large_arrays(value: Any, limit: int = 16) -> Any:
    if isinstance(value, dict):
        return {key: summarize_large_arrays(item, limit) for key, item in value.items()}
    if isinstance(value, list) and len(value) > limit:
        return {
            "array_length": len(value),
            "first_values": [
                summarize_large_arrays(item, limit) for item in value[:limit]
            ],
        }
    if isinstance(value, list):
        return [summarize_large_arrays(item, limit) for item in value]
    return value


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gguf", type=Path, help="待检查的GGUF文件")
    parser.add_argument("--output", type=Path, help="可选JSON输出路径")
    args = parser.parse_args()

    result = read_metadata(args.gguf)
    rendered = json.dumps(summarize_large_arrays(result), ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
