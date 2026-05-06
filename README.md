# QKD Coexistence Experiment

QKD 共纤传输实验自动化控制系统。

## 项目简介

本项目用于自动化控制量子密钥分发（QKD）与经典 DWDM 光信号共纤传输实验，实现实验流程控制、设备调度与数据采集。

**项目定位**：设备自动化控制系统，重点在于控制各实验装置；仿真模块仅用于方案预评估。

## 主要功能

- **设备自动化控制**：WSS、TLS、OSA、ASE、QKD 等光学设备
- **OSA 频谱采集**：频率扫描、频谱 CSV 数据保存、3dB/30dB 带宽自动分析
- **实验流程自动化**：自动执行信道分配方案、采集 QKD 数据
- **方案预评估**：仿真模块预估信道分配方案性能
- **数据分析**：时间序列分析、SKR/QBER 统计
- **可视化**：通道分配可视化 GUI

## 项目结构

```
QKD_Coexistence/
├── main.py                # 主程序入口
├── config.yaml            # 实验参数配置（YAML）
├── config.py              # 配置加载（dataclass）
├── requirements.txt
├── device/                # 硬件控制模块
│   ├── __init__.py
│   ├── optical_spectrum_analyzer.py  # OSA 光谱仪控制（频谱扫描/图像/带宽分析）
│   ├── wavelength_selective_switch.py # WSS 波长选择开关
│   ├── ASE_source.py          # ASE 放大自发辐射源
│   ├── tunable_laser_source.py # TLS 可调谐激光源
│   ├── QKD_log_read.py        # QKD 日志读取与 SKR 绘图
│   └── SFP_source.py          # SFP 可调谐光模块
├── simulation/            # 仿真模块（方案预评估）
│   ├── __init__.py
│   ├── BB84_SKR.py           # BB84 SKR 计算（finite / infinite）
│   └── MCF.py                # 多芯光纤拉曼散射系数
├── tools/                 # 工具脚本
│   ├── time_corr.py          # 时间序列分析
│   └── count_down.py         # 倒计时工具
├── gui/                   # 可视化工具
│   └── channel_viewer.py     # 通道分配可视化
├── data/                  # 实验数据（运行时生成）
└── log/                   # QKD 日志（SFTP 下载）
```

## 快速开始

### 1. 环境配置

Python 环境：`C:\Users\Annie\miniconda3\envs\qkd_env\`

```bash
pip install -r requirements.txt
```

### 2. 实验参数配置

编辑 `config.yaml` 设置实验参数：

- `device` 段：各设备连接地址（IP / COM 口）
- `experiment` 段：光纤距离、功率、信道间隔、方案列表、重复次数等

> **注意**：YAML 中科学计数法必须带符号，如 `193.5e+12`（不能写成 `193.5e12`），否则会被解析为字符串导致类型错误。

### 3. 运行实验

```bash
python main.py
```

### 4. 可视化

```bash
python gui/channel_viewer.py
```

## 实验数据保存

每次实验在 `data/` 下自动生成层级目录：

```
data/{spacing}GHz {num_c}channel {actual_power}dBm/
├── 1_interleave_100.0GHz/       # 编号+方案名称+信道间隔
│   ├── OSA 频谱图像 (.bmp)
│   ├── 频谱数据 (.csv)
│   ├── 带宽分析 (.csv)
│   ├── SKR 详情 (.xlsx)
│   ├── 密钥/QBER 详情 (.xlsx)
│   └── SKR 随时间变化图 (.png)
├── 2_CCA_100.0GHz/
│   └── ...
└── data.xlsx                    # 实验汇总表
```

## 硬件要求

- WSS (波长选择开关) - 串口控制
- TLS (可调谐激光源) - 以太网控制
- OSA (光谱分析仪) - 以太网控制，型号 Yokogawa AQ6370D
  - **分辨率范围**：0.05nm ~ 2.0nm
  - **扫频模式**：支持以频率（Hz）为单位扫频
- ASE 源 - 串口控制
- QKD 系统 - SFTP 访问
- SFP 可调谐光模块 - 串口 JSON 控制（需板端固件配合）

## SFP 可调谐模块使用

SFP 模块采用"板端 C 固件 + PC 端 Python 控制"方式接入。Python 通过串口发送 JSON 命令，低层硬件访问由 Vitis 程序完成。

1. 在 Vitis 工程中使用项目内的 `device/sfp.c` 作为 SFP 应用源码
2. 基于硬件平台 build 应用程序
3. 将 build 出来的 ELF download/run 到 FPGA/SoC 板卡
4. 启动 Python 控制脚本

```python
import device

with device.SFP(transport="serial", serial_port="COM3", baudrate=115200) as sfp:
    print(sfp.get_module_info())
    print(sfp.get_channel())
    sfp.set_channel(10)
    print(sfp.get_status())
    print(sfp.get_ddm())
```

## 许可证

本项目采用 MIT 许可证。
