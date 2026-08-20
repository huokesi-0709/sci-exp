# Radxa 离线应急 RAG 实验执行规程

> 2026-08-11更新：Chat API适配、INA226 100Hz、SHT31环境采样、设备温度/频率/
> cooling state记录和外部能耗回填代码已完成。部署与当前门禁以
> `docs/Radxa部署与正式实验清单_v2.0.md`和
> `docs/研究协议_v3.0_SC-EA-RAG重构.md`为准；下方2026-07-29段落保留作历史记录。

> 2026-07-29 实机补充
>
> Radxa ZERO 3W已完成ARM64 `llama-server`构建、候选GGUF加载、健康检查和
> Chat API最小生成。当前仍不能启动正式实验：Python生成器使用裸
> `/completion`而该Chat GGUF只在`/v1/chat/completions`生成正文；ESP32-S3损坏
> 导致物理能耗链不可用；当前400条仍是development gold。完整记录见
> `docs/Radxa_ZERO3W首次实机运行记录_v1.0.md`。

## 1. 固定目录

Windows 主副本：

```text
D:\projects\RAG-sci\docs\sci-exp
```

Radxa 工作副本：

```text
/home/radxa/sci-exp
```

脚本、配置、数据、模型清单、运行输出和设备信息都必须位于这棵目录内。不要把
实验依赖散放到 `/home/radxa` 的其他位置；Windows `.venv`和`.pio`不进入部署包。

## 2. 复制后自检

```bash
cd /home/radxa/sci-exp
bash scripts/setup_radxa.sh
bash scripts/collect_device_info.sh
bash scripts/detect_power_paths.sh
bash scripts/run_smoke_test.sh
```

通过标准是：单元测试全通过、12 个 smoke 运行无错误、设备信息写入
`results/`。Smoke 数据和抽取后端只证明工程可运行。

## 3. 数据处理

原始协议必须记录机构、链接、版本、适用地区、有效期、权威等级和授权。查询按
`source_group_id` 分组划分，避免同一模板或同一事件的改写跨训练、校准和测试
集合：

```bash
python -m sci_exp.cli prepare-protocols \
  --registry data/raw/protocols/source_registry.jsonl \
  --output data/processed/protocols.jsonl

python -m sci_exp.cli validate \
  --protocols data/processed/protocols.jsonl \
  --queries data/processed/queries.jsonl

python -m sci_exp.cli split \
  --input data/processed/queries.jsonl \
  --output-directory data/splits \
  --seed 42
```

训练、操作校准、挑战校准、操作测试和挑战测试必须互斥。正式风险标签使用至少两名
盲法标注者；冲突项由第三人裁决，并保留标注者 ID。

## 4. 模型与服务

将 Radxa 架构对应的 `llama-server` 放入 `bin/`，GGUF 权重放入 `models/`，
并记录版本、量化和 SHA-256。启动服务：

```bash
chmod +x bin/llama-server
MODEL_PATH=/home/radxa/sci-exp/models/your-model.gguf \
  bash scripts/start_llama_server.sh
```

若在前台启动，保持当前SSH窗口运行，在第二个窗口执行客户端命令；第二个窗口
不得再次启动服务器。也可使用`nohup`后台启动。

必须分别检查三个门禁：

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"只回答：接口正常"}],"max_tokens":32,"temperature":0}'
python -m sci_exp.cli smoke --config configs/radxa.smoke.json
```

健康检查只证明进程在线，Chat请求只证明模型能生成，smoke只证明
extractive/hashing开发链路可运行。三者不能互相替代。

当前安装入口动态依赖
`third_party/llama.cpp-b9627/build-e1-release/bin`中的共享库，不得删除构建目录。
当前模型的裸`/completion`实测为空，因此在Python生成器和配置适配Chat API前，
不得运行全量C0--C3。

## 5. 主实验

先穷举 C0–C3，测得每个查询、配置和重复的输出、时延、内存、温度与物理能耗。
顺序由固定种子随机化，减少温升和缓存的顺序偏差。正式运行至少三次；在主实验前
单独做预热，预热数据不得混入统计结果。

Windows采集器开始运行后，在Radxa设置：

```bash
export SCI_EXP_METER_HOST=<Windows测量电脑局域网IP>
```

功率采样不低于100Hz；SHT31环境温湿度约1Hz；Radxa SoC温度、CPU频率和thermal
cooling state约5Hz。环境温度不得替代设备温度。

`train_calibrate_route.sh` 会在需要人工判定时明确停止。补齐
`data/annotations/train_adjudication.jsonl` 和
`calibration_adjudication.jsonl` 后重跑，即可继续训练、校准和测试路由。

## 6. 安全约束与防泄漏

- 风险模型只能使用训练/验证组；
- 阈值只能用独立 `cal_op`；
- `cal_ch` 用于检查分布偏移，不重新选阈值；
- `test_op`/`test_ch` 只做一次最终报告；
- 路由器只使用查询时可观测特征，不能读取 gold evidence、人工标签或测试结果；
- 没有满足校准风险上界、内存和时延约束的配置时必须选择 C3；
- 能耗只接受物理功率积分；没有信号时为 `null`。

## 7. 仍需在设备上确定

已实测设备为Radxa ZERO 3W、aarch64、约7694 MiB内存和4线程。仍需补齐系统
发行版、内核、存储介质、散热方式、环境温度、后台进程和性能调度策略。ESP32-S3
替换件到货后，还需重新核对板型与GPIO，完成INA226三点校准和连续稳定性测试。
这些信息会改变模型量化、线程数、内存预算和温控实验，因此目前只能锁定
“ARM64运行时可工作”，不能锁定正式模型质量和功耗配置。
