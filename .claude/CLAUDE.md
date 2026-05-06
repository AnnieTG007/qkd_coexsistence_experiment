# QKD Coexistence Experiment

## 环境

- Python 解释器：`C:\Users\Annie\miniconda3\envs\qkd_env\python.exe`（conda 环境，已在 `.claude/settings.local.json` 中配置 PATH）
- 依赖安装：`pip install -r requirements.txt`

## 项目规范

- **不保留非必要的代码，保持结构清晰**：删除无用代码、功能重复的函数、调试用注释等
- 硬件控制代码放在 `device/` 目录
- 仿真模块放在 `simulation/` 目录
- 工具脚本放在 `tools/` 目录
- 可视化代码放在 `gui/` 目录
- 如果同一个问题卡顿超过10分钟，调用codex帮助你调研和写代码

## 架构概述

- **配置层**：`config.yaml`（实验参数，YAML 格式）→ `config.py`（dataclass 加载，`get_config()` 全局单例）
- **主流程**：`main.py` → `enum_exp_scheme()` 枚举方案 → `exe_exp_scheme()` 执行实验
- **设备层**：`device/` 目录下各模块通过 `__init__.py` 暴露统一接口

## config.yaml 注意事项

- 科学计数法必须带符号：`193.5e+12`（不是 `193.5e12`），否则 YAML 会解析为字符串
- `list_att_initial` 结构为三维：`[device][com_port][switch_port]`（2×2×20）

## 目录结构

```
QKD_Coexistence/
├── main.py                 # 主程序入口
├── config.yaml             # 实验参数配置
├── config.py               # 配置加载（dataclass）
├── requirements.txt
├── device/
│   ├── __init__.py
│   ├── optical_spectrum_analyzer.py  # OSA 控制（光谱扫描、频谱数据CSV保存、带宽分析）
│   ├── wavelength_selective_switch.py # WSS 控制
│   ├── ASE_source.py                # ASE 源控制
│   ├── tunable_laser_source.py      # TLS 控制
│   ├── QKD_log_read.py             # QKD 日志读取（SKR/QBER）
│   └── SFP_source.py               # SFP 可调谐模块控制
├── simulation/
│   ├── __init__.py
│   ├── BB84_SKR.py          # BB84 SKR 计算（finite/infinite）
│   └── MCF.py               # 多芯光纤拉曼散射系数加载
├── tools/
│   ├── count_down.py        # 倒计时工具
│   └── time_corr.py         # 时间序列分析
├── gui/
│   └── channel_viewer.py    # 通道分配可视化
├── data/                    # 实验数据（运行时自动生成）
└── log/                     # QKD 日志（SFTP 下载）
```

## 实验数据保存结构

每次实验在 `data/` 下按参数命名创建根目录，每个方案拥有独立的子文件夹：

```
data/{spacing}GHz {num_c}channel {actual_power}dBm/
├── 1_interleave_100.0GHz/
│   ├── scheme_1_interleave_100.0GHz.bmp   # OSA 频谱图像
│   ├── scheme_1_interleave_100.0GHz.csv   # 频谱数据（波长+功率）
│   ├── scheme_1_interleave_100.0GHz_bandwidth.csv  # 3dB/30dB 带宽
│   ├── 1_QKD_SKR_info.xlsx               # SKR 详情
│   ├── 1_QKD_net_key_info.xlsx           # 密钥/QBER 详情
│   └── 1_<skr>.png                        # SKR 随时间变化图
├── 2_CCA_100.0GHz/
│   └── ...
└── data.xlsx                              # 实验汇总表
```
