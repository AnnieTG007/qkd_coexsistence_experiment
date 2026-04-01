
import math

# ===== 基本系统参数（和你原来的写法一致，可按需修改） =====
spd_eff = 0.1          # 探测效率
loss = 4.61e-5         # 光纤衰减 (m^-1), 4.61e-2 / km -> 4.61e-5 / m
dark_count = 1e-9      # 暗计数/脉冲
photon_launch = 0.1    # 平均光子数 mu
error_opt = 0.01       # 光学误码率（本征误码）
BB84_eff = 0.5         # sifting 系数（BB84 固定 1/2）
correct_error_eff = 1.15  # 纠错效率 f(E)
spd_rate = 1e9         # 脉冲重复率 (Hz)
IL = 8                 # 插入损耗 (dB)

# ===== 有限长密钥修正所需参数（式 (6)(7)）=====
# Q_nu^L = Q_nu * (1 - γ / sqrt(p_nu * Q_nu * N_pulse / 2))
# (E_nu Q_nu)^U = (E_nu Q_nu) * (1 + γ / sqrt(p_nu * E_nu Q_nu * N_pulse / 2))
N_pulse = 1e10         # 发射总脉冲数（可按测量时长 T ≈ spd_rate*T 来设）
gamma_ks = 5.0         # 标准差倍数（5~7 常用，越大越保守）
p_signal = 0.1         # 该示例只用“信号态”，若做多强度诱骗请按各强度的 p_nu 传入

# ====== 工具函数 ======
def H2(x, eps=1e-16):
    """二元熵函数，带稳健保护"""
    x = min(max(x, eps), 1.0 - eps)
    return -x*math.log2(x) - (1-x)*math.log2(1-x)

def _forward_channel(distance, noise_after_spd):
    """
    根据距离与噪声，计算通用中间量:
      eta, Y0, Y1, Q1, Q_ave, e1, e_ave
    说明：
      noise_after_spd：已被SPD效率折算后的噪声（与你原代码保持一致）
    """
    # 信道总体透过率（含插损）
    eta = spd_eff * math.exp(-loss * distance) * 10 ** (-0.1 * IL)

    # 背景与响应
    e0 = 0.5
    Y0 = dark_count + noise_after_spd          # 真空/背景点击率
    Y1 = Y0 + eta                              # 单光子点击率近似
    Q1 = Y1 * photon_launch * math.exp(-photon_launch)  # 单光子增益
    Q_ave = Y0 + 1 - math.exp(-eta * photon_launch)     # 整体增益（所有光子数分布加和）

    # 误码
    e1 = (e0 * Y0 + error_opt * eta) / max(Y1, 1e-30)
    e_ave = (e0 * Y0 + error_opt * (1 - math.exp(-eta * photon_launch))) / max(Q_ave, 1e-30)

    return eta, Y0, Y1, Q1, Q_ave, e1, e_ave

# ===== 无限长密钥 =====
def BB84_SKR_infinite(distance, noise_after_spd):
    _, _, _, Q1, Q_ave, e1, e_ave = _forward_channel(distance, noise_after_spd)
    skr = BB84_eff * (-Q_ave * correct_error_eff * H2(e_ave) + Q1 * (1 - H2(e1)))
    return max(0.0, skr) * spd_rate, e_ave

# ===== 有限长密钥（式 (6)(7)）=====
def BB84_SKR_finite(distance, noise_after_spd,
                    Npulse=N_pulse, gamma=gamma_ks, pnu=p_signal):
    _, _, _, Q1, Q_ave, e1, e_ave = _forward_channel(distance, noise_after_spd)

    # (6) Q_L 修正 —— 只取不小于 0 的物理值
    denom1 = max(pnu * Q_ave * Npulse / 2.0, 1e-30)
    Q_L = Q_ave * (1.0 - gamma / math.sqrt(denom1))
    Q_L = max(Q_L, 0.0)

    # (7) (E Q)^U 修正 —— 只取非负
    EQ = e_ave * Q_ave
    denom2 = max(pnu * EQ * Npulse / 2.0, 1e-30)
    EQ_U = EQ * (1.0 + gamma / math.sqrt(denom2))
    EQ_U = max(EQ_U, 0.0)

    # 用修正后的 Q_L 和 (E Q)^U 进入密钥率：E_ave^U = (EQ)^U / Q_L
    # 做稳健保护，避免 Q_L → 0 时出现除零或>1
    if Q_L <= 0:
        return 0.0, e_ave

    e_ave_U = min(max(EQ_U / Q_L, 0.0), 0.5)  # QBER 物理上不超过 0.5

    skr = BB84_eff * (-Q_L * correct_error_eff * H2(e_ave_U) + Q1 * (1 - H2(e1)))
    return max(0.0, skr) * spd_rate, e_ave