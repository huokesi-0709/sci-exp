# Radxa部署与正式实验清单 v2.0

## 1. 目录关系

Windows目录`D:\projects\RAG-sci\docs\sci-exp`是主副本；Radxa运行目录固定为
`/home/radxa/sci-exp`。不要把Windows的`.venv`复制到Radxa，它包含Windows二进制，
在ARM64 Linux上不可用。`.pytest_cache`、PlatformIO `.pio`和历史结果也不进入部署包。

## 2. 在Windows生成部署包

```powershell
Set-Location D:\projects\RAG-sci\docs\sci-exp
.\scripts\打包Radxa部署包.ps1 `
  -OutputArchive D:\projects\RAG-sci\outputs\sci-exp-radxa.tar.gz
```

脚本输出归档SHA-256。归档保留数据、模型、源码、配置、测试以及冻结的llama.cpp源码，
但排除平台不兼容的虚拟环境和缓存。

将归档复制到Radxa后，在Radxa执行：

```bash
mkdir -p /home/radxa/sci-exp
tar -xzf /home/radxa/sci-exp-radxa.tar.gz -C /home/radxa/sci-exp
cd /home/radxa/sci-exp
bash scripts/setup_radxa.sh
```

该解压流程不会主动删除目标目录中已有的ARM64构建产物。若目标目录已存在同名文件，
tar会覆盖这些明确的同名文件；正式更新前应先保存`results/`和校准日志。

## 3. Radxa运行时

若`bin/llama-server`尚不存在，在Radxa本机从冻结源码构建：

```bash
cd /home/radxa/sci-exp
bash scripts/构建并锁定ARM64_llama_server.sh
```

Windows目录中的`bin/`没有ARM64可执行文件是正常的，不能把Windows程序改名后放入。

## 4. Windows测量电脑

烧录ESP32固件后，确认I2C扫描同时出现`0x40`和`0x44`，然后保持采集器运行：

```powershell
python scripts\采集INA226串口功率.py `
  --serial COM6 `
  --output data\raw\runs\INA226_SHT31_会话001.jsonl `
  --marker-host 0.0.0.0 `
  --marker-port 8765
```

Windows防火墙只允许局域网接口UDP 8765。不要把公网接口开放为任意来源。

## 5. Radxa正式运行前

```bash
cd /home/radxa/sci-exp
export SCI_EXP_METER_HOST=<Windows测量电脑的局域网IP>
bash scripts/collect_device_info.sh
bash scripts/run_smoke_test.sh
python scripts/检查Radxa正式实验就绪.py \
  --root /home/radxa/sci-exp \
  --output results/Radxa正式实验就绪检查_v2.0.json
```

还必须人工确认：

- Windows采集器能收到Radxa的`query_start/query_end`并返回ACK；
- ESP32功率流实测有效频率不低于100Hz；
- SHT31位置固定且没有被板卡/充电器直接加热；
- Radxa thermal zone类型、CPU governor、散热器/风扇状态已记录；
- 模型、协议库、配置、数据分区和校准阈值哈希已经冻结；
- 当前数据确实是允许使用的Gold Calibration/Test，而不是development gold。

## 6. 正式运行和能耗回填

```bash
export SCI_EXP_METER_HOST=<Windows测量电脑的局域网IP>
bash scripts/run_radxa_formal_tests.sh
```

运行后把Radxa的`results/radxa_*_runs.jsonl`复制回Windows，再执行：

```powershell
python scripts\整合INA226查询能耗.py `
  --meter-log data\raw\runs\INA226_SHT31_会话001.jsonl `
  --output data\processed\INA226_查询能耗_会话001.jsonl `
  --runs results\radxa_experiment_runs.jsonl `
  --merged-runs-output results\radxa_experiment_runs_with_energy.jsonl
```

统计和资源画像只能使用`*_with_energy.jsonl`中`external_meter_valid=true`的运行。
原始ESP32日志、未合并Radxa日志和合并日志三者都要保留。
