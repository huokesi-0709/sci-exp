from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


APPROVED_SCOPE = {
    "excluded_from_direct_retrieval",
    "scope_adjudicated_pending_license",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查正式协议库生成与Radxa主实验冻结门槛。"
    )
    parser.add_argument("--sci-exp-root", required=True)
    parser.add_argument(
        "--license-table",
        default="",
        help="许可与版本核验表；未提供时优先读取最新v1.0并依次回退",
    )
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.sci_exp_root).resolve()
    registry_path = root / "data/raw/protocols/协议来源登记_v0.1.jsonl"
    if args.license_table:
        license_path = Path(args.license_table).resolve()
    else:
        candidates = [
            root / "data/annotations/许可与版本核验表_v1.0.csv",
            root / "data/annotations/许可与版本核验表_v0.3.csv",
            root / "data/annotations/许可与版本核验表_v0.2.csv",
            root / "data/annotations/许可与版本核验表_v0.1.csv",
        ]
        license_path = next(path for path in candidates if path.is_file())
    review_path = root / "data/annotations/协议内容审查表_v0.1.csv"

    registry = read_jsonl(registry_path)
    licenses = {
        row["source_id"]: row for row in read_csv(license_path)
    }
    reviews = {
        row["source_id"]: row for row in read_csv(review_path)
    }

    source_checks: list[dict[str, Any]] = []
    for source in registry:
        source_id = str(source["source_id"])
        file_path = root / "data/raw/protocols" / str(source["file"])
        license_row = licenses.get(source_id, {})
        review_row = reviews.get(source_id, {})
        file_exists = file_path.is_file()
        actual_hash = sha256(file_path) if file_exists else ""
        hash_ok = file_exists and actual_hash == source.get("file_sha256", "")
        if "内部正式实验资格" in license_row:
            license_ok = license_row.get("内部正式实验资格") == "true"
            public_redistribution_ok = (
                license_row.get("公开再分发资格") == "true"
            )
            version_ok = license_row.get("版本状态", "").startswith(
                "verified_"
            )
            disposition_ok = bool(license_row.get("正式库处置", ""))
        else:
            license_ok = license_row.get("再分发决定", "").startswith(
                "conditional_"
            ) or license_row.get("再分发决定", "") == "cleared_for_metadata_only"
            public_redistribution_ok = license_ok
            version_text = license_row.get("版本日期证据", "")
            version_ok = (
                bool(version_text)
                and "仍需回到官方发布页核对" not in version_text
            )
            disposition_ok = license_ok
        scope_ok = review_row.get("最终状态", "") in APPROVED_SCOPE
        source_checks.append(
            {
                "source_id": source_id,
                "file_exists": file_exists,
                "sha256_matches_registry": hash_ok,
                "internal_research_scope_cleared": license_ok,
                "public_redistribution_cleared": public_redistribution_ok,
                "formal_library_disposition_recorded": disposition_ok,
                "version_status_cleared": version_ok,
                "content_scope_adjudicated": scope_ok,
                "eligible_for_formal_library": all(
                    [
                        file_exists,
                        hash_ok,
                        license_ok,
                        disposition_ok,
                        version_ok,
                        scope_ok,
                    ]
                ),
            }
        )

    criteria = {
        "all_source_files_present": all(
            item["file_exists"] for item in source_checks
        ),
        "all_source_hashes_match": all(
            item["sha256_matches_registry"] for item in source_checks
        ),
        "all_internal_research_scopes_cleared": all(
            item["internal_research_scope_cleared"] for item in source_checks
        ),
        "all_formal_library_dispositions_recorded": all(
            item["formal_library_disposition_recorded"]
            for item in source_checks
        ),
        "all_versions_cleared": all(
            item["version_status_cleared"] for item in source_checks
        ),
        "all_content_scopes_adjudicated": all(
            item["content_scope_adjudicated"] for item in source_checks
        ),
    }
    formal_freeze = all(criteria.values())
    public_redistribution_eligible = all(
        item["public_redistribution_cleared"] for item in source_checks
    )
    report = {
        "report_version": "v1.0",
        "generated_at": "2026-07-28",
        "freeze_scope": (
            "local_noncommercial_scientific_research_no_republication"
        ),
        "formal_library_freeze": formal_freeze,
        "formal_training_eligible": formal_freeze,
        "radxa_main_experiment_eligible": formal_freeze,
        "public_redistribution_eligible": public_redistribution_eligible,
        "criteria": criteria,
        "source_count": len(source_checks),
        "eligible_source_count": sum(
            item["eligible_for_formal_library"] for item in source_checks
        ),
        "blocked_source_ids": [
            item["source_id"]
            for item in source_checks
            if not item["eligible_for_formal_library"]
        ],
        "source_checks": source_checks,
        "interpretation": (
            "当前仅允许本地研究副本、索引构建和设备联调；"
            "正式协议库、正式训练和论文主实验仍被冻结。"
            if not formal_freeze
            else (
                "内部非商业科学研究冻结条件满足，可生成受控正式协议库、"
                "正式标注和Radxa主实验输入；公开复现包仍必须按各来源的"
                "公开再分发资格排除受限正文和派生切块。"
            )
        ),
    }
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "formal_library_freeze": formal_freeze,
                "source_count": len(source_checks),
                "eligible_source_count": report["eligible_source_count"],
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
