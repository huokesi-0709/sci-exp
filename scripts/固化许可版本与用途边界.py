from __future__ import annotations

import argparse
import csv
from pathlib import Path


COPYRIGHT_LAW_URL = (
    "https://www.npc.gov.cn/c2/c30834/202011/t20201119_308796.html"
)
FAO_TERMS_URL = "https://www.fao.org/contact-us/terms/zh"


VERSION_EVIDENCE = {
    "WHO_ICRC_BEC_2018": (
        "2018-10-30；官方出版页标题、日期、ISBN与本地PDF一致；"
        "PDF版权页（第4页）标明CC BY-NC-SA 3.0 IGO",
        "https://www.who.int/publications/i/item/9789241513081",
    ),
    "WHO_PFA_2011": (
        "2011-10-02；官方出版页标题、日期、ISBN与本地PDF一致；"
        "PDF版权页（第2页）为All rights reserved",
        "https://www.who.int/publications/i/item/9789241548205",
    ),
    "NHC_HEALTH_LITERACY_2024": (
        "2008试行→2015版→2024征求意见稿→2024-05-30正式版；"
        "正式通知国卫办宣传函〔2024〕191号确认2024版替代2015版",
        "https://www.nhc.gov.cn/xcs/c100123/202405/"
        "73a4927142f34152abed875634a3c13b.shtml",
    ),
    "MEM_EARTHQUAKE_SAFETY_2025": (
        "2025-05-12单次新闻发布会文字实录；以发布日期、页面标题和本地SHA-256"
        "固定快照，不主张持续更新",
        "https://www.mem.gov.cn/xw/xwfbh/2025n05y12xwfbh/",
    ),
    "MEM_FLOOD_SAFETY_2025": (
        "2025-08-05单次汛期安全知识发布会文字实录；以发布日期、页面标题和"
        "本地SHA-256固定快照，不主张持续更新",
        "https://www.mem.gov.cn/xw/xwfbh/2025n08y05xwfbh/wzsl_4260/"
        "202508/t20250805_553395.shtml",
    ),
    "MEM_HIGHRISE_FIRE_ORDER5": (
        "应急管理部令第5号，2021-06-21公布，2021-08-01施行；"
        "官方政府信息公开页和PDF一致",
        "https://xxgk.mem.gov.cn/ezweb/ctrl/news/"
        "2106251518254PKfX9LNXY7sD3Mr5zJ",
    ),
    "CMA_WARNING_SIGNALS_ORDER16": (
        "中国气象局令第16号，2007-06-12发布；官方规章页明确效用状态=有效",
        "https://www.cma.gov.cn/zfxxgk/gknr/flfgbz/gz/202005/"
        "t20200528_1694399.html",
    ),
    "SHQP_HEAD_TRAUMA_2018": (
        "页面标注2018-05-29；作为静态历史科普快照使用，"
        "不得作为当前临床规范或唯一证据",
        "https://www.shqp.gov.cn/wsjkw/jkbj/20180621/137365.html",
    ),
    "BJWJW_HYPOTHERMIA_2022": (
        "北京市卫生健康委页面标注2022-10-24、来源为北京市卫生健康委员会；"
        "作为静态科普快照使用",
        "https://wjw.beijing.gov.cn/bmfw_20143/jkzs/jzjj/202210/"
        "t20221024_2842615.html",
    ),
    "BJWJW_CRUSH_INJURY_2019": (
        "北京市卫生健康委页面固定发布日期；作为静态科普快照使用，"
        "不得外推为最新临床规范",
        "https://wjw.beijing.gov.cn/bmfw_20143/jkzs/jzjj/201912/"
        "t20191217_1250605.html",
    ),
    "MEM_EARTHQUAKE_FIRST_AID_2019": (
        "应急管理部页面标注2019-04-01；作为静态科普快照使用",
        "https://www.mem.gov.cn/kp/zrzh/201904/t20190401_366170.shtml",
    ),
    "JINCHENG_HIGHRISE_FIRE_2026": (
        "晋城市人民政府页面标注2026-03-31，信息来源=山西消防；"
        "作为转载快照，仅限内部研究摘录",
        "https://jcgov.gov.cn/dtxx/zxts/202603/t20260331_2335921.shtml",
    ),
    "NHC_PSYCHOLOGICAL_HOTLINE_2021": (
        "国卫办疾控函〔2021〕15号，2021-01-08印发；"
        "2024-12-06统一12356热线通知仍明确要求按该指南接听，未被替代",
        "https://www.nhc.gov.cn/yzygj/c100068/202412/"
        "49a1a65386cd4be582d4702fd0926ee8.shtml",
    ),
    "NHC_DISASTER_ENV_HEALTH_2019": (
        "国家卫生健康委疾控局2019-08-23发布2019版，"
        "官方页面标注2019-08-26；固定为2019版快照",
        "https://www.nhc.gov.cn/jkj/c100063/201908/"
        "1a4b393904a0452da07d1aa49ccd61a3.shtml",
    ),
    "MEM_FLOOD_PREPAREDNESS_2026": (
        "2026-06-23单次汛期安全知识发布会；以发布日期、页面标题和"
        "本地SHA-256固定快照，不主张持续更新",
        "https://www.mem.gov.cn/xw/xwfbh/2026n6y23xwfbh/",
    ),
}


OFFICIAL_DOCUMENT_IDS = {
    "MEM_HIGHRISE_FIRE_ORDER5",
    "CMA_WARNING_SIGNALS_ORDER16",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="固化来源的内部研究、公开再分发、镜像和版本链边界。"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    rows = read_csv(input_path)

    new_fields = [
        "使用依据类型",
        "使用依据URL",
        "内部正式实验资格",
        "正式库处置",
        "公开再分发资格",
        "公开再分发限制",
        "镜像关系状态",
        "镜像关系证据URL",
        "版本状态",
        "版本链结论",
        "版本链证据URL",
    ]

    for row in rows:
        source_id = row["source_id"]
        version_text, version_url = VERSION_EVIDENCE[source_id]
        row["版本状态"] = "verified_as_of_2026-07-28"
        row["版本链结论"] = version_text
        row["版本链证据URL"] = version_url
        row["内部正式实验资格"] = "true"

        if source_id == "WHO_ICRC_BEC_2018":
            row["正文中观察到的许可声明"] = "CC BY-NC-SA 3.0 IGO"
            row["使用依据类型"] = "explicit_cc_by_nc_sa_3_0_igo"
            row["使用依据URL"] = (
                "https://creativecommons.org/licenses/by-nc-sa/3.0/igo/"
            )
            row["许可证据URL"] = row["实际下载地址"]
            row["正式库处置"] = "reference_only_excluded_from_chinese_retrieval"
            row["公开再分发资格"] = "true"
            row["公开再分发限制"] = (
                "仅非商业；署名；相同方式共享；不得使用WHO/ICRC标识；"
                "第三方材料另行核权"
            )
            row["再分发决定"] = (
                "conditional_noncommercial_attribution_sharealike"
            )
        elif source_id == "WHO_PFA_2011":
            row["正文中观察到的许可声明"] = (
                "All rights reserved；复制或翻译须向WHO申请许可"
            )
            row["使用依据类型"] = "all_rights_reserved_metadata_reference_only"
            row["使用依据URL"] = row["来源页面"]
            row["许可证据URL"] = row["实际下载地址"]
            row["正式库处置"] = "metadata_only_excluded_from_direct_retrieval"
            row["公开再分发资格"] = "false"
            row["公开再分发限制"] = (
                "2011版PDF版权页要求另行申请复制或翻译许可"
            )
            row["再分发决定"] = "cleared_for_metadata_only"
        elif source_id in OFFICIAL_DOCUMENT_IDS:
            row["使用依据类型"] = (
                "copyright_law_article_5_official_document_exclusion"
            )
            row["使用依据URL"] = COPYRIGHT_LAW_URL
            row["正式库处置"] = "include_official_document_with_attribution"
            row["公开再分发资格"] = "true"
            row["公开再分发限制"] = (
                "仅官方规章/命令正文；保留来源、文号、版本和有效状态；"
                "不含页面设计、图片和第三方材料"
            )
            row["再分发决定"] = (
                "cleared_official_document_statutory_exclusion"
            )
        else:
            row["使用依据类型"] = (
                "copyright_law_article_24_6_local_scientific_research"
            )
            row["使用依据URL"] = COPYRIGHT_LAW_URL
            row["正式库处置"] = "include_selected_excerpt_local_research_only"
            row["公开再分发资格"] = "false"
            row["公开再分发限制"] = (
                "仅限本研究人员内部科学研究的少量摘录；必须署名；"
                "不得出版发行或公开协议正文/派生切块"
            )
            row["再分发决定"] = (
                "cleared_for_local_research_only_no_redistribution"
            )

        if source_id == "NHC_PSYCHOLOGICAL_HOTLINE_2021":
            row["镜像关系状态"] = (
                "official_subordinate_mirror_provenance_verified_"
                "no_redistribution_grant"
            )
            row["镜像关系证据URL"] = (
                "https://ncmhc.org.cn/channel/newsinfo/6241"
            )
        elif source_id == "NHC_DISASTER_ENV_HEALTH_2019":
            row["镜像关系状态"] = (
                "faolex_hosting_provenance_verified_third_party_"
                "rights_not_granted"
            )
            row["镜像关系证据URL"] = FAO_TERMS_URL
        elif row.get("镜像HTTP状态"):
            row["镜像关系状态"] = (
                "official_download_copy_no_separate_mirror_rights_needed"
            )
            row["镜像关系证据URL"] = row["实际下载地址"]
        else:
            row["镜像关系状态"] = "not_applicable"
            row["镜像关系证据URL"] = ""

        if source_id not in {"WHO_ICRC_BEC_2018", "WHO_PFA_2011"}:
            row["许可证据URL"] = row["使用依据URL"]
        row["版本日期证据"] = version_text
        row["待完成核验"] = (
            "内部研究边界已冻结；公开复现包不得包含公开再分发资格=false"
            "来源的正文或派生切块。"
        )

    fieldnames = list(rows[0])
    for field in new_fields:
        if field not in fieldnames:
            fieldnames.append(field)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"rows={len(rows)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
