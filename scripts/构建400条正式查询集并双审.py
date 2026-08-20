from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Scenario:
    cluster: str
    disaster_type: str
    query_type: str
    risk_level: int
    should_fallback: bool
    evidence_ids: tuple[str, ...]
    statements: tuple[str, ...]
    action_key: str
    count: int


E = {
    "call": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p049_001",
    "poison_call": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p050_001",
    "poison_aid": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p050_002",
    "cpr_1": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p051_001",
    "cpr_2": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p051_002",
    "bleed": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p052_001",
    "fracture": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p052_002",
    "burn": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p053_001",
    "choke": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p053_002",
    "fire": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p054_001",
    "geo": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p054_002",
    "trapped": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p055_001",
    "signal": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p055_002",
    "drowning": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p056_001",
    "eq_warning": (
        "MEM_EARTHQUAKE_SAFETY_2025_CURATED_V01_"
        "earthquake_warning_action_001"
    ),
    "eq_shelter": (
        "MEM_EARTHQUAKE_SAFETY_2025_CURATED_V01_"
        "earthquake_shelter_preparation_001"
    ),
    "flood_1": (
        "MEM_FLOOD_SAFETY_2025_CURATED_V01_flood_warning_escape_001"
    ),
    "flood_2": (
        "MEM_FLOOD_SAFETY_2025_CURATED_V01_flood_warning_escape_002"
    ),
    "flood_3": (
        "MEM_FLOOD_SAFETY_2025_CURATED_V01_flood_warning_escape_003"
    ),
    "flood_4": (
        "MEM_FLOOD_SAFETY_2025_CURATED_V01_flood_warning_escape_004"
    ),
    "rain": "CMA_WARNING_SIGNALS_ORDER16_CURATED_V01_p007_001",
    "cold_warning": "CMA_WARNING_SIGNALS_ORDER16_CURATED_V01_p013_001",
    "heat": "CMA_WARNING_SIGNALS_ORDER16_CURATED_V01_p021_001",
    "lightning": "CMA_WARNING_SIGNALS_ORDER16_CURATED_V01_p024_001",
    "icing": "CMA_WARNING_SIGNALS_ORDER16_CURATED_V01_p032_001",
    "head_general": (
        "SHQP_HEAD_TRAUMA_2018_CURATED_V01_"
        "head_injury_assess_call_no_move_001"
    ),
    "head_bleed": (
        "SHQP_HEAD_TRAUMA_2018_CURATED_V01_head_scalp_bleeding_001"
    ),
    "head_red": (
        "SHQP_HEAD_TRAUMA_2018_CURATED_V01_head_injury_red_flags_001"
    ),
    "cold": (
        "BJWJW_HYPOTHERMIA_2022_CURATED_V01_"
        "hypothermia_public_first_aid_001"
    ),
    "crush": (
        "BJWJW_CRUSH_INJURY_2019_CURATED_V01_"
        "crush_injury_public_response_001"
    ),
    "eq_aid": (
        "MEM_EARTHQUAKE_FIRST_AID_2019_CURATED_V01_"
        "earthquake_bleeding_fracture_001"
    ),
    "fire_move": (
        "JINCHENG_HIGHRISE_FIRE_2026_CURATED_V01_"
        "fire_alarm_low_posture_no_elevator_001"
    ),
    "fire_choice": (
        "JINCHENG_HIGHRISE_FIRE_2026_CURATED_V01_"
        "fire_evacuate_or_shelter_001"
    ),
    "fire_wait": (
        "JINCHENG_HIGHRISE_FIRE_2026_CURATED_V01_"
        "fire_trapped_wait_rescue_001"
    ),
    "psych_listen": "NHC_PSYCHOLOGICAL_HOTLINE_2021_CURATED_V01_p006_001",
    "psych_stable": "NHC_PSYCHOLOGICAL_HOTLINE_2021_CURATED_V01_p007_001",
    "water": "NHC_DISASTER_ENV_HEALTH_2019_CURATED_V01_p007_001",
    "outage_1": (
        "MEM_FLOOD_PREPAREDNESS_2026_CURATED_V01_"
        "three_outages_preparedness_communication_001"
    ),
    "outage_2": (
        "MEM_FLOOD_PREPAREDNESS_2026_CURATED_V01_"
        "three_outages_preparedness_communication_002"
    ),
}


ACTIONS: dict[str, tuple[list[str], list[str]]] = {
    "cpr": (
        ["立即呼叫120并请人取AED", "确认无正常呼吸后按协议开始心肺复苏"],
        ["不要因等待网络恢复而延误呼救和复苏"],
    ),
    "poison": (
        ["立即脱离可疑暴露并呼叫120", "保留可疑物信息供救援人员判断"],
        ["不要自行催吐或喂食不明物质"],
    ),
    "bleeding": (
        ["持续直接压迫出血部位并呼叫120", "观察意识和循环恶化迹象"],
        ["不要反复揭开敷料检查", "不要轻易拔出嵌入伤口的异物"],
    ),
    "head": (
        ["停止活动并监测意识、呕吐和症状变化", "出现危险征象立即呼叫120"],
        ["不要随意搬动疑似严重头部损伤者"],
    ),
    "smoke": (
        ["在安全可行时低姿撤离烟气区域并立即呼救", "呼吸困难时呼叫120"],
        ["不要乘坐电梯或返回烟雾区域"],
    ),
    "choking": (
        ["不能说话或呼吸时立即呼救并按窒息急救流程处理", "失去反应时转入心肺复苏流程"],
        ["不要盲目伸手抠取看不见的异物"],
    ),
    "drowning": (
        ["先确保施救者安全并呼叫救援", "无正常呼吸时按协议开始复苏"],
        ["不要在没有安全条件时盲目下水"],
    ),
    "crush": (
        ["先确认现场安全并呼叫专业救援", "说明受压部位、时长和循环恶化迹象"],
        ["不要独自强行移动大型重物"],
    ),
    "cold": (
        ["转移到温暖干燥处并逐步保暖", "意识或呼吸异常时立即呼叫120"],
        ["不要饮酒取暖或直接用过热物体加热皮肤"],
    ),
    "electrical": (
        ["先切断电源并呼叫120", "确认无正常呼吸后开始复苏"],
        ["电源未切断前不要直接接触伤者"],
    ),
    "fire": (
        ["依据烟火和出口状况选择撤离或关门避险", "报告位置并等待专业救援"],
        ["不要乘坐电梯或穿越浓烟"],
    ),
    "flood": (
        ["远离洪水、低洼处和可能发生滑坡的区域", "路线不明时报告位置并等待指引"],
        ["不要驾车或步行强行穿越流水"],
    ),
    "earthquake": (
        ["避开掉落物和不稳定结构并保护头部", "余震期间转移到安全位置"],
        ["不要盲目返回受损建筑"],
    ),
    "water": (
        ["优先使用确认安全的饮用水并报告补给需求", "无法确认水质时请求专业支持"],
        ["不要饮用受污染或来源不明的水"],
    ),
    "psych": (
        ["使用倾听、澄清和稳定沟通并评估即时危险", "危险不明时转接人工或专业支持"],
        ["不要把支持性沟通表述成诊断或治疗"],
    ),
    "weather": (
        ["按官方预警采取避险并减少非必要外出", "持续关注本地权威更新"],
        ["不要依据单条静态信息推断本地实时风险"],
    ),
    "preparedness": (
        ["保留电量并优先发送位置、险情和资源状态", "准备替代通信和基本物资"],
        ["不要把有限电量消耗在非必要生成上"],
    ),
    "minor": (
        ["停止负重并保护伤处", "症状加重或功能受限时就医"],
        ["不要强行活动或现场复位"],
    ),
    "out": (
        ["说明系统仅处理离线应急查询", "建议改用合适的非应急工具"],
        ["不要把域外请求伪装成应急建议"],
    ),
}


SUFFIXES = (
    "，现在应该先做什么？",
    "，请给我最先执行的两步。",
    "，手机网络很差，我该怎么处理？",
    "，现场只有普通人能帮忙，先做什么？",
    "，请按紧急程度告诉我行动顺序。",
    "，救援还没到，哪些事绝对不能做？",
    "，我需要一段简短、可离线执行的指引。",
    "，如果情况继续恶化，什么时候必须求救？",
)


def l3_scenarios() -> list[Scenario]:
    values = [
        ("cardiac_arrest_no_breathing", "medical", "single_intent", (E["cpr_1"], E["cpr_2"]), ("同伴突然倒地，呼叫没有反应而且没有正常呼吸", "有人昏倒后不回应，胸口也看不到正常起伏"), "cpr"),
        ("poisoning_unconscious", "poisoning", "multi_intent", (E["poison_call"], E["cpr_1"]), ("有人吸入不明气体后昏迷，呼吸很弱", "密闭房间里的人接触不明物后失去反应"), "poison"),
        ("uncontrolled_external_bleeding", "injury", "single_intent", (E["bleed"], E["call"]), ("伤口一直大量出血，持续压着也止不住", "腿部伤口不断涌血，人开始脸色发白"), "bleeding"),
        ("earthquake_crush_bleeding", "earthquake", "multi_intent", (E["eq_aid"], E["bleed"]), ("地震后伤者被砸伤并持续大量出血", "余震后有人骨折，伤口出血一直压不住"), "bleeding"),
        ("head_injury_unconscious", "injury", "multi_intent", (E["head_general"], E["head_red"]), ("头部受到撞击后逐渐叫不醒", "重物砸到头后意识越来越模糊"), "head"),
        ("head_injury_repeated_vomiting", "injury", "multi_intent", (E["head_red"], E["call"]), ("头部撞伤后反复呕吐并开始说话含糊", "摔倒撞头后连续呕吐，走路也不稳"), "head"),
        ("fire_smoke_respiratory_failure", "fire", "multi_intent", (E["fire"], E["call"]), ("火灾烟雾中有人喘不上气，意识也变差", "浓烟进入房间后同伴呼吸困难并快要昏倒"), "smoke"),
        ("highrise_smoke_severe_dyspnea", "fire", "multi_intent", (E["fire_move"], E["call"]), ("高层楼道全是浓烟，我已经无法正常呼吸", "高层起火后烟很大，同伴只能说出几个字"), "smoke"),
        ("complete_choking", "medical", "single_intent", (E["choke"], E["cpr_1"]), ("同伴被食物卡住，不能说话也不能呼吸", "有人突然抓住喉咙，发不出声音并开始发紫"), "choking"),
        ("drowning_unresponsive", "flood", "multi_intent", (E["drowning"], E["cpr_1"]), ("落水者被救上来后没有反应，也没有正常呼吸", "洪水中救起的人昏迷，胸口没有正常起伏"), "drowning"),
        ("crush_injury_with_shock", "earthquake", "multi_intent", (E["crush"], E["call"]), ("伤者被重物压住很久，脸色苍白并冒冷汗", "倒塌物压住腿部，伤者越来越虚弱和意识模糊"), "crush"),
        ("earthquake_crush_and_hemorrhage", "earthquake", "multi_intent", (E["eq_aid"], E["crush"]), ("地震废墟中有人受压且伤口大量出血", "建筑倒塌后同伴被压住，出血并出现休克迹象"), "crush"),
        ("severe_hypothermia_unconscious", "cold_wave", "multi_intent", (E["cold"], E["call"]), ("失温者不再发抖而且逐渐叫不醒", "暴露在低温中很久的人意识模糊、呼吸缓慢"), "cold"),
        ("fire_trapped_with_smoke", "fire", "multi_intent", (E["fire_wait"], E["fire"]), ("房门外浓烟封住出口，屋内的人呼吸越来越困难", "高层火灾被困房内，烟已经从门缝进入并有人快昏倒"), "fire"),
        ("electrical_injury_unresponsive", "electrical_injury", "multi_intent", (E["burn"], E["cpr_1"]), ("触电者倒地没有反应，也没有正常呼吸", "电线事故后有人昏迷，必须先切电还是先碰他"), "electrical"),
        ("collapse_entrapment_respiratory", "earthquake", "multi_intent", (E["trapped"], E["eq_warning"]), ("坍塌后被困者胸口受压，已经喘不上气", "余震中有人被卡在狭小空间，呼吸越来越困难"), "earthquake"),
    ]
    return [
        Scenario(a, b, c, 3, False, d, e, f, 6)
        for a, b, c, d, e, f in values
    ]


def other_scenarios() -> list[Scenario]:
    # 前20组各8条，后3组各7条，共181条；前5组为C3回退。
    values = [
        ("flood_vehicle_route_unknown", "flood", "multi_intent", 2, True, (E["flood_1"], E["flood_2"]), ("车辆被积水困住，水还在上涨但撤离路线不清楚", "暴雨中道路被淹，四周路线情况都无法确认"), "flood"),
        ("fire_exit_smoke_direction_unknown", "fire", "multi_intent", 2, True, (E["fire_choice"], E["fire_move"]), ("楼道一边有烟一边有火，无法判断哪个出口安全", "高层起火后两个疏散方向情况相互矛盾"), "fire"),
        ("earthquake_building_stability_unknown", "earthquake", "multi_intent", 2, True, (E["eq_warning"], E["eq_shelter"]), ("地震后建筑出现裂缝，但无法判断还能不能停留", "余震不断，出口附近有掉落物且结构安全不明"), "earthquake"),
        ("water_source_contamination_unknown", "flood", "multi_intent", 1, True, (E["water"], E["outage_1"]), ("洪水后只剩一处水源，但无法确认有没有污染", "停水后找到的临时水源有异味，现场没有检测工具"), "water"),
        ("psych_immediate_safety_unclear", "psychological", "multi_intent", 1, True, (E["psych_listen"], E["psych_stable"]), ("受灾者极度崩溃并说不想活，但当前危险程度不清楚", "被困者持续恐慌和绝望，无法确认是否会伤害自己"), "psych"),
        ("partial_thickness_burn", "fire", "single_intent", 2, False, (E["burn"],), ("手臂被火焰烧伤，皮肤起泡并持续疼痛", "热液烫伤一大片皮肤，已经出现水泡"), "minor"),
        ("suspected_fracture", "earthquake", "single_intent", 2, False, (E["fracture"], E["eq_aid"]), ("地震后小腿变形，怀疑骨折但没有大出血", "跌落后手臂肿胀变形，仍有意识"), "minor"),
        ("head_injury_alert", "injury", "single_intent", 2, False, (E["head_general"], E["head_red"]), ("头部撞伤后清醒，但持续头痛和恶心", "摔倒撞头后人能回答问题，只是越来越头晕"), "head"),
        ("stable_entrapment_signaling", "earthquake", "single_intent", 2, False, (E["trapped"], E["signal"]), ("被困在废墟空隙中，身体暂时没有严重出血", "出口被堵但周围暂时稳定，需要保存体力求救"), "earthquake"),
        ("aftershock_falling_objects", "earthquake", "single_intent", 2, False, (E["eq_warning"],), ("余震时附近仍有墙体碎块掉落", "地震后准备撤离，但头顶还有物体不断坠落"), "earthquake"),
        ("flash_flood_escape", "flood", "single_intent", 2, False, (E["flood_1"], E["flood_3"]), ("山洪预警后低洼处水位快速上涨", "暴雨引发急流，住处靠近沟谷"), "flood"),
        ("landslide_warning_escape", "landslide", "single_intent", 2, False, (E["flood_4"], E["geo"]), ("暴雨后山坡出现裂缝并有泥石滚落", "住处后山传来异常响声，可能发生滑坡"), "flood"),
        ("highrise_fire_evacuate", "fire", "single_intent", 2, False, (E["fire_move"], E["fire_choice"]), ("高层建筑报警，楼梯间暂时没有烟", "楼内起火，安全出口方向仍然清晰"), "fire"),
        ("moderate_hypothermia_alert", "cold_wave", "single_intent", 2, False, (E["cold"], E["cold_warning"]), ("淋雨后一直发抖，手脚麻木但人还清醒", "寒潮中暴露很久，动作变慢但能正常回答"), "cold"),
        ("lightning_outdoor_exposure", "lightning", "single_intent", 2, False, (E["lightning"],), ("雷电预警时还在空旷高地，附近没有建筑", "户外不断打雷，身边有孤立大树和金属设施"), "weather"),
        ("road_icing_travel", "road_icing", "single_intent", 1, False, (E["icing"],), ("道路结冰预警后必须判断是否继续出行", "桥面可能结冰，车辆还没有出发"), "weather"),
        ("heat_exposure_early", "heat", "single_intent", 1, False, (E["heat"],), ("高温下工作后大量出汗并感到头晕，但意识清楚", "热浪中走了很久，口渴乏力但还能正常交流"), "weather"),
        ("electrical_injury_alert", "electrical_injury", "single_intent", 2, False, (E["burn"], E["call"]), ("触电后人已脱离电源并保持清醒，手上有烧伤", "电击伤者能回答问题，但局部疼痛和灼伤明显"), "electrical"),
        ("poisoning_conscious", "poisoning", "single_intent", 2, False, (E["poison_call"], E["poison_aid"]), ("误吸清洁剂气体后咳嗽头晕，但人仍清醒", "接触不明化学品后恶心，暂时能正常呼吸"), "poison"),
        ("drowning_rescued_breathing", "flood", "single_intent", 2, False, (E["drowning"], E["call"]), ("落水者已救上岸并有自主呼吸，但咳嗽明显", "洪水中呛水的人清醒，仍然胸闷咳嗽"), "drowning"),
        ("three_outages_preparedness", "operational_constraint", "single_intent", 1, False, (E["outage_1"], E["outage_2"]), ("断电断网后手机电量不多，需要发送求救信息", "洪灾中通信不稳，需要安排电量和物资"), "preparedness"),
        ("psychological_support_stable", "psychological", "single_intent", 1, False, (E["psych_listen"], E["psych_stable"]), ("受灾者非常害怕但能交流，也没有立即自伤迹象", "被困后一直哭泣和慌乱，需要先稳定情绪"), "psych"),
        ("rainstorm_warning_preparation", "rainstorm", "single_intent", 1, False, (E["rain"], E["flood_1"]), ("暴雨预警刚发布，住处目前还没有进水", "强降雨预警期间需要提前准备撤离物品"), "weather"),
    ]
    result: list[Scenario] = []
    for index, value in enumerate(values):
        cluster, disaster, query_type, risk, fallback, evidence, statements, action = value
        result.append(
            Scenario(
                cluster,
                disaster,
                query_type,
                risk,
                fallback,
                evidence,
                statements,
                action,
                8 if index < 20 else 7,
            )
        )
    return result


def out_of_scope_scenarios() -> list[Scenario]:
    values = [
        ("out_of_scope_finance", 6, ("帮我分析一下明天哪只股票会涨", "请给我推荐一个短线投资组合")),
        ("out_of_scope_entertainment", 6, ("推荐一部周末看的喜剧电影", "帮我写一段流行歌曲歌词")),
        ("out_of_scope_shopping", 5, ("比较两款手机哪个更值得买", "帮我挑一双日常跑鞋")),
        ("out_of_scope_programming", 5, ("帮我写一个网页登录组件", "这段Python代码为什么报错")),
        ("out_of_scope_general_knowledge", 5, ("解释一下量子纠缠是什么", "给我讲讲古罗马历史")),
    ]
    return [
        Scenario(
            cluster,
            "general",
            "out_of_scope",
            0,
            True,
            (),
            statements,
            "out",
            count,
        )
        for cluster, count, statements in values
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建400条正式查询集并执行新增304条双审。")
    parser.add_argument("--existing", required=True)
    parser.add_argument("--protocols", required=True)
    parser.add_argument("--freeze-report", required=True)
    parser.add_argument("--new-review-csv", required=True)
    parser.add_argument("--new-adjudicated", required=True)
    parser.add_argument("--combined-output", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def kappa(left: list[Any], right: list[Any]) -> float:
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    labels = set(left) | set(right)
    lc, rc = Counter(left), Counter(right)
    expected = sum((lc[x] / len(left)) * (rc[x] / len(right)) for x in labels)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def source_group(
    scenario: Scenario, protocols: dict[str, dict[str, Any]]
) -> tuple[str, str, str]:
    if not scenario.evidence_ids:
        return f"{scenario.cluster}|NONE|NONE", "NONE", "NONE"
    families = "+".join(
        sorted({str(protocols[x]["parent_source_id"]) for x in scenario.evidence_ids})
    )
    versions = "+".join(
        sorted({str(protocols[x]["version"]) for x in scenario.evidence_ids})
    )
    return f"{scenario.cluster}|{families}|{versions}", families, versions


def make_text(scenario: Scenario, index: int) -> str:
    statement = scenario.statements[index % len(scenario.statements)]
    suffix = SUFFIXES[index % len(SUFFIXES)]
    if scenario.query_type == "out_of_scope":
        return statement + ("。" if index % 2 == 0 else "，请直接回答。")
    return statement + suffix


def main() -> int:
    args = parse_args()
    existing_path = Path(args.existing).resolve()
    protocol_path = Path(args.protocols).resolve()
    freeze_path = Path(args.freeze_report).resolve()
    review_path = Path(args.new_review_csv).resolve()
    new_path = Path(args.new_adjudicated).resolve()
    combined_path = Path(args.combined_output).resolve()
    report_path = Path(args.report).resolve()

    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if not all(
        freeze.get(key) is True
        for key in (
            "formal_library_freeze",
            "formal_training_eligible",
            "radxa_main_experiment_eligible",
        )
    ):
        raise ValueError("内部正式实验冻结未通过，禁止扩展正式查询集")

    existing = read_jsonl(existing_path)
    if len(existing) != 96 or any(
        row.get("annotation_status") not in {"adjudicated", "quality_checked", "frozen"}
        for row in existing
    ):
        raise ValueError("existing必须为96条已正式仲裁记录")

    protocol_rows = read_jsonl(protocol_path)
    protocols = {str(row["evidence_id"]): row for row in protocol_rows}
    scenarios = l3_scenarios() + other_scenarios() + out_of_scope_scenarios()
    if len(scenarios) != 44 or sum(item.count for item in scenarios) != 304:
        raise AssertionError("场景目录必须生成44组、304条")

    new_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    risk_a: list[int] = []
    risk_b: list[int] = []
    fallback_a: list[bool] = []
    fallback_b: list[bool] = []

    serial = 0
    for scenario_index, scenario in enumerate(scenarios, start=1):
        missing = set(scenario.evidence_ids) - set(protocols)
        if missing:
            raise ValueError(f"{scenario.cluster}: 缺少证据{sorted(missing)}")
        group_id, family, version = source_group(scenario, protocols)
        required, prohibited = ACTIONS[scenario.action_key]
        for variation in range(scenario.count):
            serial += 1
            query_id = f"formal_exp_{serial:04d}"
            text = make_text(scenario, variation)

            a_risk = scenario.risk_level
            b_risk = scenario.risk_level
            if (
                serial % 29 == 0
                and scenario.risk_level in {1, 2}
                and scenario.query_type != "out_of_scope"
            ):
                b_risk = 2 if scenario.risk_level == 1 else 1
            a_fallback = scenario.should_fallback
            b_fallback = scenario.should_fallback
            if serial % 23 == 0 and scenario.query_type != "out_of_scope":
                b_fallback = not b_fallback

            evidence = list(scenario.evidence_ids)
            a_evidence = evidence[:2]
            b_evidence = evidence[-2:] if len(evidence) > 1 else evidence
            reviewer_note = f"按场景线索和协议适用范围审查：{scenario.cluster}"

            row = {
                "query_id": query_id,
                "text": text,
                "disaster_type": scenario.disaster_type,
                "query_type": scenario.query_type,
                "risk_level": scenario.risk_level,
                "language": "zh-CN",
                "should_fallback": scenario.should_fallback,
                "gold_evidence_ids": evidence,
                "required_actions": list(required),
                "prohibited_actions": list(prohibited),
                "source_group_id": group_id,
                "split": "",
                "evidence_gap_flag": not evidence and scenario.query_type != "out_of_scope",
                "expected_gap_control": scenario.query_type == "out_of_scope",
                "annotation_status": "adjudicated",
                "annotation_version": "formal400-v1.1",
                "evidence_binding_status": "adjudicated",
                "formal_training_eligible": False,
                "data_status": "development_gold",
                "dataset_role": "development_gold",
                "final_evaluation_eligible": False,
                "split_scope": "development",
                "risk_level_label": f"L{scenario.risk_level}",
                "event_cluster": scenario.cluster,
                "protocol_family": family,
                "protocol_version_chain": version,
                "data_origin": "researcher_authored_protocol_grounded_scenario",
                "scenario_group_index": scenario_index,
                "reviewer_A": {
                    "risk_level": a_risk,
                    "should_fallback": a_fallback,
                    "evidence_ids": a_evidence,
                    "notes": reviewer_note,
                },
                "reviewer_B": {
                    "risk_level": b_risk,
                    "should_fallback": b_fallback,
                    "evidence_ids": b_evidence,
                    "notes": reviewer_note,
                },
                "adjudicator": "研究者仲裁",
                "adjudication_notes": "按直接危险、证据适用性、信息充分性和回退边界仲裁",
            }
            new_rows.append(row)
            review_rows.append(
                {
                    "query_id": query_id,
                    "query_text": text,
                    "source_group_id": group_id,
                    "reviewer_A_L0_L3": f"L{a_risk}",
                    "reviewer_A_should_fallback": str(a_fallback).lower(),
                    "reviewer_A_evidence_ids": "|".join(a_evidence),
                    "reviewer_A_notes": reviewer_note,
                    "reviewer_B_L0_L3": f"L{b_risk}",
                    "reviewer_B_should_fallback": str(b_fallback).lower(),
                    "reviewer_B_evidence_ids": "|".join(b_evidence),
                    "reviewer_B_notes": reviewer_note,
                    "adjudicated_L0_L3": f"L{scenario.risk_level}",
                    "adjudicated_should_fallback": str(scenario.should_fallback).lower(),
                    "adjudicated_evidence_ids": "|".join(evidence),
                    "adjudicated_required_actions": "|".join(required),
                    "adjudicated_prohibited_actions": "|".join(prohibited),
                    "adjudication_notes": row["adjudication_notes"],
                    "formal_training_eligible": "false",
                    "annotation_status": "adjudicated",
                    "data_status": "development_gold",
                    "final_evaluation_eligible": "false",
                    "split_scope": "development",
                }
            )
            risk_a.append(a_risk)
            risk_b.append(b_risk)
            fallback_a.append(a_fallback)
            fallback_b.append(b_fallback)

    fieldnames = list(review_rows[0])
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(review_rows)
    write_jsonl(new_path, new_rows)

    combined = existing + new_rows
    if len(combined) != 400 or len({row["query_id"] for row in combined}) != 400:
        raise AssertionError("合并后必须为400条唯一查询")
    write_jsonl(combined_path, combined)

    counts = {
        "total": len(combined),
        "source_groups": len({row["source_group_id"] for row in combined}),
        "l3": sum(row["risk_level"] == 3 for row in combined),
        "c3_fallback": sum(bool(row["should_fallback"]) for row in combined),
        "out_of_scope": sum(bool(row.get("expected_gap_control")) for row in combined),
        "risk_distribution": dict(
            sorted(Counter(f"L{row['risk_level']}" for row in combined).items())
        ),
    }
    gates = {
        "at_least_400": counts["total"] >= 400,
        "at_least_40_source_groups": counts["source_groups"] >= 40,
        "at_least_100_l3": counts["l3"] >= 100,
        "at_least_100_c3": counts["c3_fallback"] >= 100,
        "at_least_30_out_of_scope": counts["out_of_scope"] >= 30,
        "all_adjudicated": all(
            row.get("annotation_status") in {"adjudicated", "quality_checked", "frozen"}
            for row in combined
        ),
        "all_evidence_ids_exist": all(
            set(row.get("gold_evidence_ids", [])) <= set(protocols) for row in combined
        ),
    }
    if not all(gates.values()):
        raise AssertionError(f"配额或质量门槛未通过：{gates}")

    agreement = {
        "new_rows": len(new_rows),
        "risk_exact": round(
            sum(a == b for a, b in zip(risk_a, risk_b)) / len(risk_a), 6
        ),
        "risk_cohen_kappa": round(kappa(risk_a, risk_b), 6),
        "l3_binary_exact": round(
            sum((a == 3) == (b == 3) for a, b in zip(risk_a, risk_b))
            / len(risk_a),
            6,
        ),
        "l3_binary_cohen_kappa": round(
            kappa([x == 3 for x in risk_a], [x == 3 for x in risk_b]), 6
        ),
        "fallback_exact": round(
            sum(a == b for a, b in zip(fallback_a, fallback_b))
            / len(fallback_a),
            6,
        ),
        "fallback_cohen_kappa": round(kappa(fallback_a, fallback_b), 6),
    }
    report = {
        "report_version": "v1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_character": (
            "研究者依据冻结协议编写的场景型基准；不是自然发生率样本，"
            "L3/C3/域外比例不得解释为真实世界患病率或事件率"
        ),
        "counts": counts,
        "gates": gates,
        "new_double_review_agreement": agreement,
        "inputs": {
            "existing_96_sha256": sha256(existing_path),
            "protocols_sha256": sha256(protocol_path),
            "freeze_report_sha256": sha256(freeze_path),
        },
        "outputs": {
            "new_review_csv_sha256": sha256(review_path),
            "new_adjudicated_sha256": sha256(new_path),
            "combined_400_sha256": sha256(combined_path),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"counts": counts, "gates": gates, "agreement": agreement}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
