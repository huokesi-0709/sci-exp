---
record_id: SCER-DG-260821-002
record_type: data_governance_preparation
date: 2026-08-21
timezone: Asia/Shanghai
stage: cross_stage_annotation_preparation
status: preparation_complete_pending_domain_review
formal_evidence: false
---

# 输入级协议 Gold 标注工作包建立记录

## 结论

已建立输入级协议 Gold 的项目说明、角色、专业人员招募、培训、字段定义、试标、正式双盲、
一致性、仲裁、冻结和论文报告工作包，并创建与 Radxa 推理路径隔离的数据目录、模板、Schema
和一致性统计脚本。

该工作只完成流程和工具准备，不代表已有真实专业人员审核、真实 A/B 双审、正式一致性、
Gold Calibration 或 Gold Test。所有产物 `formal_evidence=false`，当前 400 条继续保持
`development_gold`。

## 新增入口

- 人工手册：`docs/输入级Gold标注工作包_v1.0/README.md`
- 数据区：`data/annotations/input_gold_v1.0/README.md`
- 一致性脚本：`scripts/计算输入级Gold一致性.py`
- 候选质量门槛：
  `data/annotations/input_gold_v1.0/templates/quality_gates_v0.1.json`

## 管线验证

使用两份明确标记为 `PILOT` 和管线占位的 CSV 运行 200 次 source-group bootstrap：

```powershell
.\.venv\Scripts\python.exe scripts\计算输入级Gold一致性.py `
  --reviewer-a data\annotations\input_gold_v1.0\pilot\pipeline_test_A.csv `
  --reviewer-b data\annotations\input_gold_v1.0\pilot\pipeline_test_B.csv `
  --output-json data\annotations\input_gold_v1.0\reports\pipeline_test_agreement.json `
  --output-md data\annotations\input_gold_v1.0\reports\pipeline_test_agreement.md `
  --gates data\annotations\input_gold_v1.0\templates\quality_gates_v0.1.json `
  --bootstrap 200 --seed 20260821
```

结果：脚本退出码 0，配对 4 条，识别 2 条分歧查询；候选指标决定为
`REVIEW_REQUIRED`，正式决定为 `REVIEW_REQUIRED_UNTIL_GATE_PROFILE_APPROVED`。
这符合样例中预设的不一致和候选门槛尚未获批准的状态。

## 边界与下一动作

下一动作不是生成正式 Gold，而是：

1. 导师确认研究边界和人员方案；
2. 招募领域审核/仲裁者；
3. 由领域人员审核严重度、风险触发、动作和约束本体；
4. 批准或修订候选质量门槛；
5. 创建与正式数据不重叠的培训题和独立试标题；
6. 完成真实 A/B 试标后再决定正式样本量和批次。

