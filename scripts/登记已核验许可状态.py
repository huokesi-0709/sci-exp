from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


KNOWN_LICENSES = {
    "WHO_ICRC_BEC_2018": {
        "license_status": "verified_conditional_cc_by_nc_sa_3_0_igo",
        "redistribution_status": (
            "conditional_noncommercial_attribution_sharealike"
        ),
        "license_evidence_url": (
            "https://www.who.int/publications/i/item/9789241513081"
        ),
        "license_evidence_date": "2026-07-28",
    },
    "WHO_PFA_2011": {
        "license_status": "verified_conditional_cc_by_nc_sa_3_0_igo",
        "redistribution_status": (
            "conditional_noncommercial_attribution_sharealike"
        ),
        "license_evidence_url": (
            "https://www.who.int/publications/i/item/9789241548205"
        ),
        "license_evidence_date": "2026-07-28",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="登记已从官方出版物页面核验的许可状态。"
    )
    parser.add_argument("--registry", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.registry).resolve()
    rows: list[dict[str, Any]] = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    updated = 0
    for row in rows:
        source_id = str(row["source_id"])
        if source_id not in KNOWN_LICENSES:
            continue
        row.update(KNOWN_LICENSES[source_id])
        updated += 1

    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {"registry_rows": len(rows), "updated_license_rows": updated},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
