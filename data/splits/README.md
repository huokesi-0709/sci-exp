# 数据划分目录（v1.0历史版本）

本目录是使用SHA-256来源组哈希生成的历史工程分区，仅用于追溯已有Smoke输出。
当前活动开发分区已迁移到：

```text
data/splits_stratified_v2/
```

禁止使用本目录继续选择模型、校准阈值或形成论文结果。

正式划分建议包含：

- `train.jsonl`
- `valid.jsonl`
- `cal_op.jsonl`
- `cal_ch.jsonl`
- `test_op.jsonl`
- `test_ch.jsonl`
- `ood_adapt.jsonl`
- `ood_final.jsonl`

同一协议家族、版本链、事件簇、语义模板和扰动对不得跨分区。
