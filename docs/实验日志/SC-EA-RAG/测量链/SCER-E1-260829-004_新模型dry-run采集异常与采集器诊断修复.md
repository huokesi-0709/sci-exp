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

## 2026-08-30补充：013预检通过

使用修正后的collector与Windows新地址`192.168.10.11`完成短时配对标记预检013：3,997 sample、40 environment、2 marker，`invalid=0`、`invalid_serial=0`、`invalid_marker=0`，`partial_serial_at_shutdown=1`。停止尾部按设计独立审计，不影响完整记录有效性；UDP与串口短预检门槛通过。

完整raw为`D:\sci-exp-data\E1_20260830\INA226_E1_devtemp_marker_precheck_013.full.jsonl`，1,760,039 bytes、4,050行，SHA-256为`AFA8C02007DE6AA6C9CF02998F7413F31B460842556DAE0CFEB5E1E382077EA8`，保留在Git外且不得覆盖。下一步使用全新run ID执行新官方Q4_K_M的一条query、C0/C1/C2各3次随机顺序dry-run；仍为`formal_evidence: false`。

## 2026-08-31补充：015完整会话等待积分

`E1_devtemp_dryrun_015`首次完成新官方Q4_K_M下的完整采集会话：Radxa runner报告9/9成功；Windows collector记录65,399 sample、654 environment、20 marker，`invalid=0`、`invalid_serial=0`、`invalid_marker=0`，`partial_serial_at_shutdown=1`。20个marker恰好由一对65秒空闲标记与9条查询的起止边界组成，不存在010的重复空闲对。

完整raw为`D:\sci-exp-data\E1_20260830\INA226_E1_devtemp_dryrun_015.full.jsonl`，28,950,062 bytes、66,163行，SHA-256为`18684A34F4E7433174D3366343592C7EDD9CA53EF0318019F81D0D2178205027`，保留在Git外且不得覆盖。当前状态仅为`candidate_pending_device_clock_integration`：仍须同步Radxa的`results/E1_devtemp_dryrun_015.jsonl`，核对内部marker错误，并以设备时钟积分确认9/9 `external_meter_valid=true`后才能判定非正式dry-run通过。

## 015积分结果与prompt cache异常

runner审计为9条`status=ok`且0条`external_marker_errors`。设备时钟积分得到9/9有效、空闲功率`1.3411159715014278W`；空闲区间65.391秒、6,495样本，最大设备间隔16.021ms。所有查询区间均无欠压、饱和、shunt近限或固件integration gap，merged中9/9 `external_meter_valid=true`。

派生文件：

- `results/E1_devtemp_dryrun_015.jsonl`：83,289 bytes，SHA-256 `49F36B33CF6CDD8EACE455F09730A90AA7246A22F600A0EDD6196A49A663F514`；
- `results/E1_devtemp_dryrun_015.deviceclock.energy.jsonl`：8,854 bytes，SHA-256 `073577E5F3A4F61A444B47BACD15DA014DD4AB644EF199364493771340A0EDBC`；
- `results/E1_devtemp_dryrun_015.deviceclock.meter_merged.jsonl`：88,927 bytes，SHA-256 `98DEE266338543D98CDDEB3CF01797218BC439D0B23B4613140B51D5458E5008`。

但015不能作为最终dry-run通行证。C2三次生成token均为30，首个C2耗时/能耗为67.130秒/141.856J，后两次仅11.627秒/19.963J与11.453秒/19.673J；C1首个长提示运行也明显高于后续重复。冻结`llama.cpp b9627`文档与源码确认server的prompt cache默认开启，重复公共前缀时只计算未见suffix，并明确提示可能产生非位级确定结果。015的变化符合跨运行KV复用，而不是功率链故障。

处置：`scripts/start_llama_server.sh`新增`--no-cache-prompt`，正式配置清单冻结`prompt_cache=false`。必须重启服务并用全新run ID重做9-run；015保留为`measurement_valid_but_prompt_cache_contaminated_diagnostic_only`，不得进入配置能耗统计或Oracle。

首次按该修改重启后，进程命令行虽包含`--no-cache-prompt`，启动日志仍明确报告全局prompt cache为`enabled`、上限8,192MiB，并保存idle slots；冻结版本存在请求级cache开关和server全局cache-ram两层。按同一启动日志与冻结README的明确说明，启动脚本进一步加入`--cache-ram 0`及`--no-cache-idle-slots`。016只能在启动日志明确显示`prompt cache is disabled`后开始。

## 016：服务未保持运行，诊断失败

016采集器获得23,742 sample、238 environment、20 marker，`invalid=0`、`invalid_serial=0`、`invalid_marker=0`、`partial_serial_at_shutdown=1`；但Radxa runner为0/9成功，9条均为连接`127.0.0.1:8080`被拒绝，且marker错误为空。用户确认执行016时没有保持`scripts/start_llama_server.sh`前台运行。

完整raw为`D:\sci-exp-data\E1_20260831\INA226_E1_devtemp_dryrun_016.full.jsonl`，10,491,368 bytes、24,048行，SHA-256为`C693C3987ED712696DCA5CBBE973173928F97D15587DB0749EC92BE9A11DB210`。该raw与`results/E1_devtemp_dryrun_016.jsonl`只作失败诊断，禁止积分、回填或覆盖。下一轮必须使用新run ID，并在启动采集器前同时确认`pgrep`含三项禁缓存参数及`/health`成功；服务终端须在整轮保持前台运行。

## 017：服务再次被Ctrl+C终止

017物理流获得26,201 sample、262 environment、20 marker，三项无效计数均为0；runner仍为0/9成功。服务终端提供了决定性日志：`^C ... cleaning up before exit`，证明llama-server被用户按`Ctrl+C`主动终止。进程启动时已明确显示prompt cache disabled，故本轮不支持“禁缓存参数导致服务故障”的解释。

完整raw为`D:\sci-exp-data\E1_20260831\INA226_E1_devtemp_dryrun_017.full.jsonl`，11,579,959 bytes、26,534行，SHA-256为`6A3CE0329910DA030E2EA935996648D1425BD60CF784375766865EA7182D60A3`。017只作服务生命周期失败诊断，不积分、不覆盖。下一轮改用`nohup`后台常驻并保存服务日志，先验证进程与health，再启动采集器；实验结束后以明确PID停止服务。

## 018：无缓存后台服务完整候选会话

使用`nohup`启动PID 33876并写入独立服务日志；采集前确认进程包含`--no-cache-prompt --cache-ram 0 --no-cache-idle-slots`，启动日志显示`prompt cache is disabled`。018 runner为9/9成功，结束后同一PID仍存在且`/health`成功。Windows collector记录101,957 sample、1,020 environment、20 marker，`invalid=0`、`invalid_serial=0`、`invalid_marker=0`、`partial_serial_at_shutdown=1`。

完整raw为`D:\sci-exp-data\E1_20260831\INA226_E1_devtemp_dryrun_018.full.jsonl`，45,174,078 bytes、103,124行，SHA-256为`7C770E2D49D1B21F3CE414527FAA4866A1ED408F5AC67828010A6C1C4BF7C9FC`，保留在Git外且不得覆盖。当前仅登记为`candidate_pending_device_clock_integration`；须同步9行runner结果、确认0个marker错误并完成9/9设备时钟积分后，才能判定无缓存dry-run是否通过。

## 2026-08-31最终处置：018通过

018后续审计确认runner 9/9成功、0条marker错误、设备时钟积分9/9有效且merged中9/9
`external_meter_valid=true`。服务在runner后仍健康，随后按PID 33876正常停止；最终服务日志154行、
14,147 bytes、SHA-256 `1AEB4B4E3E9E4D94EA88FC952A3233A3B469DA3692C2FDE7647E6E7746BC1018`，
末行是正常清理。018状态升级为`passed_nonformal_dry_run`；完整结论与派生文件哈希见
[`SCER-E1-260831-001_无缓存新模型完整dry-run通过.md`](SCER-E1-260831-001_无缓存新模型完整dry-run通过.md)。
