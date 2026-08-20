# ESP32-S3 + INA226 R010 + SHT31功率与环境采集器

本工程对应照片中的红色 INA226 模块：大端子为蓝色输入 `VIN/GND`、绿色输出
`GND/VOUT`，小排针为 `VCC/GND/SDA/SCL/ALER`，板载分流电阻为 R010
（0.01 Ω）。

## 第一阶段：只检查 I²C

四个大螺丝端子保持空置，Radxa 不接入。只连接：

| 红色 INA226 | ESP32-S3 |
|---|---|
| `VCC` | `3V3` |
| `GND` | `GND` |
| `SDA` | `GPIO4` |
| `SCL` | `GPIO5` |
| `ALER` | 不接 |

SHT31与INA226共用同一I²C总线：

| SHT31 | ESP32-S3 |
|---|---|
| `VCC`/`VIN` | `3V3` |
| `GND` | `GND` |
| `SDA` | `GPIO4` |
| `SCL` | `GPIO5` |
| `ADDR` | 模块默认低电平（地址`0x44`） |
| `ALERT` | 不接 |

ESP32-S3 通过电脑 USB 供电。当前 PlatformIO 环境使用 `COM18` 和 921600 波特率。

## 构建、烧录和查看输出

在 VS Code 的 PlatformIO 插件中依次执行：

1. **Build**；
2. **Upload**；
3. **Serial Monitor**。

也可以在本目录使用命令：

```powershell
pio run
pio run --target upload --upload-port COM18
pio device monitor --port COM18 --baud 921600
```

固件启动时会自动扫描 I²C。正常的默认地址结果类似：

```json
{"type":"i2c_scan","addresses":["0x40","0x44"],"count":2,"ina226_found":true,"sht31_found":true,"sda":4,"scl":5}
```

随后应出现：

```json
{"type":"boot","ok":true,"device_us":123456}
```

串口也支持手动发送 `SCAN`，可随时重新扫描。若没有找到设备，扫描结果中的
`addresses` 会为空且 `expected_found` 为 `false`；此时只检查 `VCC/GND/SDA/SCL`
接线，不连接四个大螺丝端子和 Radxa。

## 第二阶段：Radxa UART 同步

保持 INA226 的 I²C 接线不变，增加：

| Radxa ZERO 3W | ESP32-S3 |
|---|---|
| Pin 18 `UART4_TX_M1` | GPIO10（RX） |
| Pin 16 `UART4_RX_M1` | GPIO9（TX） |
| GND | GND |

固件使用独立 UART1，参数为 115200、8N1。它不会占用 INA226 的 GPIO4/GPIO5，
也不会把全部功率样本回传给 Radxa；功率日志仍通过 ESP32 USB 输出到 Windows。

Radxa 项目中的测试工具为：

```text
scripts/radxa_uart_power_sync.py
```

在 Radxa 上安装硬件可选依赖后测试：

```bash
cd /home/radxa/sci-exp
.venv/bin/python -m pip install -e '.[hardware]'
sudo .venv/bin/python scripts/radxa_uart_power_sync.py hello
```

成功时 Radxa 输出 `ACK,HELLO` 对应的 JSON，Windows 串口日志出现
`{"type":"radxa_rx","command":"HELLO",...}`。

正式协议：

```text
ARM,<run_id>  -> READY,<run_id>
START,<run_id> -> ACK_START,<run_id>
STOP,<run_id> -> DONE,<run_id>
```

也可以用一条命令包裹一次待测程序：

```bash
sudo .venv/bin/python scripts/radxa_uart_power_sync.py run \
  --run-id SCM_0001_C05_R1 -- python3 your_experiment.py
```

UART 启动的每个功率样本都会带同一个 `run_id`，结束时 Windows 日志会输出
`run_end`，其中包含样本数、持续时间和该段累计能量。

功率样本目标频率为100 Hz。SHT31环境温湿度按1 Hz独立输出`environment`记录，
不得把SHT31温度当成Radxa SoC温度；后者由Radxa的Linux thermal zone记录。

## 后续功率路径（第一阶段通过后再接）

```text
5V电源正极 -> 蓝色 VIN
5V电源负极 -> 蓝色 GND
绿色 VOUT  -> Radxa +5V
绿色 GND   -> Radxa GND
```

`VCC` 只接 ESP32-S3 的 3.3 V，不能用它给 Radxa 供电。
