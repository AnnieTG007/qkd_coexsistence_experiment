# 使用说明

## 目录结构

```
QKD_Coexistence/
├── main.py                # 主程序入口
├── device/                # 硬件控制模块
├── simulation/            # 仿真模块
├── tools/                 # 工具脚本
│   ├── time_corr.py       #   时间序列分析
│   └── count_down.py      #   倒计时工具
├── gui/                   # 可视化工具
│   └── channel_viewer.py  #   通道分配可视化
├── data/                  # 实验数据目录
└── log/                   # QKD 日志目录
```

## 主程序使用

`main.py` 是实验自动化的主入口，负责控制整个实验流程。

### 基本用法

```bash
python main_1.py
```

### 配置实验方案

在 `main.py` 中修改实验参数：

```python
# 信道间隔列表
spacing_list = np.array([100e9])

# 方案名称列表
scheme_name_list = ['CCA_anti', 'qUFS', 'interleave', 'None']

# 经典信道数量
num_c = 8
```

### 支持的信道分配方案

| 方案名称 | 说明 |
|----------|------|
| `interleave` | 交错方案：经典信道交错分布在量子信道两侧 |
| `neg_interleave` | 负交错方案 |
| `CCA` | 经典信道靠近同步频率排列 |
| `CCA_anti` | 反 CCA 方案 |
| `qEFS` | 量子增强频隙方案（固定 4 对称分布） |
| `qUFS` | 量子非相关频隙方案（通过仿真优化选择） |
| `None` | 无经典信号（对照组） |

### 运行模式

将 `DEBUG_MODE` 设置为 `True` 可以启用调试模式，仅运行仿真而不实际操作设备：

```python
DEBUG_MODE = True
```

## 仿真模块使用

### SKR 预评估

在实验前评估信道分配方案的预期性能：

```python
from simulation import MulticoreFiber, BB84_SKR_finite
import numpy as np

# 定义经典信道频率数组
classical_channels = np.array([
    193.10e12, 193.20e12, 193.30e12, 193.40e12,
    193.60e12, 193.70e12
])

# 计算预期 SKR 和 QBER
skr, qber = SKR_simulation(classical_channels)
print(f"预期 SKR: {skr} bps, QBER: {qber}")
```

## 工具脚本使用

### 时间序列分析

`tools/time_corr.py` 用于分析 QKD 采集的时间序列数据：

```bash
python tools/time_corr.py
```

主要功能：
- 自动读取 Excel 数据文件
- 重采样处理
- 自相关分析
- Ljung-Box 检验
- ADF/KPSS 平稳性检验

### 倒计时工具

`tools/count_down.py` 提供实验倒计时功能：

```python
from tools.count_down import countdown

# 10 分钟倒计时
countdown(600)
```

## 可视化工具

### 通道分配可视化

`gui/channel_viewer.py` 提供 GUI 界面展示信道分布：

```bash
python gui/channel_viewer.py
```

或通过 Python 调用：

```python
from gui.channel_viewer import show_channel_distribution
import numpy as np

classical = np.array([193.10e12, 193.20e12, 193.30e12])
quantum = np.array([193.5e12])

show_channel_distribution(classical, quantum)
```

## 数据输出

实验结果保存在 `data/` 目录下，格式为：

```
data/{spacing}GHz {num_c}channel {power}dBm {timestamp}/
├── data.xlsx           # 实验数据表
└── [其他实验数据文件]
```
