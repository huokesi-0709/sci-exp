---
schema_version: experiment-log-v1.0
exp_id: SCER-E1-260831-001
system: SC-EA-RAG
stage: E1
experiment_type: 官方Q4_K_M无缓存单query随机顺序功率dry-run
date: 2026-08-31
timezone: Asia/Shanghai
status: passed_nonformal_dry_run
formal_evidence: false
operator: user
device: Radxa ZERO 3 + ESP32-S3/INA226/SHT31
run_id: E1_devtemp_dryrun_018
---

# E1：无缓存新模型完整dry-run通过

## 结论

018通过最终非正式运行时与功率链dry-run：C0/C1/C2各3次，共9次均成功；runner无外部marker错误，
设备时钟积分9/9有效，merged中9/9 `external_meter_valid=true`。llama-server在整个runner结束后仍健康，
并在审计完成后按明确PID正常停止。该结果只证明正式E1流程已具备运行条件，不能替代Dev-Temp
35条query × 3配置 × 3重复的315次正式运行，也不进入Oracle或论文统计。

## 冻结运行条件

- 模型：`/home/radxa/sci-exp/models/qwen1_5-0_5b-chat-official-4d14e384-q4_k_m-r2.gguf`
- 模型SHA-256：`EF63EBD112199C99E53B394FC6C9F10F27927B565258738FCF99A91421EA31A8`
- llama-server SHA-256：`4D157AF0EB8C136FFA845065C7ED8D749CE40B048037C19696254A6344AE16B9`
- 运行参数：`--ctx-size 4096 --no-cache-prompt --cache-ram 0 --no-cache-idle-slots --threads 4`
- 启动方式：`nohup`后台常驻，PID `33876`，独立服务日志；启动日志明确显示
  `prompt cache is disabled`。
- Windows采集：COM18，921600 baud，UDP监听`0.0.0.0:8765`。
- Radxa marker目标：`192.168.10.11:8765`。
- 查询：`data/inference_splits_stratified_v2/valid.jsonl`首条；固定随机seed由
  `configs/E1_devtemp_v1.json`提供。
- 已知运行时观察：加载时仍记录token 128247 `</s>` control-type覆盖警告；未静默删除，后续人工质量
  审查仍须保留。

实际5V/3A充电头的标签型号、额定输出和本批次输入线标识尚未由用户提供，因此本日志不猜测填写；它们
仍是正式E1开始前必须补记并冻结的条件。精确墙钟开始/结束时间未单独记录，证据以run ID、设备时钟、
marker边界和文件哈希关联。

## 关键执行命令

Radxa后台启动服务：

```bash
cd /home/radxa/sci-exp
mkdir -p /home/radxa/sci-exp/logs/runtime
nohup ./scripts/start_llama_server.sh \
  > /home/radxa/sci-exp/logs/runtime/llama_server_nocache_018.log \
  2>&1 &
```

Radxa空闲基线与9-run：

```bash
export PYTHONPATH=/home/radxa/sci-exp/src
export SCI_EXP_METER_HOST=192.168.10.11

.venv/bin/python scripts/发送功率实验标记.py \
  --event idle_start --run-key E1_devtemp_dryrun_idle_018 \
  --host "$SCI_EXP_METER_HOST" --port 8765
sleep 65
.venv/bin/python scripts/发送功率实验标记.py \
  --event idle_end --run-key E1_devtemp_dryrun_idle_018 \
  --host "$SCI_EXP_METER_HOST" --port 8765

.venv/bin/python -m sci_exp.cli run \
  --config configs/E1_devtemp_v1.json \
  --queries /tmp/E1_devtemp_onequery_20260831_018.jsonl \
  --output results/E1_devtemp_dryrun_018.jsonl
```

Windows采集与设备时钟积分：

```powershell
.\.venv\Scripts\python.exe .\scripts\采集INA226串口功率.py `
  --serial COM18 `
  --baud 921600 `
  --output 'D:\sci-exp-data\E1_20260831\INA226_E1_devtemp_dryrun_018.full.jsonl' `
  --marker-host 0.0.0.0 `
  --marker-port 8765

.\.venv\Scripts\python.exe .\scripts\整合INA226查询能耗.py `
  --meter-log 'D:\sci-exp-data\E1_20260831\INA226_E1_devtemp_dryrun_018.full.jsonl' `
  --output results\E1_devtemp_dryrun_018.deviceclock.energy.jsonl `
  --runs results\E1_devtemp_dryrun_018.jsonl `
  --merged-runs-output results\E1_devtemp_dryrun_018.deviceclock.meter_merged.jsonl
```

服务结束审计：

```bash
kill 33876
sleep 3
pgrep -a llama-server
wc -l -c logs/runtime/llama_server_nocache_018.log
sha256sum logs/runtime/llama_server_nocache_018.log
tail -n 20 logs/runtime/llama_server_nocache_018.log
```

`pgrep`无输出；服务日志末行是`operator(): cleaning up before exit...`，无崩溃或异常退出证据。

## 原始与派生证据

完整高频raw保存在Git外，禁止覆盖：

- `D:\sci-exp-data\E1_20260831\INA226_E1_devtemp_dryrun_018.full.jsonl`
- 45,174,078 bytes，103,124行；101,957 sample、1,020 environment、20 marker；
- `invalid=0`、`invalid_serial=0`、`invalid_marker=0`、`partial_serial_at_shutdown=1`；
- SHA-256：`7C770E2D49D1B21F3CE414527FAA4866A1ED408F5AC67828010A6C1C4BF7C9FC`。

Git内派生证据：

- `results/E1_devtemp_dryrun_018.jsonl`：9行，82,790 bytes，SHA-256
  `F9C66857C5BCE78D7242E5EB1E59C8A09ED18EDA53715B1B62E8588DB9E059D6`；
- `results/E1_devtemp_dryrun_018.deviceclock.energy.jsonl`：9行，8,821 bytes，SHA-256
  `82D830F8EFE1CF01C6463E73D153B072CED8D71B3A4E89556873C125721D7B95`；
- `results/E1_devtemp_dryrun_018.deviceclock.meter_merged.jsonl`：9行，88,398 bytes，SHA-256
  `0FD5450BFC61DD549A6332797B8ABFB0C6C96CFEE681A3AD5915BB3BA1DBD467`。

Radxa服务日志保存在Radxa工作区，不提交高频服务输出到Git：

- `/home/radxa/sci-exp/logs/runtime/llama_server_nocache_018.log`
- 154行，14,147 bytes；SHA-256
  `1AEB4B4E3E9E4D94EA88FC952A3233A3B469DA3692C2FDE7647E6E7746BC1018`。

## 积分与重复性结果

- 空闲基线：6,498样本、65.422秒、`1.3441157696693329W`；空闲最大设备间隔`16.021ms`。
- 查询积分：9/9有效；查询区间最大设备间隔`16.827ms`，低于30ms冻结门槛。
- 质量标志：无欠压、过流/近限或固件integration gap。
- 每个配置内三次回答哈希一致。
- C0：能耗约`19.524/19.696/23.033J`，能耗CV `7.784%`；时延CV `11.35%`。
- C1：能耗约`256.598/256.606/259.584J`，能耗CV `0.546%`；时延CV `0.082%`。
- C2：能耗约`294.037/295.735/296.453J`，能耗CV `0.343%`；时延CV `0.117%`。

C1/C2在禁用两层prompt cache后不再出现015那种首轮与后续重复相差数倍的缓存污染。C0残余波动保留
为正式随机顺序与硬件状态记录中的监测项，不在dry-run阶段解释为配置效应。

## 接受判定与下一动作

接受门槛全部满足：runner 9/9成功、marker错误为0、collector三类invalid为0、设备时钟积分9/9有效、
9/9 `external_meter_valid=true`、服务全程存活且正常退出。因此018标记为
`passed_nonformal_dry_run`。

下一步不再继续重复单query dry-run。应先补记供电源与输入线身份，冻结正式315次运行清单、唯一文件名、
随机顺序和盲法双审/仲裁材料，再以新session开始正式E1 Dev-Temp运行。

## 后续状态更新

用户随后已提供UGREEN X336充电头与15cm铜输入线信息，并确认整轮E1保持供电链不变；该前置项已在
[`SCER-E1-260831-002_正式供电源与接线冻结.md`](SCER-E1-260831-002_正式供电源与接线冻结.md)
中冻结为`E1-POWER-CHAIN-01`。当前下一门槛仅为315次运行清单与盲法双审/仲裁材料冻结。
