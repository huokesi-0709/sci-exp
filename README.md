# sci-exp：离线应急 RAG 实验工程

## 2026-08-19 E0–E8实验框架

- E0功率链、E1配置异质性、E2安全校准、E3三类能耗模型、E4主实验、E5 Router
  成本、E6硬件状态压力、E7跨设备和E8 query-level bootstrap的冻结设计见
  `docs/E0-E8实验设计与执行协议_v1.0.md`；
- Static Mean Energy已作为正式强基线，并与No-State和State-Aware能耗预测并列；
- 路由器现在可在决策时读取Radxa SoC温度、CPU频率、cooling state和可用内存，
  并通过`SCI_EXP_ENERGY_BUDGET_J`使用available energy budget；
- SHT31只作为环境温湿度参照，不作为Radxa device temperature；
- Windows到Radxa建议使用`scripts/sync_to_radxa.sh`增量同步。该入口不使用
  `--delete`，不会清除Radxa上的ARM64构建、结果或校准原始日志。

## 2026-08-11 SC-EA-RAG重构状态

- 当前实施口径改为输入-配置级`y_trigger/y_miss/y_quality`多头风险、独立校准和
  硬约束能耗选择，见`docs/研究协议_v3.0_SC-EA-RAG重构.md`；
- Radxa真实生成配置已切换到`/v1/chat/completions`，C0/C1/C2分别使用128/256/512
  token输出上限并记录结构化配置属性；
- ESP32固件已改为GPIO4/GPIO5共用INA226（0x40）和SHT31（0x44），功率目标100Hz、
  环境温湿度1Hz；Radxa另行记录SoC温度、CPU频率和thermal cooling state；
- 外部INA226积分可按`run_key`回填Radxa运行日志，正式配置要求通过环境变量
  `SCI_EXP_METER_HOST`指定Windows采集电脑；
- Windows的`.venv`、PlatformIO缓存和历史结果不得复制到ARM64设备，部署步骤见
  `docs/Radxa部署与正式实验清单_v2.0.md`；
- 代码和固件已通过本地测试/编译，但实物接线、I2C扫描、三点校准、UART4启用、
  正式Gold标注和主实验仍是阻断门禁。

## 2026-07-29 Radxa首次实机状态

- Radxa ZERO 3W 已完成 ARM64 `llama-server` Release构建，版本
  `1 (53bd47e)`，安装入口SHA-256为
  `4d157af0eb8c136ffa845065c7ed8d749ce40b048037c19696254a6344ae16b9`；
- 服务已加载389 MiB候选GGUF，`/health`正常，`/v1/chat/completions`可以生成；
- 裸`/completion`对该Chat GGUF返回空正文；当前Python生成器和正式配置尚未
  适配Chat API，真实LLM先导不得启动；
- Radxa本机52项测试通过，extractive smoke为12/12成功；该smoke不调用GGUF、
  BGE或物理功率链；
- ESP32-S3损坏、替换件在途，INA226校准、真实`energy_j`、正式资源画像和
  Radxa主实验暂停；
- ARM64入口程序动态依赖`third_party/llama.cpp-b9627/build-e1-release/bin`
  中的共享库，不得删除该构建目录。

详细记录见`docs/Radxa_ZERO3W首次实机运行记录_v1.0.md`，执行门禁见
`docs/新手实验执行流程教程_v1.0.md`。

## 2026-07-28 正式数据状态

以下状态替代本文后续保留的先导阶段历史说明：

- 13个中文来源的64条协议切块已形成受控内部正式库：
  `data/processed/protocols.jsonl`；
- 开发gold已扩展到400条、65个`source_group_id`，包含102条L3、
  105条C3和30条域外对照；
- 400条当前明确标记为`development_gold`，不可进入确认性
  `cal_op`/`cal_ch`/`test_op`/`test_ch`，六分区名称仅保留开发阶段分组；
- 新增304条已完成双审和仲裁；
- 开发阶段六分区已冻结且无组间泄漏；确认性v2.0六分区需在3,600条形成后重建；
- Windows正式预处理接受400条、隔离0条；
- Windows抽取式工程验证共400次运行全部成功，但不是论文结果；
- Radxa数据与脚本已就绪；目标架构`llama-server`和基础设备信息已在
  2026-07-29核验，仍缺正式GGUF质量锁定、Chat API代码适配、BGE实机验证和
  物理功率路径。

完整交接见`docs/正式400条扩展双审六分区与实验交接报告_v1.0.md`。

该目录是Radxa实验工程的Windows主副本，但不能把其中Windows专用缓存原样复制。
Windows路径为：

```text
D:\projects\RAG-sci\docs\sci-exp
```

复制到 Radxa 后的目标路径为：

```text
/home/radxa/sci-exp
```

推荐使用`powershell scripts/打包Radxa部署包.ps1`生成排除`.venv/.pio`的归档，
不要拖拽整个目录覆盖设备。

## 当前已包含

- 统一数据 schema 与校验；
- 防泄漏分组划分；
- 纯 Python BM25 检索；
- C0 无检索、C1 单步 RAG、C2 复杂 RAG、C3 安全回退；
- 抽取式 smoke 后端和本地 llama.cpp server 后端；
- 可训练的逐配置逻辑风险模型与校准安全约束路由；
- 风险阈值校准；
- 行动完整率、严重失效、coverage 和资源指标；
- Linux/Radxa 温度、内存、负载和可选功率路径采样；
- 全配置实验运行器；
- Windows 与 Radxa 配置；
- 盲法人工判定合并流程、样例协议、查询和单元测试。
- 可复现查询/资源日志预处理、异常隔离、稳健异常值标记和文件哈希日志。
- 研究协议 v1、旧项目资产审计、120 条先导候选查询和当前任务重新标注模板。
- 7份权威协议候选、下载哈希报告、1382条原始候选切块和内容风险审计。
- 5份中文来源的50条章节级精选候选切块，以及24条先导查询的机器证据建议与双审表。

## 当前不包含

- 可公开再分发且转换链完整的正式大模型权重（工程内仅有内部候选GGUF）；
- 受许可证限制的公开数据集正文；
- 尚未取得的真实应急协议数据；
- 已完成实机校准并可用于正式结果的外部功耗计链路；
- 已训练的正式风险模型和真实 Radxa 资源画像。

这些资产通过 `manifests/` 和 `models/` 接入，不能用 smoke 样例替代正式实验。

## 当前先导数据

当前已从作者旧项目的 RAIR-RAG gold 中确定性抽取 120 条历史查询，位置为：

```text
data/raw/queries/旧项目先导候选查询_v0.1.jsonl
```

对应重新标注模板为：

```text
data/annotations/先导查询重新标注模板_v0.1.csv
```

这些记录只是候选池。每条记录均设置
`formal_training_eligible=false`，且未分配正式 split、未继承旧项目证据标签，
不能用于论文训练、校准或测试。必须先取得并切块当前研究采用的权威协议，再完成
证据绑定、行动槽位和 L0–L3 双人重新标注。

如需从只读旧项目重新生成同一批候选数据：

```powershell
python scripts\import_legacy_monibox_pilot.py `
  --input D:\projects\monibox-Y\monibox\benchmarks\rair_rag\data\gold\rair_gold_all_v2.jsonl `
  --output data\raw\queries\旧项目先导候选查询_v0.1.jsonl `
  --annotation-template data\annotations\先导查询重新标注模板_v0.1.csv `
  --report data\logs\旧项目先导数据导入报告_v0.1.json `
  --seed 42 `
  --max-per-canonical 4
```

研究边界见 `docs/研究协议_v1.md`，可借鉴范围见
`docs/旧项目可借鉴资产审计.md`。

## 当前候选协议

已取得7份WHO及中国官方材料并生成1382条候选切块，但全部仍为 `draft`：

```text
data/raw/protocols/协议来源登记_v0.1.jsonl
data/processed/候选协议切块_v0.1.jsonl
data/logs/候选协议切块审计_v0.1.json
```

自动审计已确认当前候选库不具备正式使用资格，原因包括内容尚未双人审查、
许可证尚未确认，以及WHO BEC PDF存在文本替换字符。正式实验配置仍不得指向
该候选切块文件。

在原始候选库之上，已通过可复现章节规则生成50条精选候选切块：

```text
data/raw/protocols/协议章节筛选规则_v0.1.jsonl
data/processed/协议派生登记_v0.1.jsonl
data/processed/精选候选协议切块_v0.1.jsonl
data/logs/协议派生候选报告_v0.1.json
data/logs/精选候选协议切块审计_v0.1.json
```

WHO BEC因专业适用边界和提取乱码、WHO PFA因当前仅有英文版，暂不进入中文
直接检索。精选切块仍为 `draft`、待双人内容审查和许可证确认，不能作为正式库。

已从120条历史候选中按意图配额选择24条，并生成机器证据建议和空白双审表：

```text
data/annotations/先导24条证据绑定候选_v0.1.jsonl
data/annotations/先导24条证据双审表_v0.1.csv
docs/先导24条证据绑定说明_v0.1.md
```

机器阶段预设4条证据空白，分别用于缺水、心理困扰、低电量和域外问题。两轮
审查又确认“被困很久且口渴”因灾种不明不能跨场景绑定，最终证据空白增至5条。

24条现已完成两轮审查和仲裁：

```text
data/annotations/先导24条双轮审查决定_v0.1.json
data/annotations/先导24条证据仲裁结果_v0.1.jsonl
data/logs/先导24条双审一致性报告_v0.1.json
docs/先导查询风险与行动标注手册_v0.1.md
docs/先导证据覆盖缺口_v0.1.md
```

风险等级和回退判断的Cohen's kappa分别为1.000和0.753，证据集合平均
Jaccard为0.778。仲裁后19条有至少部分证据，5条无直接证据。协议内容和
许可证仍未批准，因此这些记录继续保持 `formal_training_eligible=false`。

## Windows 快速验证

在 PowerShell 中：

```powershell
Set-Location D:\projects\RAG-sci\docs\sci-exp
$env:PYTHONPATH = "D:\projects\RAG-sci\docs\sci-exp\src"
python -m unittest discover -s tests -v
python -m sci_exp.cli smoke --config configs\windows.smoke.json
python -m sci_exp.cli route --config configs\windows.smoke.json `
  --output results\windows_routed_smoke.jsonl
```

正式查询数据预处理：

```powershell
.\scripts\run_preprocess.ps1 `
  -Queries data\raw\public_datasets\queries.jsonl `
  -Seed 42 `
  -AugmentTrainCopies 0
```

如果没有安装为包，命令脚本会自动设置 `PYTHONPATH`：

```powershell
.\scripts\run_smoke_test.ps1
```

## Radxa 快速验证

复制后：

```bash
cd /home/radxa/sci-exp
bash scripts/setup_radxa.sh
bash scripts/collect_device_info.sh
bash scripts/run_smoke_test.sh
bash scripts/run_preprocess.sh data/raw/public_datasets/queries.jsonl 42 0
```

## 正式实验闭环

以下文件就绪后，运行 `bash scripts/train_calibrate_route.sh`：

- `data/processed/protocols.jsonl`
- `data/splits/train.jsonl`
- `data/splits/cal_op.jsonl`
- `data/splits/test_op.jsonl`
- `data/splits/test_ch.jsonl`
- `models/*.gguf`
- `bin/llama-server`
- Radxa 可读的物理功率路径或外部功耗计采样接口

脚本按顺序执行：

1. 穷举 C0–C3 得到训练运行；
2. 合并盲法专家的误触发、必要动作遗漏和最低充分性标签；
3. 训练逐配置多头风险模型；
4. 从 Radxa 实测运行建立时延、内存、能耗画像；
5. 在独立校准集上产生风险分数并校准阈值；
6. 在独立测试集上做安全约束逐查询配置选择。

人工判定模板在 `data/annotations/adjudication_template.jsonl`。未提供人工标签时
脚本会停止，不会把 smoke 启发式指标冒充正式风险标签。

## 本地模型

正式生成后端使用本地 `llama-server`。截至2026-08-11，Radxa正式配置和Python
生成器已使用`http://127.0.0.1:8080/v1/chat/completions`，并解析OpenAI兼容的
`choices[0].message.content`和`usage`字段。启动服务器的方式为：

```bash
MODEL_PATH=/home/radxa/sci-exp/models/your-model.gguf \
  bash scripts/start_llama_server.sh
```

模型文件建议放在：

```text
/home/radxa/sci-exp/models/
```

## 能耗

只有当配置了可读取的功率路径或外部功耗计时，运行器才会输出
`energy_j`。没有功率信号时该字段为 `null`，不能用时延、FLOPs 或
token 数冒充物理能耗。

可先运行 `bash scripts/detect_power_paths.sh` 查找内核暴露的候选功率节点，再将
确认过单位的路径写入配置中的 `telemetry.power_paths` 和 `power_scale`。

## 目录

```text
sci-exp/
├── configs/
├── data/
├── manifests/
├── models/
├── results/
├── scripts/
├── src/sci_exp/
├── bin/
├── docs/
└── tests/
```
