---
schema_version: experiment-log-v1.0
exp_id: SCER-E1-260829-002
system: SC-EA-RAG
stage: E1
experiment_type: Dev-Temp单query随机顺序dry-run与外部功率回填
date: 2026-08-29
timezone: Asia/Shanghai
status: passed_nonformal_dry_run
formal_evidence: false
operator: user
device: Radxa ZERO 3 + ESP32-S3/INA226/SHT31
---

# E1：Dev-Temp随机dry-run与设备时钟积分

## 目的与范围

只验证E1的随机任务顺序、UDP query边界、INA226能耗积分和回填链路；不做盲审，不能生成Oracle或配置异质性结论。

## 固定输入与执行

- 查询：`data/inference_splits_stratified_v2/valid.jsonl`首条，推理端不含Gold标签。
- 配置与重复：C0/C1/C2，各3次；配置文件seed为42。
- Radxa运行输出：`results/E1_devtemp_dryrun_005.jsonl`，9行、9/9成功，SHA-256为`828B373833B189590E35DEC03C6955DD16FF866E1B32ACEBD33531364ED3EDA9`。
- Windows完整原始功率流（Git外只读保存）：`D:\sci-exp-data\E1_20260829\INA226_E1_devtemp_dryrun_005.full.jsonl`，21,145,763 bytes、47,904 sample、480 environment、20 marker、0 invalid，SHA-256为`841D54A4513297935327EF554113F71B57296C0DCDC512708FDE515470AD1E6D`。
- 同一采集会话内的空闲标记：`E1_devtemp_dryrun_idle_005`，65.469秒。

## 时钟判定修正

第一次整合错误使用Windows `host_monotonic_ns`作功率积分和连续性时钟，得到4/9有效；其最大到达间隔为32ms。
原始ESP32 `device_us`显示P99/最大采样间隔为10.984/16.025ms，且无设备侧质量标志。原因是Windows约15.6ms的调度量化，不是INA226采样中断。

已修正`整合INA226查询能耗.py`：主机单调时钟只用于将UDP标记映射到采样边界；边界内的梯形积分与30ms连续性门槛使用连续的ESP32 `device_us`。新增单元测试覆盖“32ms主机到达间隔但10ms设备采样间隔”的情形。

复算结果：9/9有效，空闲功率`1.2778067249631462W`；输出为：

- `results/E1_devtemp_dryrun_005.deviceclock.energy.jsonl`，SHA-256 `3681923E526D446B27B0C3C9FB5772507940A609116E5822F5BAE3A23778D694`；
- `results/E1_devtemp_dryrun_005.deviceclock.meter_merged.jsonl`，SHA-256 `1BDC037B1502968088681AC44FE9B7EEB333DD851D21D902450C43E911F746EF`。

第一版由主机到达时间产生的`E1_devtemp_dryrun_005.energy.jsonl`和对应merged文件保留为诊断派生物，但不用于任何正式或非正式性能结论。

## 结论与下一门槛

本次确认采样链在设备时钟上满足30ms连续性门槛，并确认9条运行均可回填`external_meter_valid=true`。结果严格标记为`formal_evidence: false`。在冻结正式E1 Dev-Temp 315次穷举前，仍需完成GGUF的可追溯来源、tokenizer元数据和无`missing pre-tokenizer type`警告的运行时审计。
