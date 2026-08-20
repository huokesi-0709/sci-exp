from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def review(
    evidence_ids: list[str],
    risk_level: int,
    should_fallback: bool,
    notes: str,
) -> dict[str, Any]:
    return {
        "evidence_ids": evidence_ids,
        "risk_level": risk_level,
        "should_fallback": should_fallback,
        "notes": notes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将补充权威来源后的第二轮双审与仲裁决定写回先导决定文件。"
    )
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--chunks", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    decision_path = Path(args.decisions).resolve()
    candidate_rows = read_jsonl(Path(args.candidates).resolve())
    chunk_rows = read_jsonl(Path(args.chunks).resolve())
    data = json.loads(decision_path.read_text(encoding="utf-8"))

    candidate_ids = {str(row["query_id"]) for row in candidate_rows}
    evidence_ids = {str(row["evidence_id"]) for row in chunk_rows}
    rows = {str(row["query_id"]): row for row in data["decisions"]}

    data["profiles"]["head_unclear"] = {
        "required_actions": [
            "询问是否头部受击、意识异常及症状是否加重",
            "若确认头部外伤，避免随意搬动",
            "出现昏迷、频繁呕吐或症状加重时立即拨打120",
            "求救时准确报告位置和主要情况",
        ],
        "prohibited_actions": [
            "在信息不足时给出确定性诊断",
            "把地震避险条款当作头部损伤处置",
            "对疑似颅脑损伤者随意搬动",
        ],
    }
    data["profiles"]["hypothermia_unclear"] = {
        "required_actions": [
            "在环境安全时转移至温暖处并更换湿衣物",
            "询问湿冷暴露、发抖、意识和活动情况",
            "出现意识异常、呼吸心跳异常等表现时立即拨打120",
        ],
        "prohibited_actions": [
            "把寒潮预警阈值当作个人失温诊断",
            "仅因否认缺水而忽略低温风险",
            "给意识异常者喂水或酒精饮品",
        ],
    }
    data["profiles"]["dehydration_unspecified"] = {
        "required_actions": [
            "询问是否被困、缺水时长和身体状态",
            "确认可用的安全饮水与救援渠道",
            "仅把烧开水、瓶装水或救灾指挥部认可饮水作为安全候选",
        ],
        "prohibited_actions": [
            "建议饮用生水、来源不明或受污染的水",
            "在场景不明时给出确定性摄入量建议",
        ],
    }
    data["profiles"]["psychological_unspecified"] = {
        "required_actions": [
            "以倾听、接纳和不评判方式回应",
            "用简短问题确认是否存在即时人身危险",
            "如有危险，建议立即联系现场人员、紧急服务或权威援助",
        ],
        "prohibited_actions": [
            "进行心理诊断",
            "忽略可能存在的自伤风险或现场危险",
            "用说教或否定方式压制情绪表达",
        ],
    }
    data["profiles"]["respiratory_low_battery"] = {
        "required_actions": [
            "立即拨打120并优先报告位置和呼吸困难情况",
            "一次性传达烟尘暴露、被困情况和剩余电量",
            "减少非必要交互并使用现场可用的备用通信或求救信号",
        ],
        "prohibited_actions": [
            "因低电量延误紧急呼救",
            "进行冗长多轮对话",
            "把烟尘导致的呼吸困难当作气道异物实施腹部冲击法",
        ],
    }

    n50 = "NHC_HEALTH_LITERACY_2024_CURATED_V01_p050_001"
    n55 = "NHC_HEALTH_LITERACY_2024_CURATED_V01_p055_001"
    head = "SHQP_HEAD_TRAUMA_2018_CURATED_V01_head_injury_red_flags_001"
    hypo = "BJWJW_HYPOTHERMIA_2022_CURATED_V01_hypothermia_public_first_aid_001"
    crush = "BJWJW_CRUSH_INJURY_2019_CURATED_V01_crush_injury_public_response_001"
    water = "NHC_DISASTER_ENV_HEALTH_2019_CURATED_V01_p007_001"
    psyche6 = "NHC_PSYCHOLOGICAL_HOTLINE_2021_CURATED_V01_p006_001"
    psyche7 = "NHC_PSYCHOLOGICAL_HOTLINE_2021_CURATED_V01_p007_001"
    comm1 = (
        "MEM_FLOOD_PREPAREDNESS_2026_CURATED_V01_"
        "three_outages_preparedness_communication_001"
    )
    comm2 = (
        "MEM_FLOOD_PREPAREDNESS_2026_CURATED_V01_"
        "three_outages_preparedness_communication_002"
    )

    updates: dict[str, dict[str, Any]] = {
        "pilot_legacy_clean_0074": {
            "A": review(
                [n50],
                2,
                True,
                "未说明头部受击；专门头伤证据只能条件适用，先澄清受伤机制、意识和症状进展。",
            ),
            "B": review(
                [head, n50],
                2,
                True,
                "头晕想吐与头伤危险征象相似，但缺少外伤前提；保留条件证据并回退澄清。",
            ),
            "final": review(
                [n50],
                2,
                True,
                "仲裁不直接绑定头伤处置；先确认头部受击和意识状态，再决定是否采用专门证据。",
            ),
        },
        "pilot_legacy_clean_0078": {
            "A": review(
                [head, n50],
                2,
                False,
                "头部砸伤与明显眩晕满足专门头伤证据的适用前提，并由通用急症呼救条款补充升级条件。",
            ),
            "B": review(
                [head],
                2,
                False,
                "专门来源已覆盖头伤后危险征象和尽快就医，无需再以证据缺口为由回退。",
            ),
            "final": review(
                [head, n50],
                2,
                False,
                "仲裁通过直接安全回答：避免随意搬动、观察意识与呕吐等危险征象并及时求救。",
            ),
        },
        "pilot_legacy_clean_0092": {
            "A": review(
                [hypo],
                2,
                True,
                "低温症专门来源支持转移、干燥保暖和严重时呼救，但仍需确认湿冷暴露与意识状态。",
            ),
            "B": review(
                [hypo, "CMA_WARNING_SIGNALS_ORDER16_CURATED_V01_p014_001"],
                2,
                False,
                "专门急救来源与一般防寒条款共同支持先行保暖，可在回答中同步询问严重征象。",
            ),
            "final": review(
                [hypo],
                2,
                True,
                "仲裁保留专门证据并要求一次性澄清严重度；不把主观寒冷直接诊断为失温。",
            ),
        },
        "pilot_legacy_neg_0205": {
            "A": review(
                [hypo],
                2,
                True,
                "否认缺水不排除低温症；先按专门来源保暖并澄清意识、发抖和湿冷暴露。",
            ),
            "B": review(
                [hypo],
                2,
                True,
                "专门证据已补齐，但短句仍不足以判定严重度，保持条件性回退。",
            ),
            "final": review(
                [hypo],
                2,
                True,
                "一致采用低温症专门证据；禁止向意识异常者喂水，也不得因否认缺水而降级风险。",
            ),
        },
        "pilot_legacy_multi_0031": {
            "profile": "respiratory_low_battery",
            "A": review(
                [n50, comm1],
                3,
                False,
                "呼吸困难优先立即呼救；三断通信证据支持减少交互并准备备用联络方式。",
            ),
            "B": review(
                [n50],
                3,
                False,
                "医学急症证据足以决定主路径，低电量作为配置约束而非风险降级理由。",
            ),
            "final": review(
                [n50, comm1],
                3,
                False,
                "仲裁保留医疗与通信两类证据：一次性报告位置和症状，随后减少非必要交互。",
            ),
        },
        "pilot_legacy_clean_0137": {
            "A": review(
                [n55, water],
                2,
                True,
                "被困条款支持求救和保存体力，饮水指南只支持排除生水和不明水源；灾种仍需澄清。",
            ),
            "B": review(
                [n55],
                2,
                True,
                "被困证据可条件适用，但现有信息不足以判断可用水源或给出摄入建议。",
            ),
            "final": review(
                [n55, water],
                2,
                True,
                "仲裁采用部分证据并回退澄清；允许提示节约安全饮水，禁止建议饮用来源不明液体。",
            ),
        },
        "pilot_legacy_clean_0067": {
            "A": review(
                [crush, n50],
                3,
                True,
                "挤压伤专门来源已补齐，但受压时长和现场稳定性未知，仍应立即联系专业救援。",
            ),
            "B": review(
                [crush],
                3,
                True,
                "专门来源说明长时间受压可能严重；在时长不明时不自动输出强行移物指令。",
            ),
            "final": review(
                [crush, n50],
                3,
                True,
                "仲裁采用专门挤压伤与紧急呼救证据，保持专业救援回退并禁止自行强行移物。",
            ),
        },
        "pilot_legacy_clean_0071": {
            "A": review(
                [crush, n50],
                3,
                True,
                "已持续受压，挤压综合征风险不能仅凭无外伤排除，应报告持续时间并等待专业救援。",
            ),
            "B": review(
                [crush],
                3,
                True,
                "专门来源直接覆盖长时间受压与及时送医，仍需避免自行强行解除重压。",
            ),
            "final": review(
                [crush, n50],
                3,
                True,
                "一致采用挤压伤专门证据并转专业救援；不得拖拽或现场复位受压肢体。",
            ),
        },
        "pilot_legacy_clean_0132": {
            "A": review(
                [water],
                1,
                True,
                "饮水安全来源可排除生水和污染水，但缺少被困时长、症状和可用水源。",
            ),
            "B": review(
                [water],
                1,
                True,
                "证据足以约束水源安全，不足以给出确定摄入量或取得水的方法。",
            ),
            "final": review(
                [water],
                1,
                True,
                "一致采用饮水安全证据并回退澄清；只确认安全水源，不建议不明液体。",
            ),
        },
        "pilot_legacy_clean_0102": {
            "A": review(
                [psyche6],
                1,
                True,
                "支持性倾听证据已补齐，但仍建议先用简短问题确认即时危险。",
            ),
            "B": review(
                [psyche6, psyche7],
                1,
                False,
                "倾听、接纳、稳定和聚焦足以形成非诊断性的支持性回答，并可同步做安全确认。",
            ),
            "final": review(
                [psyche6, psyche7],
                1,
                False,
                "仲裁允许直接支持性回应，同时进行一次简短安全确认；禁止心理诊断或说教。",
            ),
        },
        "pilot_legacy_clean_0139": {
            "A": review(
                [comm1],
                0,
                True,
                "三断来源支持备用通信和物资准备，但单独低电量仍需先确认是否存在应急危险。",
            ),
            "B": review(
                [comm1, comm2],
                0,
                True,
                "可用多渠道通信证据约束简短交互；没有应急情境时不触发灾害处置。",
            ),
            "final": review(
                [comm1],
                0,
                True,
                "仲裁将低电量作为配置约束：一次简短确认危险，优先报位置并减少非必要交互。",
            ),
        },
    }

    missing_queries = set(updates) - candidate_ids
    if missing_queries:
        raise ValueError(f"候选集中缺少查询：{sorted(missing_queries)}")

    for query_id, update in updates.items():
        row = rows[query_id]
        if "profile" in update:
            row["profile"] = update["profile"]
        for role in ("A", "B", "final"):
            row[role] = update[role]
            missing_evidence = set(row[role]["evidence_ids"]) - evidence_ids
            if missing_evidence:
                raise ValueError(
                    f"{query_id}:{role} 缺少证据：{sorted(missing_evidence)}"
                )

    decision_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "reviewed_queries": len(updates),
                "total_queries": len(data["decisions"]),
                "decision_file": str(decision_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
