from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把在线页面状态回填到许可与版本核验表，但不自动解除blocked。"
    )
    parser.add_argument("--table", required=True)
    parser.add_argument("--online", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parse_args()
    table_path = Path(args.table).resolve()
    online_path = Path(args.online).resolve()
    output_path = Path(args.output).resolve()
    rows = read_csv(table_path)
    online = {
        row["source_id"]: row for row in read_csv(online_path)
    }
    extra_fields = [
        "在线核验日期",
        "官方页面HTTP状态",
        "官方页面标题",
        "官方页面Last-Modified",
        "官方页面明确许可证据",
        "镜像HTTP状态",
        "镜像Last-Modified",
        "镜像明确授权证据",
        "在线核验结论",
        "在线版本证据",
    ]
    for row in rows:
        result = online.get(row["source_id"], {})
        row["在线核验日期"] = result.get("核验日期", "")
        row["官方页面HTTP状态"] = result.get("官方页面HTTP状态", "")
        row["官方页面标题"] = result.get("官方页面标题", "")
        row["官方页面Last-Modified"] = result.get("官方页面Last-Modified", "")
        row["官方页面明确许可证据"] = result.get("官方页面明确许可证据", "")
        row["镜像HTTP状态"] = result.get("镜像HTTP状态", "")
        row["镜像Last-Modified"] = result.get("镜像Last-Modified", "")
        row["镜像明确授权证据"] = result.get("镜像明确授权证据", "")
        row["在线核验结论"] = result.get("在线核验结论", "")
        row["在线版本证据"] = (
            f"登记版本日期证据：{row.get('版本日期证据', '')}；"
            f"官方页面HTTP={result.get('官方页面HTTP状态', '') or '未获取'}；"
            f"官方Last-Modified={result.get('官方页面Last-Modified', '') or '未提供'}；"
            f"页面标题={result.get('官方页面标题', '') or '未获取'}；"
            f"结论={result.get('在线核验结论', '') or '未记录'}"
        )
        note = (
            f"在线核验({result.get('核验日期', '')})：官方HTTP="
            f"{result.get('官方页面HTTP状态', '') or '未获取'}; "
            f"官方明确许可={result.get('官方页面明确许可证据', '否')}; "
            f"镜像HTTP={result.get('镜像HTTP状态', '') or '无'}; "
            f"镜像明确授权={result.get('镜像明确授权证据', '否')}; "
            f"结论={result.get('在线核验结论', '') or '未记录'}。"
        )
        existing = row.get("待完成核验", "")
        row["待完成核验"] = f"{existing} {note}".strip()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = list(rows[0])
        for field in extra_fields:
            if field not in fieldnames:
                fieldnames.append(field)
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"rows={len(rows)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
