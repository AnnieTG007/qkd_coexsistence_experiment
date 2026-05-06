# QKD Coexistence Experiment

## SFP 可调谐模块使用顺序

SFP 可调谐模块采用“板端 C 固件 + PC 端 Python 控制”的方式接入。Python 不直接访问 SFP 的 I2C/GPIO；低层硬件访问由 Vitis 程序完成，上层实验流程由 Python 通过串口发送 JSON 命令控制。

使用前请按下面顺序操作：

1. 在 Vitis 工程中使用项目内的 `device/sfp.c` 作为 SFP 应用源码。
2. 基于 `E:\vivado\sfp_project_1` 对应的硬件平台 build 应用程序。
3. 将 build 出来的 ELF download/run 到 FPGA/SoC 板卡，确保板端串口 JSON 服务已经运行。
4. 再启动 Python 上位机控制脚本。

Python 示例：

```python
import device

with device.SFP(transport="serial", serial_port="COM3", baudrate=115200) as sfp:
    print(sfp.get_module_info())
    print(sfp.get_channel())
    sfp.set_channel(10)
    print(sfp.get_status())
    print(sfp.get_ddm())
```

如果 Python 报串口超时或返回不是 JSON，优先检查：板端 ELF 是否已经 download/run、串口号是否正确、Vitis 程序是否使用了 `device/sfp.c` 这份 JSON 服务版本。

QKD 共纤传输实验自动化控制系统。

## 项目简介

本项目用于自动化控制量子密钥分发（QKD）与经典 DWDM 光信号共纤传输实验，实现实验流程控制、设备调度与数据采集。

**项目定位**：设备自动化控制系统，重点在于控制各实验装置；仿真模块仅用于方案预评估。

## 主要功能

- **设备自动化控制**：WSS、TLS、OSA、ASE、QKD 等光学设备
- **实验流程自动化**：自动执行信道分配方案、采集 QKD 数据
- **方案预评估**：仿真模块预估信道分配方案性能
- **数据分析**：时间序列分析、SKR/QBER 统计
- **可视化**：通道分配可视化 GUI

## 项目结构

```
QKD_Coexistence/
├── main.py                # 主程序入口
├── device/                # 硬件控制模块
│   ├── ASE_source.py          # ASE 源控制
│   ├── tunable_laser_source.py # TLS 控制
│   ├── QKD_log_read.py        # QKD 日志读取
│   ├── optical_spectrum_analyzer.py # OSA 控制
│   ├── wavelength_selective_switch.py # WSS 控制
│   └── SFP_source.py          # SFP 源控制
├── simulation/            # 仿真模块（方案预评估）
│   ├── BB84_SKR.py           # BB84 SKR 计算
│   └── MCF.py                # 多芯光纤仿真
├── tools/                 # 工具脚本
│   ├── time_corr.py          # 时间序列分析
│   └── count_down.py         # 倒计时工具
├── gui/                   # 可视化工具
│   └── channel_viewer.py     # 通道分配可视化
├── data/                  # 实验数据目录
├── log/                   # QKD 日志目录
└── docs/                  # 项目文档
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置设备连接

在 `main.py` 中修改设备地址和串口配置。

### 3. 运行实验

```bash
python main_1.py
```

### 4. 可视化

```bash
python gui/channel_viewer.py
```

## 硬件要求

- WSS (波长选择开关) - 串口控制
- TLS (可调谐激光源) - 以太网控制
- OSA (光谱分析仪) - 以太网控制，型号 Yokogawa AQ6370D
  - **分辨率范围**：0.05nm ~ 2.0nm（通过 `:SENSe:BANDwidth:RESolution` 设置）
  - **扫频模式**：支持直接以频率（Hz）为单位扫频（`:SENSe:WAVelength:STARt {freq}[HZ]`）
  - **横坐标显示**：可切换为频率（`:UNIT:X FREQuency`）
- ASE 源 - 串口控制
- QKD 系统 - SFTP 访问

## 文档

详细文档请参阅 [docs/](docs/) 目录：

- [项目概述](docs/project_overview.md)
- [安装指南](docs/installation.md)
- [使用说明](docs/usage.md)
- [硬件说明](docs/hardware.md)
- [仿真说明](docs/simulation.md)
- [API 参考](docs/api_reference.md)

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。
