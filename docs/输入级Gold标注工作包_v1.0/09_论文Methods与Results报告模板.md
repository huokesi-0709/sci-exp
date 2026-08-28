# 论文 Methods 与 Results 报告模板

以下文字是结构模板，不是已完成事实。方括号必须替换为真实记录，不能提前填写虚构人数、
资历、Kappa、伦理编号或样本量。

## 1. Methods 中文信息清单

论文至少报告：

- 输入级 Gold 的协议一致性边界；
- 查询和协议语料来源、版本和分组方式；
- 标注字段及其操作定义；
- A/B 人数、资格、培训和试标；
- 盲法和禁止信息；
- 仲裁者资格和仲裁范围；
- 仲裁前一致性指标和置信区间计算；
- 数据冻结、版本、哈希和泄漏防护；
- 伦理、隐私、补偿和利益冲突状态；
- 当前数据不能证明临床有效性的边界。

## 2. Methods 英文模板

### Protocol-grounded input annotation

> We constructed input-level protocol Gold labels to characterize whether each query contained a protocol-defined risk trigger and which public-facing actions were required, prohibited or conditional. The labels represented consistency with a frozen corpus of [source organizations and corpus version], rather than clinical diagnosis or real-world treatment effectiveness. Each record included a three-state risk label (positive, negative or unknown), an ordinal severity level, escalation requirements, required and prohibited action identifiers, operational constraints, and the exact protocol evidence supporting each decision.

### Reviewers, training and blinding

> Two trained reviewers independently annotated all records using annotation manual [version] and ontology [version]. Reviewer [A qualification] and reviewer [B qualification] completed [training description] and independently labelled a held-out pilot set of [n] queries before formal annotation. The reviewers could access the frozen protocol corpus but could not access each other’s labels, previous development labels, model outputs, system configurations, routing scores, energy measurements or aggregate label distributions.

### Agreement and adjudication

> Inter-rater agreement was calculated from the original pre-adjudication labels. We used Cohen’s kappa for nominal categorical labels, quadratic-weighted kappa for ordinal severity, and exact-match, Jaccard and Dice coefficients for evidence and action sets. Confidence intervals were obtained by cluster bootstrap resampling at the source-group level with [B] iterations. All disagreements, all high-severity records, all escalation-positive records and [x%] of low-risk agreements were reviewed by an adjudicator with [qualification and relevant experience]. Adjudication was based on the frozen protocol corpus, and the original reviewer files were retained unchanged.

### Data freezing and leakage control

> Query groups and dataset roles were frozen before annotation and were not reassigned using observed Gold labels. Adjudicated files were versioned and hashed before use. Gold-only fields were stored separately from inference inputs and were not transferred to the edge device. The current development set was not used as the confirmatory Gold test set.

### Ethics and scope

仅在获得真实机构结论后选择一种表述：

> [The institutional committee name] determined that [exact approval/exemption/not-human-participant status], reference [identifier].

不得自行写“伦理审批不适用”。如果只有合成和公开文本，也应记录由谁作出不适用认定。

## 3. Results 报告表

| 字段 | n | 原始一致率 | 主指标 | 95% CI | 主要分歧 | 仲裁数 |
|---|---:|---:|---:|---:|---|---:|
| `risk_state` | [ ] | [ ] | Cohen’s κ=[ ] | [ ] | [ ] | [ ] |
| `risk_severity` | [ ] | [ ] | weighted κ=[ ] | [ ] | [ ] | [ ] |
| `escalation_required` | [ ] | [ ] | Cohen’s κ=[ ] | [ ] | [ ] | [ ] |
| response mode | [ ] | [ ] | Cohen’s κ=[ ] | [ ] | [ ] | [ ] |
| evidence IDs | [ ] | exact=[ ] | mean IoU=[ ] | [ ] | [ ] | [ ] |
| required actions | [ ] | exact=[ ] | mean IoU=[ ] | [ ] | [ ] | [ ] |
| prohibited actions | [ ] | exact=[ ] | mean IoU=[ ] | [ ] | [ ] | [ ] |

正文应同时报告类别比例和高风险分歧，不能只写“标注具有较高一致性”。

## 4. Supplementary Information 建议

- 完整标注手册和版本变更；
- 风险触发、动作和约束本体；
- 培训与试标流程；
- 盲法示意图；
- 全部分歧矩阵和分层指标；
- 每个协议家族、风险级别和查询类型的指标；
- 去身份化的 A/B 原始标签或可复算统计；
- 仲裁原因类别统计；
- 伦理/隐私状态和数据来源说明。

## 5. 禁止表述

没有相应证据时不要写：

- “由多名临床专家完成标注”；
- “标签证明了医学正确性”；
- “系统在真实灾害中是安全的”；
- “Kappa 达标说明标签无偏”；
- “当前 400 条是独立 Gold Test”；
- “所有分歧均由专家解决”，除非有完整记录。

