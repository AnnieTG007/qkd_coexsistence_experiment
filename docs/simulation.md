# 仿真模块说明

## 仿真模块 (simulation/)

本目录包含用于方案预评估的物理仿真模块，帮助在实验前估算信道分配方案的性能。

**注意**: 仿真结果仅供参考，实际性能以实验为准。

---

### MCF - 多芯光纤仿真

**文件**: `MCF.py`

**类**: `MulticoreFiber`

**功能**: 仿真光纤中的非线性光学效应

#### 主要仿真效应

1. **拉曼散射 (Raman Scattering)**
   - 前向拉曼散射
   - 后向拉曼散射
   - 芯间拉曼效应

2. **四波混频 (Four-Wave Mixing, FWM)**
   - 简并 FWM
   - 非简并 FWM
   - 芯间 FWM

#### 主要方法

```python
from simulation import MulticoreFiber

mcf = MulticoreFiber()

# 获取前向拉曼散射噪声功率
noise1 = mcf.get_raman_power_all2(classical_channels, power, quantum_freq,
                                   func, distance, coefficient_raman, index_center, f_diff)

# 获取 FWM 噪声功率
noise2 = mcf.get_fwm_power_all3(classical_channels, power, quantum_freq,
                                 func, distance)

# 获取芯间 FWM
noise3 = mcf.get_intercore_four_wave_mixing(...)
```

#### 物理参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 光纤衰减 | 0.2 dB/km | C 波段标准衰减 |
| 有效面积 | 70 μm² | G.652 光纤典型值 |
| 非线性系数 | 1.3e-3 /W/km | C 波段典型值 |
| 工作波长 | 1550 nm | C 波段中心波长 |

---

### BB84_SKR - BB84 协议 SKR 计算

**文件**: `BB84_SKR.py`

**功能**: 计算 BB84 协议的安全密钥率 (Secure Key Rate)

#### 支持的模式

1. **无限长密钥**: `BB84_SKR_infinite()`
   - 忽略有限长统计波动
   - 适合长脉冲/高脉冲数情况

2. **有限长密钥**: `BB84_SKR_finite()`
   - 包含统计波动修正（式 6、7）
   - 适合实际实验评估

#### 主要参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 探测效率 | 10% | 单光子探测器效率 |
| 暗计数 | 1e-9 | 每脉冲暗计数率 |
| 平均光子数 | 0.1 | 信号态平均光子数 |
| 光学误码率 | 1% | 设备本征误码 |
| 脉冲重复率 | 1 GHz | 源脉冲重复频率 |
| 插入损耗 | 8 dB | 系统插入损耗 |

#### 使用方法

```python
from simulation import BB84_SKR_finite

# 距离 (m)
distance = 10e3

# 噪声功率（经探测效率和插入损耗折算后）
noise_after_spd = 1e-6

# 计算 SKR 和 QBER
skr, qber = BB84_SKR_finite(distance, noise_after_spd)
print(f"SKR: {skr:.2e} bps, QBER: {qber:.4f}")
```

#### 有限长修正公式

有限长密钥的 SKR 修正使用以下公式：

$$Q_\nu^L = Q_\nu \left(1 - \frac{\gamma}{\sqrt{p_\nu \cdot Q_\nu \cdot N_{pulse}/2}}\right)$$

$$(E_\nu Q_\nu)^U = E_\nu Q_\nu \left(1 + \frac{\gamma}{\sqrt{p_\nu \cdot E_\nu \cdot Q_\nu \cdot N_{pulse}/2}}\right)$$

其中 $\gamma$ 为标准差倍数（通常取 5~7）。

---

## 联合仿真流程

通常需要联合使用 MCF 和 BB84_SKR 进行方案评估：

```python
import numpy as np
from simulation import MulticoreFiber, BB84_SKR_finite

# 1. 定义信道
classical_channels = np.array([193.10e12, 193.20e12, 193.30e12])
quantum_freq = 193.5e12

# 2. 仿真光纤效应
mcf = MulticoreFiber()
power_dBm = 13
power = np.ones(len(classical_channels)) * 10 ** (power_dBm / 10 - 3)
distance = np.array([10e3])

# 获取噪声
func1 = mcf.get_forward_raman_scatter
noise_raman = mcf.get_raman_power_all2(classical_channels, power, quantum_freq,
                                         func1, distance, coef_raman, idx, f_diff)
func2 = mcf.get_four_wave_mixing
noise_fwm = mcf.get_fwm_power_all3(classical_channels, power, quantum_freq,
                                    func2, distance)[1]

# 3. 折算到探测器
work_wave = 1550e-9
gate_time = 1e-9
spd_eff = 0.1
IL = 8
Planck = 6.62607015e-34
c = 299792458

noise = (noise_raman + noise_fwm) * work_wave * gate_time * spd_eff * 10**(-0.1*IL) / (Planck * c)

# 4. 计算 SKR
skr, qber = BB84_SKR_finite(distance[0], noise[1])
print(f"SKR: {skr:.2e} bps, QBER: {qber:.4f}")
```
