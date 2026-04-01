# QKD Coexistence Experiment

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
python main.py
```

### 4. 可视化

```bash
python gui/channel_viewer.py
```

## 硬件要求

- WSS (波长选择开关) - 串口控制
- TLS (可调谐激光源) - 以太网控制
- OSA (光谱分析仪) - 以太网控制
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
