# Radxa ZERO 3W首次实机运行记录 v1.0

记录日期：2026-07-29  
设备：Radxa ZERO 3W，Linux aarch64，约7694 MiB可用内存，4个CPU线程  
工程目录：`/home/radxa/sci-exp`

## 1. 结论

本次完成了目标设备上的 ARM64 `llama-server` 增量构建、安装、动态依赖检查、
GGUF加载、HTTP健康检查和 Chat API 最小生成测试。以下事项尚未完成：

- 项目 Python 生成器仍使用裸 `/completion`，与当前 Chat GGUF 不兼容；
- `radxa.smoke.json`只验证extractive/hashing开发链路，未调用GGUF或BGE；
- ESP32-S3损坏，INA226真实功率和能耗积分不可用；
- 当前400条为development gold，不能进入确认性正式训练、校准或测试；
- GGUF加载时报告缺少pre-tokenizer类型，正式转换来源和生成质量仍需审计。

因此，本次结果属于**首次实机工程验证**，不是论文主实验结果。

## 2. ARM64构建记录

冻结源码：

```text
llama.cpp tag = b9627
commit = 53bd47ea5b46335cf6125a674af378ac422fc392
build type = Release
architecture = aarch64
compiler = GNU 10.2.1
```

构建过程中C++主体曾多次被人工中断，但CMake对象文件可增量复用。核心目标
`llama`完成后，Hugging Face UI资源下载出现超时。通过以下缓存选项禁止联网：

```text
LLAMA_BUILD_UI=OFF
LLAMA_USE_PREBUILT_UI=OFF
```

旧UI缓存随后因缺少`loading.html`被新版`llama-ui-embed`拒绝。将
`tools/ui/static/loading.html`复制到
`build-e1-release/tools/ui/dist/loading.html`后，最终完成：

```text
[100%] Built target llama-server
version: 1 (53bd47e)
built with GNU 10.2.1 for Linux aarch64
```

安装记录：

```text
path = /home/radxa/sci-exp/bin/llama-server
size = 15576 bytes（ls显示约16 KiB）
sha256 = 4d157af0eb8c136ffa845065c7ed8d749ce40b048037c19696254a6344ae16b9
built_at_utc = 2026-07-29T12:13:23Z
```

## 3. 运行时依赖边界

`ldd /home/radxa/sci-exp/bin/llama-server`确认主要共享库来自：

```text
/home/radxa/sci-exp/third_party/llama.cpp-b9627/build-e1-release/bin
```

包括：

- `libllama-server-impl.so`
- `libllama-common.so.0`
- `libmtmd.so.0`
- `libllama.so.0`
- `libggml.so.0`
- `libggml-base.so.0`
- `libggml-cpu.so.0`

因此16 KiB入口程序不是自包含二进制。当前不得删除
`third_party/llama.cpp-b9627/build-e1-release`，也不得只复制入口程序作为复现包。

CMake未找到OpenSSL，当前服务仅验证HTTP：

```text
http://127.0.0.1:8080
```

这不影响板内离线HTTP实验，但不得声称运行时已提供HTTPS。

## 4. 模型加载记录

模型：

```text
/home/radxa/sci-exp/models/qwen1_5-0_5b-chat-q4_k_m.gguf
文件大小约389 MiB
```

实测内存投影约496 MiB，服务以4线程、4个slot、每slot上下文4096启动。日志显示：

```text
n_ctx_seq (4096) < n_ctx_train (32768)
```

这是有意降低运行上下文，不是加载失败。

模型加载还报告：

```text
missing pre-tokenizer type
GENERATION QUALITY WILL BE DEGRADED
```

这不是可忽略的正式质量结论。当前模型可以用于接口和开发先导，但正式模型锁定前
必须补齐GGUF来源、转换版本和tokenizer元数据，或更换无此警告的可追溯GGUF。

## 5. 服务与接口实测

健康检查：

```bash
curl http://127.0.0.1:8080/health
```

返回：

```json
{"status":"ok"}
```

裸`/completion`对中文问题返回：

```text
content = ""
tokens_predicted = 1
stop_type = eos
```

因此裸补全门禁失败。

`/v1/chat/completions`使用`system`和`user`消息后返回非空assistant正文，说明模型
和聊天模板能够工作。但首次回答把“拨打110”列为地震首要行动，只能作为链路
证据，不能作为安全质量通过证据。

当前代码差异：

| 项目 | 当前值 | 所需修复 |
|---|---|---|
| `configs/radxa.experiment.json` | `/completion` | 改为Chat API或增加接口类型配置 |
| `LlamaServerGenerator`请求 | 顶层`prompt` | 使用`messages` |
| `LlamaServerGenerator`解析 | 顶层`content` | 读取`choices[0].message.content` |
| 空响应处理 | 已抛出异常 | 保留并增加自动化测试 |

在代码和配置同步修复前，不运行第11步全量实验。

## 6. Python与smoke实测

Radxa执行：

```text
python -m unittest discover -s tests -v
Ran 52 tests
OK
```

smoke结果：

```json
{
  "runs": 12,
  "successful": 12,
  "failed": 0,
  "output": "/home/radxa/sci-exp/results/radxa_smoke_runs.jsonl"
}
```

`radxa.smoke.json`使用`extractive`生成器、`hashing_development`检索和空功率路径，
所以不能用这12次成功证明GGUF、BGE或能耗链路已经通过。

## 7. 功率硬件状态

ESP32-S3在本次实机阶段已损坏，替换件正在采购。当前允许继续：

- 单元测试和extractive smoke；
- Chat API适配与自动化测试；
- BGE ARM64加载和dense检索验证；
- 非测试查询上的少量开发先导；
- 数据、标注和审计准备。

当前必须暂停：

- INA226三点校准和60分钟稳定性测试；
- 正式`energy_j`积分；
- 正式`resource_profile.json`；
- 能耗约束路由、Radxa主实验和最终测试。

开发诊断允许显式使用`--allow-missing-energy`，但输出文件名和报告必须标记
`development`，且不得事后升级为正式论文结果。

## 8. 下一执行门禁

1. 修复并测试Chat API适配。
2. 验证BGE ARM64真实dense检索。
3. 使用非测试查询完成预热和30--150条C0--C3先导。
4. 更换ESP32-S3，核对开发板型号、GPIO和固件。
5. 完成INA226零点、0.5A/1A/2A三点校准及连续稳定性检查。
6. 重新做含真实能耗的先导，稳定后才讨论正式训练和校准。

