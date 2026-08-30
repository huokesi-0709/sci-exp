---
schema_version: experiment-log-v1.0
exp_id: SCER-E1-260829-004
system: SC-EA-RAG
stage: E1
experiment_type: 新官方GGUF单query随机dry-run功率采集异常与诊断修复
date: 2026-08-29
timezone: Asia/Shanghai
status: failed_nonformal_dry_run_diagnostic_fix_pending_marker_precheck
formal_evidence: false
operator: user
device: Radxa ZERO 3 + ESP32-S3/INA226/SHT31
---

# E1：新模型dry-run采集异常与采集器诊断修复

## 结果与处置

本记录覆盖新官方Q4_K_M模型后的非正式dry-run恢复过程；没有一轮可作为E1证据，也不得运行能耗积分或回填。

- `006`：llama-server未运行，9/9请求均为`Connection refused`；Windows采集器同时发生COM18读取`PermissionError`，因此不重试同名文件。
- `007`：仅获得同一会话的空闲`idle_start/idle_end`，Windows collector为11,339 sample、114 environment、2 marker、`invalid=0`；尚未运行推理。
- `008`：`idle_start`未获得采集器ACK，标记发送端超时；中止，不执行推理。
- `009`：单个`idle_start`验证成功，Windows collector为2,459 sample、25 environment、1 marker、`invalid=0`；这是端口闭环测试，不含配对空闲区间或推理。
- `010`：新模型真实RAG链完成9/9运行成功，Windows完整raw为`D:\sci-exp-data\E1_20260829\INA226_E1_devtemp_dryrun_010.full.jsonl`，collector汇总75,346 sample、754 environment、22 marker、`invalid=34`。22个标记由两次重复的空闲配对（4）与9条查询的起止边界（18）构成。该会话因非零无效记录及重复空闲对不接受；raw保留在Git外，禁止覆盖。文件字节数、行数和SHA-256尚待补录，不能把缺失元数据伪造为完整归档。

## 诊断修复

此前采集器只输出单一`invalid`计数，并在解析失败时直接丢弃输入；无法区分串口不完整行、串口损坏字节或异常UDP包。已修改`scripts/采集INA226串口功率.py`：

- 串口以字节缓冲读取，仅在收到完整换行后解析一条NDJSON，避免短超时返回的半行被当作无效JSON；
- 汇总新增`invalid_serial`和`invalid_marker`；
- 每条无效输入以`collector_invalid`记录写入当前raw，包含来源、异常类别、字节长度和最多64字节的十六进制预览，便于审计；
- 新增单元测试覆盖跨读取边界的半条JSON；全套73项测试通过。

## 下一动作

先用更新后的Windows采集器执行一轮短时、配对UDP标记预检。只有collector报告`invalid=0`、`invalid_serial=0`、`invalid_marker=0`，才使用全新run ID进行下一次9-run dry-run。下一轮只发送一对空闲标记；Windows采集器必须在空闲和全部9次推理期间持续运行。

## 2026-08-30补充：012停止边界诊断

短时配对标记预检`012`收到5,404 sample、55 environment和2个完整marker，`invalid_marker=0`；唯一的`invalid_serial=1`审计记录为`unterminated serial row`，长度1字节、十六进制`7b`（字符`{`），时间位于用户按`Ctrl+C`的采集停止边界。它不是一条已换行但无法解析的串口记录，而是下一条NDJSON只读取首字节时进程收到停止信号。完整raw为`D:\sci-exp-data\E1_20260830\INA226_E1_devtemp_marker_precheck_012.full.jsonl`，2,379,426 bytes、5,473行，SHA-256为`00D40E3BCAE176730165853BA140F667AD9410F5CD7E50CF8E178734F25F0660`，保留在Git外且不得覆盖。

采集器进一步修正：停止边界的非空尾部改记为`collector_shutdown_partial`和`partial_serial_at_shutdown`，不再计入`invalid`或`invalid_serial`；完整换行记录的UTF-8/JSON解析失败仍保持严格无效。后续接受门槛仍要求`invalid=0`、`invalid_serial=0`、`invalid_marker=0`，同时透明报告停止边界尾部计数。
