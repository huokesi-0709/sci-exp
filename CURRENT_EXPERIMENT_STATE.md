# 当前实验状态

更新时间：2026-09-02（Asia/Shanghai）

权威机器可读账本：[`docs/实验状态总览_v1.0.yaml`](docs/实验状态总览_v1.0.yaml)

## 一句话结论

E0已于2026-08-28通过正式验证：三点误差、冷/热ZERO与CAL、60分钟连续采样、三段空闲基线、
SYNC和100次标记RTT均有可核验的完整原始证据。该通过的适用边界是“厂家指标运行参考下的物理
能耗测量”：可以支撑固定测量链内的绝对能耗记录和相对物理能耗比较，但不得表述为计量溯源或
认可实验室校准。2026-08-26
电子负载、ANENG计量仪和转接链已实际接入，但首次三点前检的ZERO在真实负载下执行，且
重测r1虽已获得正确的冷/热ZERO，却仍在1A/2A出现全程欠压；该批数据不能用于校准，须
修正接线/供电后重测。
2026-08-27再次重测时，0.5A/1A/2A三点也全部欠压，平均Vbus约为4.65V/4.32V/3.64V；
压降对应约0.69Ω串联电阻。该轮还复用了旧`r1`文件名并覆盖了2026-08-26的外部raw，
因此仍为无效诊断数据，后续必须使用新run ID。
同日后续重测获得良好的冷机ZERO和接近名义点的冷机电流校正，但三个点仍全程欠压；
热态ZERO又在约2A负载未移除时执行，写入`1.9805A`错误offset，随后CAL失败。ESP32必须
在物理空载下重新`RESET_CAL`和ZERO，且旧`r1`路径已再次被覆盖。
随后用户已在完全空载下成功执行`RESET_CAL`和ZERO，当前offset为`-0.000203125A`、
gain重置为1.0，错误持久状态已清除；但供电链欠压仍未解决，暂不重新CAL或采集三点。
2026-08-28在UTP3313的5.00V/CV、约0.5A负载下定位到压降：UTP端子至INA226输入降`0.46V`，
INA226输入至输出仅降`0.01V`，INA226输出至ANENG显示节点再降`0.202V`；ANENG节点仅`4.328V`。
主要问题为前后USB-A母座/引线/接触链，不是INA226分流路径。UTP电流`0.634A`与ANENG
`0.492–0.523A`不一致，ANENG暂不得作为可信电流参考；先更换短粗线与转接件后复查0.5A。
随后改用UTP附带短粗测试线直连INA226输入，`U1/U2`均升至`4.92V`、ANENG节点升至`4.776V`，
已证实原输入USB-A链为主要高阻段；但输出段仍降`0.144V`，且UTP约`0.5A`与ANENG约`0.43A`
仍不一致。暂不进入1A/2A或校准，先取得INA226原始电流完成三表对照。
三表对照已完成：新诊断流3127个样本、`invalid=0`，INA226 raw/校正电流均值为
`0.499185A/0.499388A`，与UTP约`0.500A`一致；ANENG约`0.430A`，较INA226低约13.9%，
应从校准参考链中移除。该结果仅支持“INA226在当前0.5A诊断点同UTP读数一致”，不替代
可信参考仪器下的三点校准；输出USB-A链和1A/2A欠压仍须修复。
移除ANENG后，直接USB-A输出链在约0.5A下获得5455个有效样本：INA226电流均值`0.498484A`、
总线电压均值/最小值`4.907738V/4.905000V`，无欠压、积分间隙或饱和；但封装USB-A母座无安全
可测的负载侧节点，不能据此证明电子负载插头处电压。下一步改用已有20AWG Type-C红黑线直连
INA226输出与电子负载Type-C输入，并在裸露引线处复核负载供电电压。
该Type-C链的0.5A复核已完成：`U0/U1/U2/U3=5.00/4.92/4.91/4.91V`，3776个有效样本的
INA226总线电压均值/最小值为`4.906563/4.897500V`，无欠压、积分间隙或饱和。该低点输出链
诊断通过；下一步仅升至1A复核电压，尚不运行ZERO、CAL或正式三点采集。ANENG仍不得回接。
同一Type-C链的1A复核也通过：`U0/U1/U2/U3=5.00/4.83/4.82/4.81V`，4619个有效样本的
INA226总线均值/最小值为`4.816702/4.810000V`，无欠压。0.5A与1A两点估计串联电阻约
`0.183Ω`，2A时预计仅约`4.63V`；暂不执行2A升载，应先降低UTP至INA226输入段的线阻和
夹子/端子接触电阻。该1A记录仍为诊断，不能用于正式校准。
改善输入线后，新的1A/2A流（5752/4088样本）最低总线电压`4.893750V/4.782500V`，均无
欠压、积分间隙或饱和，且手工2A负载侧`U3=4.78V`。此前0.5A Type-C流早于这次最终输入线
改善，按接线变更规则不得自动计入同一组三点，需补采最终接线下的0.5A诊断流。完成后可关闭
供电链欠压诊断；E0仍未通过，剩余关键门槛是可信电流参考、重新空载ZERO、1A CAL及正式三点误差采集。
最终接线的P05补采也通过：4445个样本、总线最低`4.945000V`、无欠压；因此P05/P10/P20最终
接线三点的最低总线电压为`4.945000/4.893750/4.782500V`，供电链欠压诊断已完成修复。E0整体
仍为`in_progress_recalibration_required`：ANENG低读已排除，尚须明确可信电流参考后重新空载ZERO、
1A CAL及正式三点误差采集。
2026-08-28用户明确选择UTP3313TFL-II的面板读数作为本项目的“厂家指标运行参考”：其依据为
厂家说明书的电流设定分辨率1mA、25°C±5°C下电流设定准确度`<0.5%+5mA`，但没有计量溯源证书，且
说明书未单独承诺面板读回准确度。因此后续E0只能形成“有厂家指标边界的物理能耗测量”证据，不能写为
计量溯源/计量级绝对准确度；ANENG继续排除。该选择已解除“尚未选定参考策略”的阻塞，但不解除ZERO、
CAL、三点误差、热态复核、60分钟稳定性及E0总报告等门槛。三点电压误差须由DT-9205A的直流20V档在
INA226 `VOUT-GND`同一节点读取；不能用UTP端子设定的5V代替该节点电压，否则会把供电线压降误判为INA226电压误差。
同日已按该策略完成冷机ZERO（`-0.000074219A`）、1A CAL（参考`1.001A`、测得`0.994511724A`、
gain=`1.006524086`）以及P05/P10/P20三份新run ID完整原始流；三点持续时间为
`71.328/73.782/86.516s`，均无欠压、积分间隙或饱和。热态空载ZERO也合格（`-0.000082031A`）。
但用户在本应执行热态CAL前又执行了`RESET_CAL+ZERO`，并记录`offset_a=0.074011721A`，随后CAL写入
`gain=1.087826490`；这不满足空载零偏门槛，不能计入热态增益复核，且当前ESP32持久校准状态必须恢复。
三份流仍可作为冷机校准状态下的候选正式证据；等待补录各点UTP稳定电流和DT-9205A在VOUT-GND的U2读数，
再进行三点误差计算。
随后用户已在物理空载下成功恢复ZERO（`-0.000054688A`）和1A CAL（参考`1.000A`、内部测得
`0.993156314A`、gain=`1.006890893`）。三点参考读数也已补齐且全程CV：P05/P10/P20的UTP电流
分别为`0.500/1.000/2.000A`，DT-9205A U2分别为`4.95/4.89/4.77V`。三点报告在该复合、不可溯源的
厂家指标参考链下通过：最大电压/电流/功率相对误差分别为`0.244%/1.049%/1.296%`，均低于2%。
这确认了三点误差门槛，但不解除热态增益复核、60分钟稳定性归档及E0总报告等剩余门槛；E1–E8仍不可开始。
用户随后报告在约2.000A、CV、U2=`4.78V`后断开负载并执行ZERO，得到`offset_a=-0.000105469A`
（64样本），数值合格；但未提供2A热负载保持时长，暂不能将其登记为协议要求的“至少5分钟”热态复核。
用户随后确认该2A热负载已保持满5分钟，并在约1A、CV、U2=`4.89V`下以实际UTP面板`1.002A`执行
热态CAL，返回`ok=true`、内部测量`0.995246112A`、gain=`1.006786108`。与恢复冷机gain
`1.006890893`相对差约`0.010%`，热态ZERO/增益复核现已通过。
新采集的Radxa空闲60分钟流完整保存：358,998个样本、3,590个环境样本、362个SYNC回包；有效率
`99.275Hz`、序列丢样率`0.0301%`、无序列回退、无欠压/饱和/固件积分间隙，供电均值`4.969V`。
但采集器报告19条无效串口行，设备时间最大间隔`110ms`，超过冻结30ms门槛；且此次未发送三段
`idle_start/idle_end`标记，无法重建新的三段空闲基线。因此该60分钟流是保留的失败诊断证据，
不能解除E0阻塞；须先排查串口路径并以新run ID重采，同时纳入三段标记。
随后的10分钟Radxa空闲串口预检通过：59,977样本、`invalid=0`、有效率`99.306Hz`、最大设备间隔
`16.025ms`、零序列丢样、无质量标志，说明当前USB/串口链路可满足门槛。最终60分钟重采时，Windows
采集器必须监听`0.0.0.0:8765`而非`127.0.0.1`，使Radxa能发送三段idle标记。
用户为控制Git体积已主动删除旧JSONL的中段，因此仓库中的旧同名文件只是首尾摘录，不是完整raw。
最终重采会话`INA226_E0_stability_radxa_idle_marked_003.full.jsonl`完整保存在Git外，采集器报告
`sample=371578`、`environment=3716`、`marker=6`、`invalid=0`。审计报告显示时长`3741.776s`、
有效率`99.305Hz`、零序列缺失/回退、P99/最大间隔`10.985/16.026ms`、无欠压/饱和/积分间隙；
三段空闲标记各为约65.47秒，空闲平均功率`1.261294W`、段间SD`0.008933W`，并有375个SYNC回包。
全部E0软件门槛通过，详细证据见`data/logs/E0功率测量链分析_20260828_003.json`与
`docs/实验日志/SC-EA-RAG/测量链/SCER-PM-260828-002.md`。后续智能体不得重新执行E0，除非设备、
接线、固件或参考链发生改变，或证据校验失败。
E1前，用户将实际运行供电从UTP切换为一只标称5V/3A充电头，保持INA226、20AWG Type-C输出线和
Radxa接线不变。其10分钟空闲预检得到58,797个样本、`invalid=0`，Vbus均值/最小值为
`4.993702/4.981250V`，无欠压、积分间隙或饱和，且手工`VOUT-GND=5.00V`。该充电头通过
空闲换源预检；尚须用E1最高负载配置完成短时预检后，才能冻结为E1正式供电源。充电头具体型号尚未记录。
同一充电头下的短时高负载预检随后完成：60.936秒内记录6,053个样本、`invalid=0`，平均/峰值功率
`2.387068/3.514953W`，Vbus最低`4.982500V`，无欠压、积分间隙或饱和；手工`VOUT-GND=5.00V`。
充电头在本轮Radxa负载预检下通过，且无需重做E0或修改ESP32校准。E1开始前仅需记录该充电头标签型号/
额定输出与实际使用的输入线标识，并在整个可比较E1批次中保持该源和接线不变。

2026-08-29已完成E1运行时的ARM64本机构建与密集检索准备：冻结的`llama.cpp b9627`
在Radxa ZERO 3上成功构建`bin/llama-server`（SHA-256
`4d157af0eb8c136ffa845065c7ed8d749ce40b048037c19696254a6344ae16b9`），`file`确认其为
`ELF 64-bit aarch64`，`ldd`无缺失共享库。构建期间，预构建UI包缺少`loading.html`；已通过
关闭嵌入式UI并在构建脚本中从冻结源码补齐该静态资产修复，后续不应删除构建目录。Python
`openai_chat`适配单元测试通过；安装`sentence-transformers 3.4.1`与`torch 2.13.0+cu130`后，
本地BGE模型编码输出为`(1, 512)`。随后当前二进制的真实`/health`返回`{"status":"ok"}`，
`/v1/chat/completions`返回非空正文“E1接口正常。”；本机服务验证通过。Windows采集器监听
`0.0.0.0:8765`后，Radxa以`SCI_EXP_METER_HOST=192.168.66.219`发送`idle_start`并收到匹配ACK，
标记闭环也通过。此前的`TimeoutError`不能归因为未`export`主机变量：该命令已成功发送UDP并等待ACK，
直接故障是Windows端未返回ACK；今后须同时显式导出主机IP并确认采集器正在监听。上述均为E1运行时/
边界预检证据，`formal_evidence=false`；GGUF来源/tokenizer审计与随机顺序dry-run仍未完成，不能据此
宣称E1正式实验已开始。
随后以`E1_devtemp_dryrun_idle_004`完成一对同名`idle_start`/`idle_end`：Windows raw
`D:\sci-exp-data\E1_20260829\INA226_E1_devtemp_dryrun_004.full.jsonl`记录8,451个sample、85个
environment、2个marker和0个invalid；按Radxa单调时钟，配对空闲区间为`74.922470s`。此前001含重复
start、002只有一条marker、003的start/end run key不一致，均保留为非正式诊断而不用于积分或基线。
2026-08-29的单query随机顺序dry-run `005`随后完成：C0/C1/C2各3次，`9/9`运行成功；Windows raw
`D:\sci-exp-data\E1_20260829\INA226_E1_devtemp_dryrun_005.full.jsonl`含47,904个功率样本、480个环境
样本、20个标记和0条无效串口行。首次整合错误地以Windows串口到达时间作为积分连续性时钟，因Windows约
15.6ms调度量化产生14个31ms和4个32ms到达间隔，导致5/9条被30ms门槛拒绝；原始ESP32设备时钟的P99/最大
间隔实际为10.984/16.025ms，所有9条均无缺样、欠压、饱和或固件积分间隙。整合器已更正为“主机时钟只用于
UDP标记边界，`device_us`用于积分和连续性判定”，经新增单元测试后复算为9/9有效，空闲功率为
`1.277806725W`。该dry-run验证了随机任务顺序、外部能耗回填和时钟判定；仍为`formal_evidence=false`，不得
用于E1结论或替代正式315次Dev-Temp穷举。随后已从官方`Qwen/Qwen1.5-0.5B-Chat`固定revision
`4d14e384a4b037942bb3f3016665157c8bcb70ea`重新转换并量化；新Q4_K_M位于Git外的
`/home/radxa/sci-exp/models/qwen1_5-0_5b-chat-official-4d14e384-q4_k_m-r2.gguf`，SHA-256为
`ef63ebd112199c99e53b394fc6c9f10f27927b565258738fcf99a91421ea31a8`。其元数据完整包含
`tokenizer.ggml.pre=qwen2`；ARM64服务启动不再出现旧的tokenizer缺失/质量降级警告，`/health`及最小Chat
请求均通过。启动期仍报告token 128247 `</s>`的control-type覆盖；该观察已记录，不能静默忽略，须在新模型
dry-run与后续人工质量审查中保留。模型来源/tokenizer审计门槛已通过；新模型后的006至010均为
`formal_evidence: false`。其中010的RAG运行层为9/9成功，但collector记录75,346 sample、22 marker及
`invalid=34`，不能积分或回填；raw保留在`D:\sci-exp-data\E1_20260829\`且不得覆盖。采集器已改为
完整串口行缓冲，并分开报告`invalid_serial`/`invalid_marker`，将异常元数据写入raw。下一步先做新的
短时配对标记预检，三项无效计数必须均为0；详见
[`SCER-E1-260829-004_新模型dry-run采集异常与采集器诊断修复.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260829-004_新模型dry-run采集异常与采集器诊断修复.md)。

2026-08-30的012预检已证明新Windows地址`192.168.10.11`上的UDP闭环正常（2个marker、
`invalid_marker=0`）。其唯一`invalid_serial=1`是用户停止采集时遗留的单字节`{`，不是完整串口行
损坏；采集器已将此停止边界尾部改为`partial_serial_at_shutdown`独立审计，不计入真实无效行。
随后013预检得到3,997 sample、2 marker，`invalid`、`invalid_serial`、`invalid_marker`均为0；
`partial_serial_at_shutdown=1`仅作停止边界审计。短预检已通过，下一步以新run ID执行新官方Q4_K_M的
单query、C0/C1/C2各3次随机顺序dry-run。015现已完成9/9 runner并取得65,399 sample、20 marker、
三项无效计数均为0的完整raw；该会话仍为`candidate_pending_device_clock_integration`，必须同步runner
结果、核对内部marker错误并确认设备时钟积分9/9有效后，才能判为通过的非正式dry-run。

015后续设备时钟积分为9/9有效，merged中9/9 `external_meter_valid=true`，证明新模型、标记和物理
积分链已经闭环；但C2三次生成token均为30时，首轮仍为67.130秒/141.856J，后两轮仅约11.5秒/
19.7J。冻结llama-server默认开启prompt cache，会跨请求复用公共前缀KV且可能造成非位级确定结果；
因此015被降为`measurement_valid_but_prompt_cache_contaminated_diagnostic_only`。启动脚本已加入
`--no-cache-prompt`并写入正式配置锁。首次重启发现冻结server仍启用独立的8,192MiB全局prompt cache并
保存idle slots，因此最终参数补充`--cache-ram 0 --no-cache-idle-slots`。下一步仅在启动日志明确显示
`prompt cache is disabled`后，用全新run ID重做9-run；不重做E0或013。

016虽取得23,742 sample、20 marker及三项无效计数为0，但runner 9/9均因`127.0.0.1:8080`
连接被拒绝而失败；用户确认该轮没有保持llama-server运行。016只作失败诊断，不积分。下一轮使用新
run ID，采集前必须同时确认进程参数、`/health`及服务终端持续前台运行。

017再次出现0/9，服务终端的`^C ... cleaning up before exit`证明进程被Ctrl+C主动终止；该轮26,201
sample、20 marker与三项无效计数为0的raw仍只作失败诊断，不积分。为消除操作性重复失败，下一轮改用
`nohup`后台常驻并保存服务日志，记录明确PID，验证进程与health后再采集。

018已用`nohup`后台无缓存服务完成最终非正式dry-run：9/9 runner成功、0条marker错误、9/9设备
时钟积分有效且merged中9/9 `external_meter_valid=true`；collector获得101,957 sample、20 marker，
`invalid`、`invalid_serial`、`invalid_marker`均为0。空闲功率为`1.344115770W`，查询区间最大设备
间隔`16.827ms`，无欠压、饱和、shunt近限或固件integration gap。服务在runner结束后仍健康，随后
按PID 33876正常停止；最终服务日志154行、14,147 bytes、SHA-256为
`1AEB4B4E3E9E4D94EA88FC952A3233A3B469DA3692C2FDE7647E6E7746BC1018`，末行是正常清理。
该会话状态为`passed_nonformal_dry_run`，只证明正式流程已具备运行条件，不计入E1的315次正式证据。

2026-08-31正式E1供电身份已冻结为`E1-POWER-CHAIN-01`：UGREEN X336（SN
`E78012001608`，输入100–240V AC、50/60Hz、500mA max，输出5V DC/3A）；输入线编号
`E1-POWER-IN-01`，为15cm铜线，线体无线规标识，用户描述为普通规格；既有20AWG Type-C输出线编号
`E1-POWER-OUT-01`。用户确认整个可比较E1批次不更换充电头、输入线、测量链和输出线。机器可读锁见
`configs/E1_power_chain_lock_v1.0.json`；下一门槛只剩315次固定seed运行清单与盲法双审/仲裁材料冻结。

2026-08-31正式Dev-Temp执行设计已冻结为`E1-DEVTEMP-FORMAL-SEED42-V1`：35条query、C0/C1/C2、
每配置3次，共315次；全局顺序由`random.Random(42).shuffle`一次性产生，manifest SHA-256为
`D2BE522F74060B276FB079525F77C2BF51BA9EF0E9176DFC3901073E43DD0048`。为降低7–8小时单会话
中断风险，固定划分为5个连续区间批次，每批63次；批次之间不得重新随机。CLI现会逐行校验manifest、
保留全局`run_order`、写入`session_id`并拒绝覆盖正式输出。盲审生成器已建立，但首批前仍须登记独立
reviewer A/B与adjudicator身份，并准备Git外私有blind salt；清单冻结本身不是实验结果。

2026-08-31用户已预登记三个互不相同的稳定匿名角色编号：Reviewer A=`E1-REV-A-01`、
Reviewer B=`E1-REV-B-01`、Adjudicator=`E1-ADJ-01`，角色锁为`E1-REVIEW-ROLES-V1`。Git仅保存
匿名编号，不保存真实身份映射、blind salt或crosswalk；角色登记完成时尚未生成私盐，也未执行B01预检。

2026-08-31用户已在`/home/radxa/e1-private/`生成Git外私盐`E1_blind_salt_v1.hex`：65 bytes、
权限`600`、属主`radxa:radxa`，SHA-256为
`E7781B8C83EA7D5DAF640E5587AA3D52203471250BAA0A3782654C863987FA62`；仓库`git status --short`
为空。正文未进入聊天或Git，清单为`E1-BLIND-SALT-V1`。当前只剩B01启动预检，尚未执行正式运行。

## 最近完成的跨阶段数据治理

- `gold_label_inference_leakage`：**已解决**。推理端现只接受Gold-free
  `InferenceQuery`，C2不再读取人工`disaster_type`；400条开发数据已导出独立推理视图，
  Radxa配置只读取该视图，71项测试通过。完整记录见
  [`SCER-DG-260821-001_Gold标签隔离修复.md`](docs/实验日志/SCER-DG-260821-001_Gold标签隔离修复.md)。
- 该修复不改变E0的`in_progress_waiting_hardware`状态，也不把400条
  `development_gold`升级为正式Gold Test。
- 输入级Gold工作包的C补充确认与身份核验已完成：两个补充动作均获`REVISE`，四项机械修正
  均获`ACKNOWLEDGE`，HOST-P已核验ANN-C真实身份、红十字应急救护培训背景、师资资质
  及相关年限。导师S仅作限定领域批准：C可支持心肺复苏、AED、创伤处置、低温、烧伤等
  公众初级救护内容，但不能据此自动批准心理援助/自伤、地质灾害、气象预警、消防和公共
  卫生条目。当前状态为
  `partial_domain_approval_pending_uncovered_domain_resolution_and_statistics_approval`，完整A/B包
  继续保持HOLD；需增加相应领域审核者或正式排除未覆盖领域，并取得统计审核者T批准。
  `formal_evidence=false`。完整记录见
  [`SCER-DG-260822-002_C补充回传_HOST核验与S范围裁定.md`](docs/实验日志/SCER-DG-260822-002_C补充回传_HOST核验与S范围裁定.md)。
- 根据ANN-C最新六类领域能力声明，已启动范围受限的A/B预标注：四份阶段分离工作簿已生成，
  培训页与独立试标页互相隐藏。A/B可以立即开始预标注；公众初级救护部分可由C后续终裁，
  其余心理/自伤、地质、气象、消防系统和公共卫生条目在外部领域审核前只能保留为待复核
  预标注，不能冻结为完整Gold。完整A/B Gold包仍保持HOLD，formal_evidence=false。
  记录见[`SCER-DG-260822-003_C范围确认与AB预标注启动.md`](docs/实验日志/SCER-DG-260822-003_C范围确认与AB预标注启动.md)。
- ANN-A 与 ANN-B 的独立标注者信息已补充完成，HOST-P已核验两人的身份、证书状态、相关年限、
  利益冲突和独立性声明。A/B/C三人的`training_completed_at`统一登记为
  `2026-06-15T12:16:00+08:00`（与C同一培训完成时间）。A/B当前状态为
  `REGISTERED_PENDING_TRAINING_AND_PILOT`，不是已通过正式标注准入；完整A/B发放仍受未覆盖领域
  处理与T统计批准约束。登记派生版见
  [`04_主持人总控_身份登记更新_v1.2.xlsx`](outputs/input_gold_host_acceptance_20260822/04_主持人总控_身份登记更新_v1.2.xlsx)。
- 对 v1.2 培训回传的质检发现：ANN-A 的触发/动作/约束集合和证据跨度未完成，ANN-B 使用了非
  canonical ID。当前 v1.2 回传不进入培训讲解或一致性统计；已依据 C 审核工作簿生成带“受控ID字典”
  的 v1.3 培训包，等待 A/B 重新完成培训25。v1.3 仍为 `formal_evidence=false`，独立试标包暂不发放。
  记录见[`SCER-DG-260822-004_v1.3受控ID字典培训包生成.md`](docs/实验日志/SCER-DG-260822-004_v1.3受控ID字典培训包生成.md)。
- ANN-A、ANN-B 已回传 v1.3 培训25，C 已提交培训讲解。培训讲解覆盖风险触发、required/critical、
  prohibited 条件适用及待外审领域边界；培训回传保留为历史记录，不用主持人改写答案。质检发现：
  ANN-A 在 TRN-018、TRN-020 各有一处 required/prohibited 重叠；ANN-B 将未冻结的
  `hazard_family_id`/`query_intent_ids` 填为 `ONTOLOGY_GAP`。这些错误已写入独立试标包的防错提示，
  不把培训答案改成伪一致。新的 v1.3 独立试标包已生成并通过结构、题集、空白培训页和公式错误检查；
  pilot 仍为 `formal_evidence=false`，不得视为完整 Gold。记录见
  [`SCER-DG-260823-005_v1.3培训回传与独立试标包发放.md`](docs/实验日志/SCER-DG-260823-005_v1.3培训回传与独立试标包发放.md)。
- ANN-A、ANN-B 已回传 v1.3 独立试标25，但仲裁前统计暂时 `HOLD`：ANN-A 的
  `evidence_span_refs_json` 25 行均为空，ANN-B 的非空跨度对象缺少必需的 `span_ref` 字段，
  官方一致性脚本无法解析这两份原始回传；ANN-B 的 `hazard_family_id`/`query_intent_ids` 仍填入
  `ONTOLOGY_GAP`，将作为未冻结字段分歧保留。当前不向 C 发仲裁包，不运行正式一致性统计；先让 A、B
  只修正证据跨度 JSON 结构并回传新文件。记录见
  [`SCER-DG-260823-006_v1.3独立试标回传预检与仲裁暂停.md`](docs/实验日志/SCER-DG-260823-006_v1.3独立试标回传预检与仲裁暂停.md)。
- A、B 已回传证据跨度修正版；两份文件的 25 行跨度 JSON、`evidence_id`/`span_ref` 引用和动作结构约束
  均通过复检。但官方一致性脚本再次发现 `uncertainty_code` 不符合冻结码本：A 有多值拼接，B 有多值及
  未冻结自定义值。日期仅是 Excel 到 CSV 的本地化序列化问题，可由主持人无损转为 ISO 8601。当前仍为
  `HOLD`，A/B 只需各自修正 `uncertainty_code` 一列；修正前不运行正式一致性统计、不生成 C 仲裁包。
- A、B 已回传码本修正版，单值 `uncertainty_code`、证据跨度和结构约束均通过。官方脚本已完成 25 对记录、
  2000 次 source-group bootstrap；指标门禁为 `REVIEW_REQUIRED`，正式门禁为
  `REVIEW_REQUIRED_UNTIL_GATE_PROFILE_APPROVED`。25/25 条存在至少一项内容分歧，但 S3 对 S0/S1 分歧、
  required/prohibited 冲突和 critical 非 required 冲突均为 0。已生成 C 仲裁工作簿和一致性报告；C 可开始
  逐项仲裁，但本批次不得表述为门禁通过或完整 Gold 冻结。记录仍见
  [`SCER-DG-260823-006_v1.3独立试标回传预检与仲裁暂停.md`](docs/实验日志/SCER-DG-260823-006_v1.3独立试标回传预检与仲裁暂停.md)。
- C 已回传仲裁文件；25/25 条实质最终值、证据和动作安全结构通过复核，且未修改仲裁输入快照及其他工作表。
  但 `decision`、`protocol_gap`、`manual_or_ontology_change_required` 和部分最终
  `uncertainty_code` 不符合冻结 schema（自定义 decision、文本代替布尔值、多值/未冻结代码）。当前状态为
  `C_SCHEMA_REPAIR_REQUIRED_BEFORE_FINAL_GOLD`；不得直接生成最终 Gold。只需 C 修正上述机械字段后，再做
  JSON Schema 校验、最终合并和仲裁后 QA。
- C 已回传 schema 修正版并通过机械字段验收。已生成仲裁后派生数据及 QA：25 条、结构/证据/不确定性检查
  全部通过；其中 10 条为 `UNRESOLVED`、3 条为 `OUT_OF_SCOPE`。该文件状态为
  `DERIVED_NOT_FORMALLY_FROZEN_REVIEW_REQUIRED`，仅可用于本轮试标诊断和标注资产整理，未覆盖领域与
  统计门禁批准完成前不得作为正式 Gold Test、监督目标或医学正确性证据。记录见
  [`SCER-DG-260823-006_v1.3独立试标回传预检与仲裁暂停.md`](docs/实验日志/SCER-DG-260823-006_v1.3独立试标回传预检与仲裁暂停.md)。
- 机构审核方 `ANN-C-ORG` 已回传机构仲裁工作簿。机械审计通过：25/25 条，`NEW=21`、`A=4`、
  `B=0`，`protocol_gap=true` 5 条，需本体/手册修改 5 条；A/B 仲裁输入快照未改写，证据 ID、
  critical/required/prohibited 结构和公式错误检查均通过。当前派生文件为
  [`输入级Gold_仲裁后派生_v1.3_非正式冻结.xlsx`](outputs/input_gold_scoped_annotation_start_20260823/qa_v13_final_gold_org/输入级Gold_仲裁后派生_v1.3_非正式冻结.xlsx)，
  状态仍为 `DERIVED_NOT_FORMALLY_FROZEN_REVIEW_REQUIRED`。机构 `人员登记` 中 `ANN-C-ORG` 的
  `credential_verified_by` 尚为空，需 HOST-P 补填后才具备完整资质追溯；机构 C JSON 未提供最终证据跨度和
  rationale，派生文件对此采用 A/B 跨度或冻结索引 source_locator，并保留为透明派生。完整记录见
  [`SCER-DG-260824-001_v1.3机构仲裁回传审计与派生Gold.md`](docs/实验日志/SCER-DG-260824-001_v1.3机构仲裁回传审计与派生Gold.md)。
- HOST-P 已确认 credential 登记、SUP-S 已批准范围、STAT-T 已批准统计门禁。基于机构 HOST 验收版
  已完成正式范围限定冻结：全量25条作为正式审核归档，12条进入正式监督子集，5条保留为不确定性挑战集，
  8条排除或等待本体/协议处理。正式监督子集仅覆盖 `IN_SCOPE + evidence_gap=false + uncertainty_code=NONE`
  且无协议缺口/本体修改要求的记录；未冻结的 `hazard_family_id/query_intent_ids` 不作为确定监督目标。
  输出见 [`输入级Gold_机构仲裁正式冻结_v1.3.xlsx`](outputs/input_gold_scoped_annotation_start_20260823/qa_v13_formal_scoped_gold/输入级Gold_机构仲裁正式冻结_v1.3.xlsx)，
  完整记录见 [`SCER-DG-260824-002_v1.3正式范围限定Gold冻结.md`](docs/实验日志/SCER-DG-260824-002_v1.3正式范围限定Gold冻结.md)。
- 正式 Gold Test 已注册到 `docs/sci-exp/data/annotations/input_gold_v1.0/frozen/gold_test_v1.3/`：
  `gold_test_v1.3.csv` 12条、挑战集5条、排除/待本体集8条、全量25条归档及 manifest/哈希/防泄漏 ID 清单。
  全量25条均禁止进入训练、few-shot、调参和检索示例；正式评估只读取12条 Gold Test。记录见
  [`SCER-DG-260824-003_v1.3GoldTest注册与防泄漏材料.md`](docs/实验日志/SCER-DG-260824-003_v1.3GoldTest注册与防泄漏材料.md)。

## 当前阶段

|阶段|状态|是否允许作为正式证据|
|---|---|---|
|E0 功率测量链|`formal_pass_with_operational_reference_limitations`|是，限厂家指标运行参考边界；不得表述为计量溯源|
|E1 配置异质性正式运行|`B05-003_locked_after_server-start_failure`|B01-003至B04-001均已封存；B05-001为串口损坏诊断、B05-002为未启动服务诊断；B05-003须先验证服务后全批重跑|
|E2–E8正式运行|`blocked_by_sequence`|否，须按冻结协议等待E1及后续前置阶段|

## 正式E1开始前仍需完成

- `E1-DEVTEMP-FORMAL-B01-002`已完成63次尝试，但13次HTTP请求超时、2次HTTP 500，CLI返回3；
  14/15失败属于C2。服务日志显示parallel=4统一KV在客户端超时取消与下一任务交叠后反复分配失败，
  两个500均为`Context size has been exceeded`。物理raw包含800,189个sample、8,002个environment和
  正确的128个实验marker，三项invalid均为0；因此这是运行时基础设施失败，不是测量链失败。
  B01-002永久保留且不能生成盲审包；不得只补跑15条或开始B02；
- 版本化候选修订新增`configs/E1_devtemp_v2.json`（timeout 300秒）并将llama-server固定为
  `--parallel 1`；生成/检索/token/上下文语义和seed42清单不变。采集器已增加经ACK确认的
  `collector_stop`自动停止机制，本地COM18 smoke通过。以上修订必须先完成针对长C2的非正式预检，
  才能冻结并以新session完整重跑B01；

- v2非正式预检`E1-RUNTIME-V2-PREFLIGHT-001`已完成10条，9成功、1失败；唯一失败为run order 21的
  `formal_exp_0171:C2:2`，在300.395秒客户端超时。服务以`--parallel 1`运行，无KV/cache、HTTP 500或
  context-size错误；服务端在取消前已经生成500 token，接近C2 512 token上限，说明问题是300秒缺少尾部
  余量。Windows collector自动停止获得`control=1`和三项invalid=0，但重复`idle_end`使marker=23，故仅作
  非正式证据。新增v3候选将超时提高到420秒，其他方法语义不变；必须先对同一run order 21完成1/1预检，
  同时验证runner结束后服务health仍可用，才可冻结v3。记录见
  [`SCER-E1-260901-009_V2预检超时与V3候选运行时.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260901-009_V2预检超时与V3候选运行时.md)。

- v3非正式预检`E1-RUNTIME-V3-PREFLIGHT-001`对同一run order 21获得1/1成功，C2耗时306.934秒并完整
  生成512 token；runner无marker错误、Windows collector自动停止（`control=1`）、三项invalid均为0，
  runner结束后服务health为HTTP 200。预检专用服务由操作者停止并正常收尾。`E1-FORMAL-RUNTIME-V3-20260901`
  已锁定，允许以全新`E1-DEVTEMP-FORMAL-B01-003`从global run order 1运行至63。记录见
  [`SCER-E1-260901-010_V3预检通过与B01-003锁定.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260901-010_V3预检通过与B01-003锁定.md)。

- 正式B01-003已完成global run order 1–63：runner 63/63成功，INA226以`device_us`积分后63/63有效；
  raw marker=128、control=1、三项invalid=0，idle power为1.350479 W。该批次是有效正式E1切片，
  但尚非完整315次E1结论；下一步须先冻结B02（run order 64–126）。完整证据见
  [`SCER-E1-260902-011_B01-003通过与物理能耗合并.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260902-011_B01-003通过与物理能耗合并.md)。

- B02-001已完成global order 64–126：runner 63/63成功，`device_us`物理积分63/63有效；Git外raw
  的marker=128、control=1、三项invalid=0。运行前Wi-Fi切换后的UDP预检通过，正式端点为
  Windows `192.168.1.24:8765`、Radxa `192.168.1.29`；这只改变传输端点，不改变冻结配置。B02是第二个
  有效正式E1切片，仍不是完整315次结论。B03已锁定为global order 127–189。记录见
  [`SCER-E1-260902-013_B02通过与物理能耗合并.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260902-013_B02通过与物理能耗合并.md)。

- B03-001已完成global order 127–189：runner 63/63成功，物理积分63/63有效，raw的marker=128、control=1、
  三项invalid=0。B03锁的Windows本地提交早于首条运行约4分54秒，但未在运行前成功推送到Radxa；该发布控制
  偏差已登记为`ANOM-E1-20260902-004`，不隐去也不重跑。B04必须先核验锁提交已在Radxa HEAD。记录见
  [`SCER-E1-260902-014_B03通过与同步偏差审计.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260902-014_B03通过与同步偏差审计.md)。

- B04-001已完成global order 190–252：runner 63/63成功，`device_us`物理积分63/63有效；Git外raw的
  marker=128、control=1、三项invalid=0，idle power为1.281873 W。B04锁已在Radxa运行前同步，但预检脚本
  错将完整HEAD同短哈希比较而给出假阴性，且工作树保留两份既有失败诊断；偏差已登记为
  `ANOM-E1-20260902-005`，两份诊断现已审计并永久提交。B04不重跑、不覆盖；B05必须使用干净工作树和
  正确的短哈希预检。完整记录见
  [`SCER-E1-260902-015_B04通过与预检偏差审计.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260902-015_B04通过与预检偏差审计.md)。

- B05-001已执行global order 253–315，runner为63/63成功（C0=21、C1=20、C2=22），但Git外raw的
  `invalid=26`、`invalid_serial=26`，并有17个sequence gap与113个缺失设备样本；损坏集中于长C2
  `formal_exp_0172:C2:1`。因此`ANOM-E1-20260902-006`已登记，B05-001只能保留为失败诊断，不能积分为
  正式物理能耗，也不能局部补跑。采集器缓冲与刷盘策略已在`afcb093`修订；下一门槛是非正式的串口恢复
  smoke和30分钟连续预检，只有通过后才可创建全新B05-002锁并完整重跑253–315。记录见
  [`SCER-E1-260902-016_B05-001串口损坏诊断与恢复预检.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260902-016_B05-001串口损坏诊断与恢复预检.md)。

- 串口恢复预检`E1-B05-SERIAL-RECOVERY-PREFLIGHT-001`已通过：Windows collector在RX=1MiB、
  `status=configured`下连续约30分钟记录179,645 sample，三项invalid=0、sequence gap/缺失/回退均为0、
  最大`device_us`间隔16.825 ms（≤30 ms），并收到一个`collector_stop`。该预检仅解除B05重跑的串口
  阻塞，`formal_evidence=false`。B05-002现已锁定为全新session `E1-DEVTEMP-FORMAL-B05-002`，必须完整
  重跑global order 253–315；详细记录见
  [`SCER-E1-260902-017_串口恢复预检通过与B05-002锁定.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260902-017_串口恢复预检通过与B05-002锁定.md)。

- B05-002尝试已永久保留但被拒绝：服务未启动导致runner 63/63为连接拒绝、0成功，`ANOM-E1-20260903-007`
  已登记。其raw的串口传输质量正常但没有有效推理区间，不能积分。B05-003现已锁定为全新session
  `E1-DEVTEMP-FORMAL-B05-003`，仍完整执行global order 253–315；必须先用独立服务日志核验PID、HTTP 200、
  禁用cache和监听成功，才允许启动collector。完整记录见
  [`SCER-E1-260903-018_B05-002服务未启动诊断与B05-003锁定.md`](docs/实验日志/SC-EA-RAG/测量链/SCER-E1-260903-018_B05-002服务未启动诊断与B05-003锁定.md)。

- `E1-DEVTEMP-FORMAL-B01-001`已作为中止的正式尝试永久保留：runner仅1行（run order 1、C1、推理
  `status=ok`），但`external_marker_errors`含两次`TimeoutError`；Git外raw只有2条空闲marker，没有查询
  marker。该行`external_meter_valid=false`，不得进入E1有效子集。原因是操作者把pipeline初始化期尚未创建
  输出文件误判为故障并停止Windows采集器；后台runner随后完成第一条推理。下一次必须使用全新
  `E1-DEVTEMP-FORMAL-B01-002`及`attempt002`文件，初始化期间持续保持采集器运行；
- 2026-09-01的B01预检采集得到9,251个sample、93个environment、2个marker，三项invalid均为0；
  无缓存llama-server PID、health和启动日志也通过。预检同时发现配置冻结哈希使用了Windows CRLF字节，
  而Radxa同一Git blob为LF字节。JSON语义、任务清单和顺序未变化；已将
  `configs/E1_devtemp_v1.json`锁定为LF并把跨平台冻结哈希勘误为
  `C95E890830FB34853DDA40D6E23B26F6C9AB25AB82E1C136B40D76B64FC85729`。Radxa已拉取提交`647dde3`并
  复核该配置哈希和清单`D2BE...0048`均匹配，工作树干净，PID 35172及health仍正常；
- Git外blind salt已冻结；不得覆盖、重生成或向Reviewer A/B暴露。盲审包只能在315条successful且
  `external_meter_valid=true`的merged结果齐全后生成；
- 正式批次使用与018一致的官方Q4_K_M、禁用两层prompt cache的启动参数、`nohup`服务日志和明确PID；
- 每条正式运行仅在`external_meter_valid=true`时进入有效物理测量子集，失败和无效运行仍须保留报告。

## 当前不能宣称

- 018不能替代35条Dev-Temp × 3配置 × 3重复的315次正式穷举；
- 尚无正式E1 Oracle配置占比、选择矩阵或Safety–Energy Pareto结论；
- 在E1、盲审/仲裁及后续阶段完成前，不能提前给出E2–E8或Gold Test论文级结论。

## 下一正式动作

E0、018最终非正式dry-run、`E1-POWER-CHAIN-01`、315次全局运行清单、`E1-REVIEW-ROLES-V1`、
`E1-BLIND-SALT-V1`、`E1-FORMAL-RUNTIME-V3-20260901`及B01-003至B04-001结果均已封存。B05-001的
推理输出也已封存，但其物理raw发生串口损坏，不能覆盖、不能积分、不能局部补跑；30分钟串口恢复预检已通过。
下一步按`E1_formal_batch_B05_attempt003_lock_v3_20260903.json`在全新session完整执行global order 253–315，且必须先验证服务PID、HTTP 200与独立启动日志。
采集器必须运行至接收`collector_stop`；端点为Windows `192.168.10.11:8765`、Radxa `192.168.10.13`。完整高频raw
继续保存在Git外，Git只提交派生证据、manifest和实验日志。
