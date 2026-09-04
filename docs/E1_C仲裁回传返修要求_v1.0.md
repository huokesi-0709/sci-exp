---
record_id: SCER-E1-260904-026
date: 2026-09-04
stage: E1
type: blind-adjudication-return-audit
formal_evidence: false
status: HOLD_C_RETURN_REPAIR_REQUIRED
---

# E1 C 仲裁回传验收与返修要求

## 本次验收结论

已对 `D:/desktop/AAAAA标注/E1/returns/C/` 的四个文件完成只读核验。A/B 原始回传、分歧表、协议摘录和 C 回传均未被修改。

- C 裁决 JSONL：313 行、313 个唯一 `blind_item_id`，与分歧表集合完全一致；
- 决策：313 条均为 `NEW`；`UNRESOLVED` / `EXCLUDE` 为 0；
- 低风险一致项候选实际为 2 条，C 抽查 2/2，均标为 `CONFIRMED_LOW_RISK`，满足至少 10% 的要求；
- C 必填元数据齐全，裁决者为 `ANN-C-ORG`；
- 当前四个文件的 SHA-256 记录见 `results/E1_C_adjudication_return_audit_v1.0.json`。

## 阻断项

当前不能把这份回传直接合并为最终 Gold。313 条中有 **291 条** 的 `final_value` 未覆盖该行 `disputed_fields` 中的全部字段。缺失字段包括：

`protocol_correct`、`constraint_preserved`、`actionable`、`evidence_relevant`、`evidence_correct`、`fallback_correct`、`trigger_forbidden`、`y_trigger`、`y_miss`、`y_quality`、`protocol_conflict`、`scope_violation`、`severe_failure`、`action_completeness`。

因此，“313 条均已作出 NEW 决定”不等于“313 条最终标签已完整确定”。在缺失字段未得到 C 明确值或透明派生规则前，不得生成 Gold、Oracle、E1 配置异质性或路由结论。

## 发给 C 的返修要求

请在不改动 A/B 原始文件、分歧表、协议或标签定义的前提下，重新导出：

1. `E1_review_C_adjudication.jsonl`：仍为原 313 个 `blind_item_id`，每行 `final_value` 至少覆盖该行全部 `disputed_fields`；推荐直接提供完整 18 字段标签向量。
2. `y_trigger`、`y_miss`、`y_quality` 必须按冻结指南的公式填写；`error_severity=4` 时 `severe_failure` 必须为 `true`。
3. `evidence_correct`、`fallback_correct` 若无法判定可为 `null`，但需在理由或备注中说明；不得用省略字段代替裁决。
4. 保持 `decision`、`adjudication_reason`、`supporting_evidence_ids`、`adjudicator_id` 和时间戳；更新裁决报告和 SHA-256 清单。
5. 低风险抽查文件可保持 2/2；不得把候选项扩写成未实际抽查的项目。

## 返修后流程

收到修正版后，主持人将先执行机械验收，再使用 Git 外私有 crosswalk 把盲编号映射回 315 条能耗主表，运行完整标签/派生字段 QA，最后才生成 E1 Gold 和后续统计。C 不需要、也不应接收配置、重复、run key、能耗或 crosswalk。
