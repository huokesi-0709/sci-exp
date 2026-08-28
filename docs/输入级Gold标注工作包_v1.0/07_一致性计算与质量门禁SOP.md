# 一致性计算与质量门禁 SOP

## 1. 谁来操作

一致性计算由项目负责人/数据管理员操作，即通常由论文第一作者执行。标注者只提交独立
原始标签，领域人员负责专业判断和仲裁，不要求他们编程。

项目负责人运行统计时不是“第三名标注者”，不得修改 A/B 内容。建议由导师或另一名具备
统计能力的人员复核命令、文件哈希和报告。

## 2. 运行时间点

只允许在以下状态运行：

```text
A 文件已锁定 + B 文件已锁定 + query ID/版本一致 + 尚未进行内容仲裁
```

结构性错误可以由原标注者更正并保留版本链，但一旦看到一致性结果，不得回改判断以提高
指标。

## 3. 输入文件要求

- A/B 各一份 CSV；
- `query_id` 唯一且集合完全相同；
- 每一对记录的 query text、source group、手册、语料和本体版本一致；
- 集合字段使用 `|` 分隔；
- 空集合留空，不写 `null`、`None` 或 `[]` 字符串；
- 所有受控字段使用规定大写值。

## 4. 运行命令

在 `docs/sci-exp` 下执行：

```powershell
.\.venv\Scripts\python.exe scripts\计算输入级Gold一致性.py `
  --reviewer-a data\annotations\input_gold_v1.0\formal\reviewer_A\IG-A-BATCH001-v1.0.csv `
  --reviewer-b data\annotations\input_gold_v1.0\formal\reviewer_B\IG-B-BATCH001-v1.0.csv `
  --output-json data\annotations\input_gold_v1.0\reports\IG-BATCH001-agreement-v1.0.json `
  --output-md data\annotations\input_gold_v1.0\reports\IG-BATCH001-agreement-v1.0.md `
  --bootstrap 2000 `
  --seed 20260821
```

培训或小样本 dry-run 可先用 `--bootstrap 200` 检查流程，但正式报告使用预注册次数。

## 5. 脚本输出

报告至少包含：

- A/B 路径、SHA-256、记录数和版本；
- 匹配/缺失/重复 query ID；
- categorical 字段的原始一致率和 Cohen’s kappa；
-严重度的 quadratic weighted kappa；
- evidence、trigger、required、critical、prohibited、constraint 集合的 exact match、IoU 和 Dice；
- `source_group_id` 聚类 bootstrap 95% CI；
- 严重分歧清单；
- required/prohibited 冲突及 critical 非 required 冲突；
- 建议门禁状态和需要仲裁的 query ID。

## 6. 指标解释

### 分类字段

- `risk_state`：Cohen’s kappa + 原始一致率 + 3×3 分歧矩阵；
- `risk_severity`：quadratic weighted kappa + S3 对 S0/S1 严重分歧数；
- `escalation_required`：Cohen’s kappa + YES 阳性一致率；
- `recommended_response_mode`：Cohen’s kappa + 3×3 分歧矩阵。

### 集合字段

- exact match：两个集合是否完全相同；
- Jaccard/IoU：交集除以并集；
- Dice：两倍交集除以集合大小之和；
- 双方均为空时，单条 exact/IoU/Dice 记为 1，但报告中必须另列双方空、单边空和双方非空比例。

### Kappa 注意事项

Kappa 会受类别分布影响，因此不能只报告一个 Kappa。类别高度不平衡时必须同时报告原始
一致率、阳性比例、阳性一致率和分歧矩阵。置信区间以 `source_group_id` 为重采样单位，
避免把同来源近重复查询视为完全独立样本。

## 7. 候选质量门禁

门禁在正式标注前由 C、S 和 T 签字冻结。v0.2 条件批准规则为：

- `scope_state` kappa ≥0.80 且原始一致率 ≥0.92；
- `risk_state` kappa ≥0.75；
- `risk_state` 原始一致率 ≥0.84；
- `risk_severity` quadratic weighted kappa ≥0.75；
- `risk_severity` exact agreement ≥0.72；
- `escalation_required` kappa ≥0.80；
- `escalation_required` 原始一致率 ≥0.88；
- `recommended_response_mode` kappa ≥0.75；
- `recommended_response_mode` 原始一致率 ≥0.80；
- trigger、evidence、required、critical、prohibited、constraint 集合 mean IoU ≥0.67；
- S3 与 S0/S1 严重分歧为 0；
- required/prohibited 交集为 0；
- critical 非 required 为 0；
- 所有分歧已进入仲裁，所有高风险记录已复核。

这些阈值是项目内决策门，不是“医学正确”的替代证据。点估计达标但置信区间很宽时，S 可
要求扩大试标或补充复核。

当前门槛文件只能标记为方法学条件批准；C、S、T 填写真实 ID 和日期后才可改为 `approved`。

## 8. 结果分级

| 状态 | 含义 | 允许用途 |
|---|---|---|
| `PASS_FOR_ADJUDICATION` | 结构和一致性足以进入逐项仲裁 | 可继续仲裁，不等于已冻结 |
| `REVIEW_REQUIRED` | 部分字段低于候选门槛或 CI 过宽 | 修订定义、补训或重点复标 |
| `BLOCKED` | 严重分歧、冲突、缺文件或版本不一致 | 不得进入正式训练/校准/测试 |

## 9. 复核记录

统计复核者至少检查：

- 命令与预注册参数一致；
- A/B 哈希与锁定记录一致；
- 没有误用仲裁文件；
- query ID 配对正确；
- source group bootstrap 已启用；
- 报告中的分歧数量可从原始文件复算；
- 报告版本、脚本 Git commit 和生成时间已记录。
