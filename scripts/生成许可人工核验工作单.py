from __future__ import annotations

import argparse
import csv
from pathlib import Path


FIELDS = [
    "source_id",
    "标题",
    "来源机构",
    "来源页面",
    "实际下载地址",
    "当前许可证状态",
    "当前再分发决定",
    "官方许可/版权证据URL",
    "官方许可/版权原文摘录",
    "镜像授权证据URL",
    "镜像授权原文摘录",
    "版本/生效证据URL",
    "版本/生效原文摘录",
    "更新机制或失效日期",
    "允许公开范围",
    "核验人",
    "核验日期",
    "核验结论",
    "备注",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从现有许可表生成逐来源人工核验工作单。"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    output_rows: list[dict[str, str]] = []
    for row in rows:
        output_rows.append(
            {
                "source_id": row["source_id"],
                "标题": row["标题"],
                "来源机构": row["来源机构"],
                "来源页面": row["来源页面"],
                "实际下载地址": row["实际下载地址"],
                "当前许可证状态": row["正文中观察到的许可声明"],
                "当前再分发决定": row["再分发决定"],
                "官方许可/版权证据URL": row["许可证据URL"],
                "官方许可/版权原文摘录": "",
                "镜像授权证据URL": "",
                "镜像授权原文摘录": "",
                "版本/生效证据URL": row["来源页面"],
                "版本/生效原文摘录": "",
                "更新机制或失效日期": "",
                "允许公开范围": row["允许范围"],
                "核验人": "",
                "核验日期": "",
                "核验结论": "待人工核验",
                "备注": row["待完成核验"],
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)
    print(
        f"generated={len(output_rows)} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
