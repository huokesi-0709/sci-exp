from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "source_id",
    "标题",
    "来源机构",
    "来源页面",
    "实际下载地址",
    "本地SHA256",
    "来源类型",
    "正文中观察到的许可声明",
    "许可证据URL",
    "再分发决定",
    "版本日期证据",
    "允许范围",
    "待完成核验",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="建立权威来源许可、再分发和版本核验表。"
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def source_type(source: dict[str, Any]) -> str:
    org = str(source["source_org"])
    if "WHO" in org or "World Health" in org:
        return "international_publication"
    if "下载镜像" in org or source["download_url"] != source["source_url"]:
        return "official_page_with_mirror"
    return "government_web_or_publication"


def main() -> int:
    args = parse_args()
    registry = read_jsonl(Path(args.registry).resolve())
    review_rows = {
        str(row["source_id"]): row
        for row in read_csv(Path(args.review).resolve())
    }
    output_path = Path(args.output).resolve()
    known_licenses = {
        "WHO_ICRC_BEC_2018": (
            "CC BY-NC-SA 3.0 IGO",
            "https://www.who.int/publications/i/item/9789241513081",
            "conditional_noncommercial_attribution_sharealike",
        ),
        "WHO_PFA_2011": (
            "CC BY-NC-SA 3.0 IGO",
            "https://www.who.int/publications/i/item/9789241548205",
            "conditional_noncommercial_attribution_sharealike",
        ),
    }

    rows: list[dict[str, str]] = []
    for source in registry:
        source_id = str(source["source_id"])
        review = review_rows[source_id]
        scope = review["最终状态"]
        license_name, license_url, redistribution = known_licenses.get(
            source_id,
            (
                "未在本地正文或登记页核验到明确许可声明",
                "",
                "blocked_pending_manual_confirmation",
            ),
        )
        if scope == "excluded_from_direct_retrieval":
            allowed_scope = "不进入中文公众直接检索；仅保留标注参考"
        else:
            allowed_scope = "仅进入登记的章节/页码派生候选"

        rows.append(
            {
                "source_id": source_id,
                "标题": str(source["title"]),
                "来源机构": str(source["source_org"]),
                "来源页面": str(source["source_url"]),
                "实际下载地址": str(source["download_url"]),
                "本地SHA256": str(source["file_sha256"]),
                "来源类型": source_type(source),
                "正文中观察到的许可声明": license_name,
                "许可证据URL": license_url,
                "再分发决定": redistribution,
                "版本日期证据": (
                    f"登记版本={source.get('version', '')}; "
                    f"生效日期={source.get('effective_date', '')}; "
                    "仍需回到官方发布页核对"
                ),
                "允许范围": allowed_scope,
                "待完成核验": (
                    "记录署名、非商业、相同方式共享和WHO标识限制；"
                    "确认版本有效性"
                    if license_url
                    else "确认官方版权/开放许可、镜像再分发授权、引用要求；"
                    "确认版本有效性后才能解除blocked"
                ),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "conditional_license_rows": sum(
                    row["再分发决定"]
                    == "conditional_noncommercial_attribution_sharealike"
                    for row in rows
                ),
                "blocked_pending_manual_confirmation": sum(
                    row["再分发决定"]
                    == "blocked_pending_manual_confirmation"
                    for row in rows
                ),
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
