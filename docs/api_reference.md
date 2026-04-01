# API 参考文档

## device 模块

设备控制模块，提供对各硬件设备的 Python 接口。

```python
from device import ASE, OSA, WSS, QKD, TLS
```

### ASE

```python
from device import ASE

ASESource(com_port, baudrate=115200, timeout=2)
```

| 方法 | 说明 |
|------|------|
| `power_on()` | 开启 ASE 源 |
| `power_off()` | 关闭 ASE 源 |
| `set_power(level)` | 设置功率级别 |

### OSA

```python
from device import OSA

OpticalSpectrumAnalyzer(osa_ip, osa_port, Timeout=5, Terminator='\r\n')
```

| 方法 | 说明 |
|------|------|
| `tcp_connect()` | 建立 TCP 连接 |
| `disconnect()` | 断开连接 |
| `send_command(cmd)` | 发送 SCPI 命令 |
| `query_trace_data()` | 查询光谱数据 |
| `save_current_image(path)` | 保存当前光谱图像 |

### WSS

```python
from device import WSS

WavelengthSelectiveSwitch(com_power, com_control, list_att, terminator='\r')
```

| 方法 | 说明 |
|------|------|
| `wsspower('on'|'off')` | 开关机 |
| `wss_spa(...)` | 设置信道参数 |
| `wss_spa_bandwidth(...)` | 设置信道带宽 |

### QKD

```python
from device import QKD

QKDLogRead(update_log=True, time_list=[], log_file_path='log/',
           log_file_name='qkd.alice-bob.log.0', data_file_path='data/')
```

| 方法 | 说明 |
|------|------|
| `get_skr_list(scheme_index)` | 获取 SKR 数据列表 |
| `get_key_and_qber(scheme_index)` | 获取密钥量和 QBER |

### TLS

```python
from device import TLS

TunableLaserSource(mtp_ip, iqs_ip)
```

| 方法 | 说明 |
|------|------|
| `set_on_and_off(channel, 'ON'\|'OFF')` | 开关控制 |
| `setFrequencyAndPower(channel, frequency, power_dBm)` | 设置频率和功率 |
| `set_wavelength(channel, wavelength_nm)` | 设置波长 |

---

## simulation 模块

物理仿真模块，用于方案预评估。

```python
from simulation import MulticoreFiber, BB84_SKR_finite
```

### MulticoreFiber

```python
mcf = MulticoreFiber()
```

| 方法 | 说明 |
|------|------|
| `get_forward_raman_scatter(...)` | 前向拉曼散射 |
| `get_inter_forward_raman_scatter(...)` | 芯间前向拉曼 |
| `get_raman_power_all2(...)` | 拉曼功率计算 |
| `get_four_wave_mixing(...)` | 四波混频 |
| `get_intercore_four_wave_mixing(...)` | 芯间四波混频 |
| `get_fwm_power_all3(...)` | FWM 功率计算 |

### BB84_SKR

```python
BB84_SKR_infinite(distance, noise_after_spd)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `distance` | float | 光纤距离 (m) |
| `noise_after_spd` | float | 探测器后噪声 |

返回: `(skr, qber)` - 安全密钥率 (bps) 和量子误码率

```python
BB84_SKR_finite(distance, noise_after_spd, Npulse=1e10, gamma=5.0, pnu=0.1)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `distance` | float | 光纤距离 (m) |
| `noise_after_spd` | float | 探测器后噪声 |
| `Npulse` | float | 总脉冲数 |
| `gamma` | float | 标准差倍数 (5~7) |
| `pnu` | float | 信号态概率 |

返回: `(skr, qber)` - 安全密钥率 (bps) 和量子误码率

---

## tools 模块

### count_down

```python
from tools.count_down import countdown

countdown(seconds)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `seconds` | int | 倒计时秒数 |

### time_corr

```python
from tools.time_corr import (
    read_time_series_from_excel,
    summarize_sampling,
    maybe_resample,
    autocorr_report
)
```

| 函数 | 说明 |
|------|------|
| `read_time_series_from_excel(filepath)` | 从 Excel 读取时间序列 |
| `summarize_sampling(series)` | 采样间隔统计 |
| `maybe_resample(series, target_interval)` | 重采样处理 |
| `autocorr_report(series)` | 自相关分析报告 |

---

## gui.channel_viewer

通道分配可视化工具。

```python
from gui.channel_viewer import show_channel_distribution, ChannelDistributionWindow
```

### show_channel_distribution

```python
show_channel_distribution(classical_channels, quantum_channels, window_title='Channel Distribution Viewer')
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `classical_channels` | np.ndarray | 经典信道频率 (Hz) |
| `quantum_channels` | np.ndarray | 量子信道频率 (Hz) |
| `window_title` | str | 窗口标题 |

---

## main.py 主程序参数

`main.py` 中的主要配置参数：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DISTANCE` | 10e3 | 光纤长度 (m) |
| `MAX_POWER` | 13 | 激光源发射功率 (dBm) |
| `ACTUAL_POWER` | 13 | 实际发射功率 (dBm) |
| `BUFFER_TIME` | 600 | 设备缓冲时间 (秒) |
| `INV_TIME` | 2400 | QKD 采集时间 (秒) |
| `wait_time` | 600 | QKD 等待时间 (秒) |
| `fq` | 193.5e12 | 量子频率 (Hz) |
| `fsyn` | 193.3e12 | 同步频率 (Hz) |
| `spacing` | 100e9 | 信道间隔 (Hz) |
| `num_c` | 8 | 经典信道数量 |
| `DEBUG_MODE` | True | 调试模式开关 |

### classical_signal_array 函数

```python
classical_signal_array(scheme_name='interleave', num_classic=8,
                        spacing=50e9, fq=193.5e12, fsyn=193.3e12)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `scheme_name` | str | 方案名称 |
| `num_classic` | int | 经典信道数 |
| `spacing` | float | 信道间隔 (Hz) |
| `fq` | float | 量子频率 (Hz) |
| `fsyn` | float | 同步频率 (Hz) |

### SKR_simulation 函数

```python
SKR_simulation(c_list, fq=193.5e12)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `c_list` | np.ndarray | 经典信道频率数组 |
| `fq` | float | 量子频率 (Hz) |

返回: `(skr, qber)` - 预期 SKR 和 QBER
