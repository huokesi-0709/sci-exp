# 输入级 Gold 数据区

本目录保存人工输入级协议 Gold 的模板、原始 A/B 文件、仲裁、报告和冻结快照。它被
`.radxa-sync-exclude` 的 `data/annotations/` 规则排除，不得进入 Radxa 推理目录。

## 目录职责

- `templates/`：空白表和本体模板，可以复制，禁止直接把模板当数据；
- `schemas/`：JSONL 规范；CSV 是人工工作格式，冻结时转换为 JSONL 并校验；
- `pilot/`：培训和试标，永远不进入正式 Gold；
- `formal/reviewer_A/`：A 原始标注，只追加新版本；
- `formal/reviewer_B/`：B 原始标注，只追加新版本；
- `adjudication/`：领域仲裁记录；
- `reports/`：一致性、质控、哈希、异常和分歧清单；
- `frozen/`：通过全部门禁的最终快照。

## 文件命名

```text
IG-A-BATCH001-v1.0.csv
IG-B-BATCH001-v1.0.csv
IG-BATCH001-agreement-v1.0.json
IG-BATCH001-agreement-v1.0.md
IG-BATCH001-adjudication-v1.0.csv
IG-BATCH001-gold-frozen-v1.0.jsonl
IG-BATCH001-freeze-manifest-v1.0.json
```

不得覆盖旧文件。任何修复使用 `v1.1` 等新版本并在 manifest 记录原因。

## CSV 与 JSONL

CSV 用于人工标注。集合字段用 `|` 分隔；空集合留空。JSONL 是冻结规范格式，集合字段必须
为数组，布尔值必须为 JSON `true/false`。`null` 表示未判定，不等同于空集合。

