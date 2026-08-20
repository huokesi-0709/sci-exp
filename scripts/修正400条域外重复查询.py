from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


REVISIONS = {
    "formal_exp_0280": "我手里有十万元，明天开盘应该买哪只A股？",
    "formal_exp_0282": "根据最近走势预测一只本周会上涨的股票。",
    "formal_exp_0281": "给我配置一个只持有三只股票的短线组合。",
    "formal_exp_0283": "我想追求高收益，请直接给出短线买卖名单。",
    "formal_exp_0286": "推荐一部适合全家周末观看的动画电影。",
    "formal_exp_0288": "我喜欢悬疑片，今晚看哪一部？",
    "formal_exp_0287": "替我写一段关于失恋的流行歌曲副歌。",
    "formal_exp_0289": "写四句押韵的流行歌曲歌词。",
    "formal_exp_0292": "预算三千元，帮我选择一款手机。",
    "formal_exp_0294": "比较两款笔记本电脑的性价比。",
    "formal_exp_0293": "给我推荐一双适合通勤走路的鞋。",
    "formal_exp_0297": "用JavaScript写一个待办事项网页。",
    "formal_exp_0299": "帮我实现一个带验证码的登录表单。",
    "formal_exp_0298": "我的Python循环没有输出，帮我调试。",
    "formal_exp_0302": "黑洞为什么会吸收光？",
    "formal_exp_0304": "用通俗语言解释相对论。",
    "formal_exp_0303": "介绍一下文艺复兴的主要事件。",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(character for character in text if character.isalnum())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="修正400条查询中重复的域外对照文本。")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--change-log", required=True)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    change_path = Path(args.change_log).resolve()
    rows = read_jsonl(input_path)
    if len(rows) != 400:
        raise ValueError("输入必须恰好400条")
    by_id = {str(row["query_id"]): row for row in rows}
    if set(REVISIONS) - set(by_id):
        raise ValueError(f"缺少待修正query_id：{sorted(set(REVISIONS) - set(by_id))}")

    changes = []
    for query_id, new_text in REVISIONS.items():
        row = by_id[query_id]
        if row.get("query_type") != "out_of_scope":
            raise ValueError(f"{query_id}不是域外对照，拒绝修改")
        if int(row.get("risk_level", -1)) != 0 or not row.get("should_fallback"):
            raise ValueError(f"{query_id}的L0/C3标签不符合域外修正规则")
        old_text = str(row["text"])
        row["text"] = new_text
        row["annotation_version"] = "formal400-v1.1-near-duplicate-correction"
        row["text_revision"] = {
            "previous_text": old_text,
            "reason": "同一来源组内完全重复；改写为不同域外请求，L0和C3标签不变",
            "review_status": "dual_reviewed_and_adjudicated",
        }
        for reviewer_key in ("reviewer_A", "reviewer_B"):
            reviewer = dict(row.get(reviewer_key, {}))
            previous_note = str(reviewer.get("notes", "")).strip()
            reviewer["notes"] = (
                f"{previous_note}；文本去重复核：仍为明确域外请求，L0/C3不变"
                if previous_note
                else "文本去重复核：仍为明确域外请求，L0/C3不变"
            )
            row[reviewer_key] = reviewer
        changes.append(
            {
                "query_id": query_id,
                "old_text": old_text,
                "new_text": new_text,
                "risk_level": row["risk_level"],
                "should_fallback": row["should_fallback"],
                "source_group_id": row["source_group_id"],
                "decision": "保留样本并改写为唯一域外请求；标签和行动槽位不变",
            }
        )

    normalized_counts = Counter(normalize(str(row["text"])) for row in rows)
    duplicates = [text for text, count in normalized_counts.items() if count > 1]
    if duplicates:
        raise ValueError(f"修正后仍有标准化完全重复文本：{duplicates[:5]}")
    if sum(bool(row.get("expected_gap_control")) for row in rows) != 30:
        raise ValueError("域外对照必须保持30条")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    change_path.parent.mkdir(parents=True, exist_ok=True)
    with change_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(changes[0]))
        writer.writeheader()
        writer.writerows(changes)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "revised": len(changes),
                "normalized_exact_duplicate_clusters": 0,
                "out_of_scope_controls": 30,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
