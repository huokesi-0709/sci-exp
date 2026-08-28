# 试标与准入 SOP

## 1. 目的

试标用于验证标签定义和人员培训是否足够，不用于制造漂亮的一致性数字。试标题不得进入
Gold Calibration 或 Gold Test。

## 2. 试题组成

建议准备两套互不重叠的试题：

- 培训练习集：20–30 条，可讨论并提供参考解释；
- 独立准入集：20–30 条，A/B 盲标，不提前提供答案。

每套应覆盖：

- Positive、Negative、Unknown；
- S0–S3；
- 证据充足和 evidence gap；
- 直接指导、条件性指导和安全回退；
- required/critical/prohibited；
- 域外、否定、条件冲突、辖区不符和本体缺项。

不要只从同一模板或同一 `source_group_id` 抽题。

## 3. 准入流程

1. P 冻结试题、协议、本体和手册版本并计算 SHA-256；
2. P 生成顺序不同的 A/B 文件；
3. A/B 在规定时间内独立提交；
4. P 检查 ID 和版本一致，锁定原始文件；
5. P 运行一致性脚本并保存仲裁前报告；
6. A/B/C 只讨论分歧类型和定义，不把分歧项回改成伪原始一致；
7. 如需修改手册，版本递增并使用一套新试题复测；
8. S 根据报告和 C 意见批准或拒绝正式准入。

## 4. 候选准入门槛

下列门槛是项目内部候选值，须经领域审核者和研究监督者确认后冻结：

| 指标 | 候选门槛 | 处理 |
|---|---:|---|
| `scope_state` kappa / 原始一致率 | ≥0.80 / ≥0.92 | 低于门槛则检查域内外边界 |
| `risk_state` kappa / 原始一致率 | ≥0.75 / ≥0.84 | 低于门槛则检查三状态定义 |
| `risk_severity` quadratic weighted kappa / exact | ≥0.75 / ≥0.72 | 同时检查严重分歧 |
| `escalation_required` kappa / 原始一致率 | ≥0.80 / ≥0.88 | S3 漏升级需逐条复核 |
| `recommended_response_mode` kappa / 原始一致率 | ≥0.75 / ≥0.80 | 检查 conditional 与 fallback 边界 |
| evidence mean IoU | ≥0.67 | 低于门槛则补证据适用性培训 |
| trigger/required/critical/prohibited/constraint mean IoU | 各 ≥0.67 | 先确认本体是否完整 |
| S3 对 S0/S1 的严重分歧 | 0 条 | 出现即暂停准入 |
| required/prohibited 同 ID 冲突 | 0 条 | 出现即暂停准入 |

小样本 Kappa 可能不稳定，因此不得只按一个点估计机械通过。P、C、S 应共同阅读分歧矩阵、
阳性比例、原始一致率和具体高风险错误。

25 条试标中，如果任一受控类别在任一标注者中少于 3 条，不对该类别稳定性作强结论；点估计
通过但 CI 很宽时，可扩大到 30–50 条全新试题。禁止通过回改旧题或调低预注册门槛获得通过。

## 5. 未通过时怎么办

按以下顺序处理：

```text
定位分歧字段
→ 区分人员误读/定义不清/本体缺项/证据冲突
→ 由 C 审核修改
→ 发布新版本手册或本体
→ 用新试题重新独立试标
```

禁止让 A/B 直接把旧试题改成相同答案后重新计算一致性。

## 6. 准入记录

每名标注者最终状态只能是：

- `qualified_for_formal_annotation`
- `qualified_with_restricted_fields`
- `retraining_required`
- `not_qualified`

若为 restricted，必须写明不能独立标注的字段及由谁复核。
