---
record_id: SCER-DG-260821-001
record_type: data_governance_fix
date: 2026-08-21
timezone: Asia/Shanghai
stage: cross_stage_data_governance
status: resolved
formal_evidence: false
issue: gold_label_inference_leakage
---

# Gold标签隔离与推理边界修复记录

## 结论

`gold_label_inference_leakage`已于2026-08-21完成修复并通过回归验证。今后的智能体不得把
该问题继续写成“当前未解决阻断项”，除非相关边界代码、输入Schema或Radxa配置再次发生
破坏性变更并有新的可定位证据。

本记录只关闭Gold标签参与推理的问题，不改变E0状态，不代表当前400条
`development_gold`已经升级为正式Gold Test，也不构成论文正式实验结果。

## 原问题

旧实现把人工标注的`disaster_type`传给C2检索流程，用于灾害类型过滤、二次查询扩展和
hazard bonus。真实部署时无法获得这一人工Gold字段，因此旧评测可能高估检索能力。

## 已完成修复

1. 在`src/sci_exp/schemas.py`新增严格的`InferenceQuery`推理输入类型。
2. 路由、风险特征、检索和生成只接收`InferenceQuery`；完整`QueryRecord`直接进入检索
   管线会被拒绝。
3. Runner即使读取开发期完整标注，也会在推理前转换为Gold-free视图；Gold只允许在
   推理完成后的开发评测阶段使用。
4. C2不再读取人工`disaster_type`，并移除了依赖该Gold字段的过滤、查询扩展和加分。
5. 新增`data/schemas/inference_query.schema.json`和
   `export-inference-queries`导出命令，使用字段白名单而不是黑名单复制。
6. 从六个开发分区导出400条Gold-free推理记录，另导出3条smoke记录，保存到
   `data/inference_splits_stratified_v2/`。
7. `radxa.smoke.json`、`radxa.experiment.json`和`radxa.challenge.json`均设置
   `data.query_role=inference`，只读取Gold-free路径。
8. `.radxa-sync-exclude`阻止完整标注、双审、裁决和Gold分区继续同步到Radxa。

## 验证结果

- 命令：`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
- 结果：71项测试全部通过。
- Gold-free扫描：7个JSONL文件，共403条记录，其中正式开发六分区合计400条，smoke 3条。
- 扫描发现的Gold字段：0。
- 防回归测试确认：改变`disaster_type`、风险等级、期望回退、Gold证据、必需动作或禁止
  动作，不会改变检索与生成结果。
- 防误用测试确认：`ConfigurationPipeline.run`直接接收带Gold的`QueryRecord`时抛出
  `TypeError`。

## 后续边界

- 如果以后重新启用灾害类别过滤，类别必须来自运行时预测器或真实可观察的外部输入，
  不得来自人工Gold；分类器的错误、时延和能耗必须计入实验。
- 同步脚本按项目规则不使用`--delete`。Radxa上若有历史Gold副本，本次未自动删除；但
  当前运行配置不会读取，严格推理加载器也会拒绝含Gold字段的输入。
- 修改`InferenceQuery`、`GOLD_ONLY_FIELDS`、推理Schema、Runner边界、C2检索参数或
  Radxa查询路径后，必须重新运行本记录中的防泄漏测试。

