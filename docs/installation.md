# 安装指南

## 环境要求

- Python 3.13 或更高版本
- Windows 操作系统（项目主要在 Windows 环境下开发测试）

## 依赖安装

安装所有依赖：

```bash
pip install -r requirements.txt
```

## 硬件连接

### 设备连接表

| 设备 | 接口类型 | 默认地址/端口 |
|------|----------|---------------|
| WSS (波长选择开关) | 串口 (COM5, COM6) | 115200 baud |
| TLS (可调谐激光源) - MTP | Ethernet | 192.168.1.102 |
| TLS (可调谐激光源) - IQS | Ethernet | 192.168.1.101 |
| OSA (光谱分析仪) | Ethernet | 192.168.1.113:10001 |
| QKD 系统 | SFTP | 192.168.1.20:56100 |

### 网络配置

确保控制主机与各设备处于同一网络段，且防火墙允许以下端口通信：
- TCP 10001 (OSA)
- TCP 22 (SFTP for QKD)
- TCP 502 (VISA for TLS)

### 串口配置

WSS 设备使用两根串口线：
- COM5: 电源控制
- COM6: 信号控制

波特率: 115200

## 配置文件

项目根目录下的主要配置参数在 `main.py` 中：

```python
DISTANCE = 10e3          # 光纤长度 (m)
MAX_POWER = 13           # 激光源发射功率 (dBm)
ACTUAL_POWER = 13        # 实际发射功率 (dBm)
BUFFER_TIME = 600        # 设备缓冲时间 (秒)
INV_TIME = 2400          # QKD 采集时间 (秒)
fq = 193.5e12            # 量子频率 (Hz)
fsyn = 193.3e12          # 同步频率 (Hz)
spacing = 100e9          # 信道间隔 (Hz)
num_c = 8                # 经典信道数量
```

## 验证安装

运行以下命令验证环境和设备连接：

```bash
python main.py
```

首次运行会显示调试信息，验证各设备是否正常连接。
