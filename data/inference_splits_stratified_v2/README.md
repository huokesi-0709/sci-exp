# Gold-free推理分区

本目录由`python -m sci_exp.cli export-inference-queries`从带标注的开发数据导出。
文件只保留推理时可见的字段：`query_id`、`text`、`language`、
`source_group_id`、`split`以及明确允许的地点、日期和目标人群元数据。

`disaster_type`、`risk_level`、`should_fallback`、Gold证据、必需动作、禁止动作、
审核人与裁决信息均不得出现在本目录。加载器发现这些字段时会直接失败。

当前六个分区合计400条，数据身份仍是`development_gold`的推理视图，不得因为完成
Gold-free导出而升级为正式Gold Test。完整标注继续保存在
`data/splits_stratified_v2/`，仅在推理完成后的Windows评测阶段使用。

Radxa配置只允许读取本目录；`.radxa-sync-exclude`会阻止完整标注目录被继续同步。
