from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: JSON格式错误") from exc
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用下载审计报告回填协议登记表中的文件SHA-256。"
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry).resolve()
    report_path = Path(args.report).resolve()
    registry = read_jsonl(registry_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("failures"):
        raise ValueError("下载报告仍含失败项，拒绝回填哈希")

    reported = {
        str(row["source_id"]): str(row["sha256"])
        for row in report.get("results", [])
    }
    changed = 0
    for row in registry:
        source_id = str(row["source_id"])
        if source_id not in reported:
            raise ValueError(f"下载报告缺少来源：{source_id}")
        source_path = (registry_path.parent / str(row["file"])).resolve()
        actual = sha256_file(source_path)
        if actual != reported[source_id]:
            raise ValueError(f"{source_id}: 报告哈希与本地文件不一致")
        if row.get("file_sha256") != actual:
            row["file_sha256"] = actual
            changed += 1

    output = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in registry
    )
    registry_path.write_text(output, encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {"registry_rows": len(registry), "updated_hashes": changed},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
