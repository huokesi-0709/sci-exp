# 查询候选数据说明

## 当前文件

`旧项目先导候选查询_v0.1.jsonl` 是从作者旧项目
RAIR-RAG gold v2 中确定性抽取的 120 条历史查询候选。

它不是当前研究的正式数据集，原因包括：

- 旧标签针对预检索风险路由，不等于逐配置 RAG 的 L3 严重失效标签；
- 旧 `expected_protocol_id` 不是当前知识库的 `gold_evidence_ids`；
- 部分旧中文指南来源尚待重新核实；
- 当前正式协议正文、版本和切块 ID 尚未冻结；
- 尚未完成当前任务的双人独立标注和仲裁。

## 强制状态

每条候选记录必须保持：

```json
{
  "formal_training_eligible": false,
  "pilot_status": "needs_protocol_grounding_and_current_reannotation",
  "gold_evidence_ids": [],
  "required_actions": [],
  "prohibited_actions": [],
  "split": ""
}
```

在完成协议绑定、双标、一致性检查、仲裁和数据冻结前，不得修改为正式可用状态，
也不得将本文件直接传给训练、校准或测试流程。

## 下一步

1. 收集并登记当前研究采用的权威应急协议；
2. 生成稳定的协议切块 ID；
3. 用 `data/annotations/先导查询重新标注模板_v0.1.csv` 进行双人独立标注；
4. 计算一致性并仲裁分歧；
5. 生成新的当前任务 gold 文件；
6. 通过预处理、隐私检查和同源分组划分后，才进入 `processed/` 与 `splits/`。
