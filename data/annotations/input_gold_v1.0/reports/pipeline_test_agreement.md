# 输入级 Gold 仲裁前一致性报告

生成时间：2026-08-21T09:16:39.759910+00:00
配对记录：4
指标门禁：`REVIEW_REQUIRED`
正式门禁：`REVIEW_REQUIRED_UNTIL_GATE_PROFILE_APPROVED`

## 输入文件

- Reviewer A：`data\annotations\input_gold_v1.0\pilot\pipeline_test_A.csv`
  - SHA-256：`984823E637D363DEAF67FD353977B84617DA46AD544422EBC915B3973627E6D9`
- Reviewer B：`data\annotations\input_gold_v1.0\pilot\pipeline_test_B.csv`
  - SHA-256：`8C143B019E7DAC30E1F4BB26A553A5A70638DB6ECDB8739DE4A1E9DDEB997754`

## 分类与有序字段

| 字段 | n | 原始一致率 | Kappa | 95% CI |
|---|---:|---:|---:|---:|
| scope_state | 4 | 1.0000 | 1.0000 | [1.0000, 1.0000] |
| hazard_family_id | 4 | 1.0000 | 1.0000 | [1.0000, 1.0000] |
| risk_state | 4 | 1.0000 | 1.0000 | [1.0000, 1.0000] |
| escalation_required | 4 | 1.0000 | 1.0000 | [1.0000, 1.0000] |
| recommended_response_mode | 4 | 0.7500 | 0.5556 | [0.0000, 1.0000] |
| risk_severity | 4 | 0.7500 | 0.9167 | [0.0000, 1.0000] |

## 集合字段

| 字段 | Exact | Mean IoU | IoU 95% CI | Mean Dice | 双方空/单边空/双方非空 |
|---|---:|---:|---:|---:|---:|
| query_intent_ids | 1.0000 | 1.0000 | [1.0000, 1.0000] | 1.0000 | 0/0/4 |
| risk_trigger_ids | 1.0000 | 1.0000 | [1.0000, 1.0000] | 1.0000 | 1/0/3 |
| evidence_ids | 1.0000 | 1.0000 | [1.0000, 1.0000] | 1.0000 | 2/0/2 |
| required_action_ids | 0.7500 | 0.8750 | [0.6250, 1.0000] | 0.9167 | 2/0/2 |
| critical_action_ids | 1.0000 | 1.0000 | [1.0000, 1.0000] | 1.0000 | 3/0/1 |
| prohibited_action_ids | 1.0000 | 1.0000 | [1.0000, 1.0000] | 1.0000 | 4/0/0 |
| constraint_ids | 1.0000 | 1.0000 | [1.0000, 1.0000] | 1.0000 | 1/0/3 |

## 质量门禁

| 检查 | 实际值 | 条件 | 门槛 | 通过 |
|---|---:|---:|---:|---:|
| risk_state_kappa | 1.0000 | >= | 0.7500 | 是 |
| risk_severity_quadratic_kappa | 0.9167 | >= | 0.7500 | 是 |
| escalation_required_kappa | 1.0000 | >= | 0.8000 | 是 |
| recommended_response_mode_kappa | 0.5556 | >= | 0.7500 | 否 |
| evidence_ids_mean_iou | 1.0000 | >= | 0.6700 | 是 |
| required_action_ids_mean_iou | 0.8750 | >= | 0.6700 | 是 |
| critical_action_ids_mean_iou | 1.0000 | >= | 0.6700 | 是 |
| prohibited_action_ids_mean_iou | 1.0000 | >= | 0.6700 | 是 |
| severe_severity_disagreement_count | 0 | <= | 0 | 是 |
| required_prohibited_conflict_count | 0 | <= | 0 | 是 |
| critical_not_required_conflict_count | 0 | <= | 0 | 是 |

## 分歧与阻断项

- 存在任意内容分歧的查询：2
- S3 对 S0/S1 严重分歧：0
- required/prohibited 冲突：0
- critical 非 required 冲突：0

### 待仲裁查询

- `PIPE_001`：required_action_ids
- `PIPE_003`：recommended_response_mode, risk_severity

## 解释边界

本报告使用仲裁前 A/B 原始标签，只衡量标注一致性。它不证明标签无偏、医学正确、
临床有效或系统在真实灾害中安全。门禁通过仅表示该批次可以进入领域仲裁。
