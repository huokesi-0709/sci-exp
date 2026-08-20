# 数据目录与处理边界

本目录只存放离线应急 RAG 实验数据，并随 `sci-exp` 一起复制到
`/home/radxa/sci-exp/data`。

## 数据流

1. 将依法取得的原始协议放入 `raw/protocols/`，公开评测数据放入
   `raw/public_datasets/`。
2. 复制并填写 `raw/protocols/source_registry.template.jsonl`，再运行
   `sci-exp prepare-protocols`，按 `schemas/protocol_chunk.schema.json` 生成
   `processed/protocols.jsonl`。TXT/Markdown 无额外依赖；PDF 需要 `pypdf`。
3. 按 `schemas/query.schema.json` 生成人工复核后的查询标注文件。
4. 使用 `sci-exp preprocess-queries` 完成规范化、隐私扫描、异常隔离、按
   `source_group_id` 分组划分、训练集增强和哈希留痕。严禁同源改写跨集合。
5. 训练风险模型只使用 `train`/`valid`；阈值只使用 `cal_op`；最终结论只使用
   `test_op`/`test_ch`。

### 标注规范 v1.0 约束

- 当前 400 条记录统一标记为 `data_status=development_gold`、
  `split_scope=development`、`formal_training_eligible=false` 和
  `final_evaluation_eligible=false`。文件中的 `train`、`cal_*`、`test_*`
  仅保留开发阶段分组来源，不能当作确认性分区。
- `risk_level_label` 使用 `L0`–`L3`；为兼容现有路由代码，`risk_level` 的
  数值编码 0–3 暂时保留。`disaster_type_label` 和 `query_type_label` 使用
  规范中的受控中文值，旧的英文标签保留在原字段供工程分组和追溯。
- `gold_evidence_ids` 为空时必须同时 `evidence_gap_flag=true`；证据 ID 必须
  存在于 `processed/protocols.jsonl`，且不得把机器候选直接当作 gold。
- 输出级标注只有在正式运行门槛通过并生成真实输出后，按
  `query_id+configuration+repetition` 写入 `annotations/adjudication_*.jsonl`；
  当前 `adjudication_template.jsonl` 只是空白模板，不代表已有输出结论。

## 数据状态

| 数据 | 当前状态 | 允许用途 |
|---|---|---|
| `sample_*.jsonl` | 演示数据 | 代码 smoke 测试 |
| `raw/queries/旧项目先导候选查询_v0.1.jsonl` | 历史候选、待重新标注 | 先导筛选、标注流程试运行 |
| `annotations/先导查询重新标注模板_v0.1.csv` | 空白工作表 | 双人独立重新标注 |
| `raw/protocols/协议来源登记_v0.1.jsonl` | 7份官方候选来源 | 来源和文件哈希审计 |
| `processed/候选协议切块_v0.1.jsonl` | 1382条 `draft` 切块 | 内容审查与切块调试 |
| `processed/精选候选协议切块_v0.1.jsonl` | 50条章节级 `draft` 切块 | 双人内容审查、先导证据建议 |
| `annotations/先导24条证据绑定候选_v0.1.jsonl` | 24条机器建议、非gold | 双审与仲裁输入 |
| `annotations/先导24条证据双审表_v0.1.csv` | 已填写双轮审查和仲裁 | 审查追踪与人工查阅 |
| `annotations/先导24条证据仲裁结果_v0.1.jsonl` | 24条已仲裁、协议仍待批准 | 缺口分析和流程验证 |
| `logs/先导24条双审一致性报告_v0.1.json` | 一致性、分布和机器召回诊断 | 先导质量审计 |
| `processed/` 与 `splits/` | 尚无正式数据 | 待协议绑定、复核、冻结后生成 |

历史候选池的旧标签只作为溯源元数据。只要
`formal_training_eligible=false`、`gold_evidence_ids` 为空或 `split` 为空，就不得
进入训练、校准和测试。导入报告及输入/输出哈希位于
`logs/旧项目先导数据导入报告_v0.1.json`。

正式查询预处理：

```bash
bash scripts/run_preprocess.sh data/raw/public_datasets/queries.jsonl 42 0
```

Windows 可运行：

```powershell
.\scripts\run_preprocess.ps1 `
  -Queries data\raw\public_datasets\queries.jsonl `
  -Seed 42 `
  -AugmentTrainCopies 0
```

有问题的记录写入 `quarantine/`，处理事件和哈希报告写入 `logs/`。正式流程使用
`--fail-on-quarantine`：只要存在待人工处理记录就以非零状态退出，但不会修改或
删除原始文件。增强默认关闭，确有预注册方案时才能设为 1 或 2。

`sample_*.jsonl` 是流水线演示数据，来源字段为 `DEMO_ONLY`，不得作为论文实验
结果。当前工程没有伪造或自动补齐真实应急协议；正式数据需要保留来源、版本、
适用地区、有效期、授权和校验和。
