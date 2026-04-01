# 硬件设备说明

## 设备控制模块 (device/)

本目录包含所有硬件设备的控制模块，通过串口或网络接口与物理设备通信。

### WSS - 波长选择开关

**文件**: `wavelength_selective_switch.py`

**类**: `WavelengthSelectiveSwitch`

**接口**: 串口 (COM5 电源控制, COM6 信号控制)

**功能**:
- 开关机控制
- 信道带宽设置
- 衰减补偿
- 频率分配

**主要方法**:

```python
from device import WSS

# 初始化
wss = WSS('COM5', 'COM6', list_att_initial)

# 开机
wss.wsspower('on')

# 设置信道
wss.wss_spa_bandwidth(port, frequency, bandwidth, ...)
```

---

### TLS - 可调谐激光源

**文件**: `tunable_laser_source.py`

**类**: `TunableLaserSource`

**接口**: 以太网 (TCP/IP via VISA)

**地址**:
- MTP: `192.168.1.102`
- IQS: `192.168.1.101`

**功能**:
- 激光开关控制
- 频率设置
- 功率设置

**主要方法**:

```python
from device import TLS

# 初始化
tls = TLS('192.168.1.102', '192.168.1.101')

# 设置频率和功率
tls.setFrequencyAndPower(channel, frequency, power_dBm)

# 开关控制
tls.set_on_and_off(channel, 'ON'|'OFF')
```

---

### OSA - 光谱分析仪

**文件**: `optical_spectrum_analyzer.py`

**类**: `OpticalSpectrumAnalyzer`

**接口**: 以太网 (TCP)

**地址**: `192.168.1.113:10001`

**功能**:
- 光谱采集
- 峰值检测
- 图像保存

**主要方法**:

```python
from device import OSA

# 初始化
osa = OSA('192.168.1.113', 10001)

# 连接
osa.tcp_connect()

# 获取光谱数据
data = osa.query_trace_data()

# 断开
osa.disconnect()
```

---

### ASE - 放大自发辐射源

**文件**: `ASE_source.py`

**类**: `ASESource`

**接口**: 串口

**功能**:
- ASE 源开关控制
- 功率调节

---

### QKD - QKD 系统日志读取

**文件**: `QKD_log_read.py`

**类**: `QKDLogRead`

**接口**: SFTP (SSH)

**地址**: `192.168.1.20:56100`

**功能**:
- 日志文件读取
- SKR 数据提取
- QBER 数据提取
- 密钥量获取

**主要方法**:

```python
from device import QKD

# 初始化
qkd = QKD(update_log=True, time_list=[(begin_time, end_time)],
          log_file_path='log/', log_file_name='qkd.alice-bob.log.0')

# 获取 SKR 列表
skr_list = qkd.get_skr_list(scheme_index)

# 获取密钥和 QBER
qkd.get_key_and_qber(scheme_index)
```

---

### SFP - SFP 光源模块

**文件**: `SFP_source.py`

**类**: `SFP`

**接口**: 串口

**功能**:
- SFP 模块控制
- 频率/功率设置
