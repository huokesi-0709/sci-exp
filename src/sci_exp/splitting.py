from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from .schemas import QueryRecord


DEFAULT_PROPORTIONS = {
    "train": 0.40,
    "valid": 0.10,
    "cal_op": 0.1333333333,
    "cal_ch": 0.0666666667,
    "test_op": 0.20,
    "test_ch": 0.10,
}


def group_split(
    queries: Iterable[QueryRecord],
    proportions: dict[str, float] | None = None,
    seed: int = 42,
) -> list[QueryRecord]:
    proportions = proportions or DEFAULT_PROPORTIONS
    total = sum(proportions.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"split proportions must sum to 1.0, got {total}")

    groups: dict[str, list[QueryRecord]] = defaultdict(list)
    for query in queries:
        groups[query.source_group_id].append(query)

    thresholds: list[tuple[str, float]] = []
    cumulative = 0.0
    for split_name, proportion in proportions.items():
        cumulative += proportion
        thresholds.append((split_name, cumulative))

    output: list[QueryRecord] = []
    for group_id in sorted(groups):
        digest = hashlib.sha256(f"{seed}:{group_id}".encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], "big") / 2**64
        split_name = thresholds[-1][0]
        for name, threshold in thresholds:
            if value < threshold:
                split_name = name
                break
        output.extend(replace(query, split=split_name) for query in groups[group_id])
    return output

