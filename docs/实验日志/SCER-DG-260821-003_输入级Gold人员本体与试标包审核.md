---
record_id: SCER-DG-260821-003
date: 2026-08-21
timezone: Asia/Shanghai
work_type: data_governance_and_annotation_preparation
formal_evidence: false
status: in_progress_pending_domain_review
source_data_status: development_gold
---

# 输入级Gold人员、本体与培训/试标包审核记录

## 目的

确定A/B/C推荐身份，复核风险严重度和响应模式，审计三套本体与质量门槛，并从现有开发材料
抽取互不重叠的培训题和独立试标题，形成可直接分发的主持人与标注工作包。

## 人员结论

- 推荐A为熟悉数据规范的项目研究者；
- 推荐B为独立且具有可核验急救训练/急诊/护理/院前背景的人员；
- 推荐C为比A/B资历更高且独立的急诊、院前、急救护理或红十字救护培训专业人员；
- 资源受限时，A/B可为两名经训练的独立标注者，唯一领域人员保留为C；论文不得写成
  “two clinical experts”。

## 标签和本体审核

- S0–S3在增加时间/后果锚点后可进入C复核；
- DIRECT/CONDITIONAL/SAFE_FALLBACK增加了按scope、证据适用性和决定性变量判定的顺序；
- 当前风险、动作、约束本体原文件只有占位行，判定为P0阻断；
- 从开发材料汇总56个风险概念、88个旧动作短语和20个约束候选，全部状态为NEEDS_C_REVIEW；
- 发现旧开发动作存在跨场景错配和复合/重复，例如烧伤起泡题绑定“停止负重/不要现场复位”。
  因此旧答案不作为培训参考答案，只使用题干。

## 题目选择

- 培训练习25条；
- 独立试标25条；
- 每个集合每个source_group最多1条；
- query重叠0；source_group重叠0；
- 全部来自`development_gold`且`final_evaluation_eligible=false`；
- 两集合永久排除于后续正式Gold calibration/test。

## 工作簿

输出目录：`outputs/input_gold_annotation_workpack_v1.1/`。

| 文件 | 用途 | SHA-256 |
|---|---|---|
| `00_主持人总控_输入级Gold_v1.1.xlsx` | P的人员、流程、盲化映射、门槛和本体候选 | `7F85F4CB0193ECF6DB82372D99B35F7A4FC5A4903A44229BF12653403C98D992` |
| `01_发给C_领域审核与培训答案_v1.1.xlsx` | C审核本体、建立培训参考答案、后续仲裁 | `FAA18F490463A5A9C42FEC9C36423CFF43E6099A75C4A43BB85AF5DA1F11AF19` |
| `02_发给A_待C冻结后再发_v1.1.xlsx` | A预生成壳 | `6FC753A692E4276CC3F6268A603D5DEF15FB1A14663FE952688528DD1964AE10` |
| `03_发给B_待C冻结后再发_v1.1.xlsx` | B预生成壳，题序与A不同 | `9BB44F44CC7366B9ADEB213CBE7F632580FAAB8F0F84CCE8EFB602B66AF56AF8` |

A/B文件明确标记`BLOCKED_PENDING_C`，且泄漏检查未发现原始query ID或旧风险分层字段。

## 质量门槛

新增`quality_gates_v0.2.json`。状态为
`methodology_approved_with_blocking_preconditions`，增加原始一致率、scope、trigger和constraint
门槛以及最小25条要求。C、S、T真实签字前不得改为`approved`。

## 验证

- `scripts/计算输入级Gold一致性.py`编译通过；
- 4条合成冒烟数据使用v0.2门槛得到`BLOCKED`，原因包含低于最小25条，符合预期；
- `python -m unittest discover -s tests -p 'test_*.py'`：71项通过；
- 四份XLSX均完成结构检查、公式错误扫描和逐sheet渲染；
- 25/25、query/source-group互斥、开发数据边界和盲化检查写入
  `培训与试标题互斥验证_v1.1.json`。

## 当前阻断项与下一步

1. 招募并核验真实C；
2. 先把C工作簿发给C，完成三套本体和培训参考答案；
3. C返回后冻结ontology/manual版本并重新生成可正式发放的A/B工作簿；
4. A/B培训后独立试标；
5. 主持人锁定A/B文件并运行仲裁前一致性脚本；
6. C仲裁，S/T决定准入。

本记录不改变E0的`in_progress_waiting_hardware`，不产生任何正式能耗或正式Gold结论。
