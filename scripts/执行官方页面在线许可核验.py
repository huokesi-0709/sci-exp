from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
from pathlib import Path
from typing import Any


FIELDS = [
    "source_id",
    "来源页面",
    "实际下载地址",
    "官方页面HTTP状态",
    "官方页面标题",
    "官方页面Last-Modified",
    "官方页面明确许可证据",
    "官方页面版权/转载摘录",
    "镜像HTTP状态",
    "镜像Last-Modified",
    "镜像明确授权证据",
    "镜像授权摘录",
    "在线核验结论",
    "核验日期",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="在线读取登记的官方页面和镜像，形成许可证据审计记录。"
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-json", required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def curl(url: str, *, head: bool = False) -> tuple[str, str, str]:
    command = [
        "curl.exe",
        "-L",
        "--compressed",
        "-sS",
        "--max-time",
        "30",
        "-A",
        "Mozilla/5.0",
        "-D",
        "-",
    ]
    if head:
        command.append("-I")
    command.append(url)
    result = subprocess.run(
        command,
        capture_output=True,
        check=False,
    )
    payload = result.stdout.decode("utf-8", errors="replace")
    headers, _, body = payload.partition("\r\n\r\n")
    status_matches = re.findall(r"HTTP/\S+\s+(\d{3})", headers)
    status = status_matches[-1] if status_matches else "ERROR"
    last_modified = ""
    for line in headers.splitlines():
        if line.lower().startswith("last-modified:"):
            last_modified = line.split(":", 1)[1].strip()
    return status, last_modified, body


def page_evidence(body: str) -> tuple[str, str, str, str]:
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
    title = html.unescape(title_match.group(1)).strip() if title_match else ""
    plain = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<[^>]+>", " ", body)
    plain = re.sub(r"\s+", " ", html.unescape(plain)).strip()
    license_pattern = (
        r"(?is).{0,120}(CC BY|Creative Commons|开放许可|许可协议|再利用|"
        r"转载说明|明确授权|开放获取许可).{0,220}"
    )
    copyright_pattern = (
        r"(?is).{0,120}(版权所有|著作权|copyright|版权).{0,220}"
    )
    license_hits = [
        item.group(0).strip()
        for item in re.finditer(license_pattern, plain)
    ][:5]
    copyright_hits = [
        item.group(0).strip()
        for item in re.finditer(copyright_pattern, plain)
    ][:5]
    license_evidence = " || ".join(license_hits)
    copyright_evidence = " || ".join(copyright_hits)
    return title, license_evidence, copyright_evidence, plain


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry).resolve()
    rows = read_jsonl(registry_path)
    output_rows: list[dict[str, str]] = []
    for source in rows:
        source_id = str(source["source_id"])
        source_url = str(source["source_url"])
        download_url = str(source["download_url"])
        page_status, page_last_modified, page_body = curl(
            source_url,
            head=source_url.lower().endswith(".pdf"),
        )
        title, page_license, page_copyright, plain = page_evidence(page_body)
        mirror_status = ""
        mirror_last_modified = ""
        mirror_evidence = ""
        if download_url != source_url:
            mirror_status, mirror_last_modified, mirror_body = curl(
                download_url,
                head=download_url.lower().endswith(".pdf"),
            )
            _, mirror_license, _, _ = page_evidence(mirror_body)
            mirror_evidence = mirror_license
        conclusion = (
            "页面可访问但未发现明确许可或再分发条款"
            if page_status == "200" and not page_license
            else "发现页面许可证据，需人工核对条款"
            if page_license
            else "官方页面访问受限或失败"
        )
        output_rows.append(
            {
                "source_id": source_id,
                "来源页面": source_url,
                "实际下载地址": download_url,
                "官方页面HTTP状态": page_status,
                "官方页面标题": title,
                "官方页面Last-Modified": page_last_modified,
                "官方页面明确许可证据": (
                    "是" if page_license else "否"
                ),
                "官方页面版权/转载摘录": (
                    "许可摘录：" + page_license if page_license else ""
                )
                + (" 版权摘录：" + page_copyright if page_copyright else ""),
                "镜像HTTP状态": mirror_status,
                "镜像Last-Modified": mirror_last_modified,
                "镜像明确授权证据": "是" if mirror_evidence else "否",
                "镜像授权摘录": mirror_evidence,
                "在线核验结论": conclusion,
                "核验日期": "2026-07-28",
            }
        )

    output_csv = Path(args.output_csv).resolve()
    output_json = Path(args.output_json).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)
    output_json.write_text(
        json.dumps(
            {
                "record_count": len(output_rows),
                "accessible_official_pages": sum(
                    row["官方页面HTTP状态"] == "200"
                    for row in output_rows
                ),
                "official_pages_with_explicit_license": sum(
                    row["官方页面明确许可证据"] == "是"
                    for row in output_rows
                ),
                "mirror_pages_with_explicit_authorization": sum(
                    row["镜像明确授权证据"] == "是"
                    for row in output_rows
                ),
                "rows": output_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "record_count": len(output_rows),
                "accessible_official_pages": sum(
                    row["官方页面HTTP状态"] == "200"
                    for row in output_rows
                ),
                "official_pages_with_explicit_license": sum(
                    row["官方页面明确许可证据"] == "是"
                    for row in output_rows
                ),
                "output_csv": str(output_csv),
                "output_json": str(output_json),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
