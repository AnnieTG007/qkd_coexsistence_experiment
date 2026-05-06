# -*- coding: utf-8 -*-
import numpy as np
from itertools import permutations
from itertools import combinations
import xlrd
from pathlib import Path

raman_file = Path(__file__).resolve().parent.parent / 'simulation' / 'Ramancrosssection25GHz（25GHz间隔）.xls'
with xlrd.open_workbook(str(raman_file)) as f:
    sheet1 = f.sheets()[0]
    sheet1_cols = sheet1.col_values(1)
    coefficient_raman = np.array(sheet1_cols)  # 拉曼散射系数
    coefficient_raman = coefficient_raman[::-1]
    index_center = 300
    f_diff = 25e9  # 25GHz频率


class MulticoreFiber(object):
    """
    本类为多芯光纤仿真使用的类也可以实现部分单芯光纤的仿真
    单位使用标准单位，即输入的频率使用Hz，传输距离使用m，不要使用THz，km等单位
    """

    def __init__(self):
        """
        这些参数的初值不建议在此更改，请生成对象时自己更改。
        """
        # print('初始化了')
        # self.name = name
        # self.distance = distance
        # 以下所有参数以1550nm的C波段为准，如果使用1310nm的O波段，色散衰减等数值会发生变化
        self.loss = 0.2 / 4.343 * 1e-3  # 光纤的衰减4.61 * 10 ^ (-2) / km，转化为m
        self.loss_c = 0.2 / 4.343 * 1e-3  # 算芯间拉曼的时候有些用，不过这个还是都设为C波段，如果使用O波段需要更改
        self.loss_q = 0.2001 / 4.343 * 1e-3  # 算芯间拉曼的时候有些用
        self.loss_dB = 0.2 * 1e-3  # 衰减0.2 dB / km，单位是m
        self.D_c = 17 * 10 ** (-6)  # 色散常数为17 ps / nm - km
        self.D_s = 0.056 * 10 ** 3  # 色散斜率为0.056 ps / nm ^ 2 - km
        self.A_eff = 70 * 10 ** (-12)  # 有效面积70 um ^ 2
        self.CW = 1550 * 10 ** (-9)  # 工作波长1550 nm
        self.FW = 193.4 * 10 ** 12  # 工作频率193.4 THz
        self.c = 299792458  # 光速m / s
        self.e3 = 6.1796e-14
        # 三阶电极化率, m ^ 3 / (W * s)。有两个值6 * 10 ^ (-15)，这个值是从非线性光纤光学中得到的，6.1796e-14这个值是从gamma = 1.3e-3算过来的
        self.kappa = 4e-7  # 芯间模耦合系数卡帕，根据芯间功率耦合系数h计算得来。
        self.n = 1.45  # 折射率
        self.hmn = 1e-9  # 功率耦合系数1e - 6 / km
        # self.k = 0.02  # 芯间耦合系数卡帕
        self.recapture_factor_Rayleigh = 1.5e-3
        self.loss_Rayleigh = 3.2e-5  # 瑞利散射的衰减3.2 * 10 ^ (-2) / km，转化为m
        self.gamma = 1.3e-3  # 非线性系数
        # 以下为SPD计算时的参数，不过没写。。。所以没啥用
        self.width = 0.12e-9  # 滤波器带宽0.12nm
        self.Planck_constant = 6.62607015 * 10 ** (-34)  # 普朗克常量J·s
        self.gate_time = 1000 * 10 ** (-12)  # 探测时间为2010 ps，即2.01ns，也可以是1ns，这个根据实验去改就是了
        self.u = 0.1  # 每脉冲平均光子数，这个可以随便设，因为实验只能测噪声……
        self.dark_count = 10 ** (-6)  # 暗计数的单脉冲数值
        self.probe = 1 * 10 ** 7  # 每秒探测10M次
        self.eff = 0.1  # 探测效率为10 %
        self.q = 0.5  # 固定效率BB84为50 %
        self.fE = 1.15  # 双向纠错算法纠错效率
        self.opt = 0.01  # 0.5 * (1 - 98 %)光学设备引入的误码率

    # FWM计算相关
    def get_phase_matching_factor(self, fi, fj, fk):
        """
        计算相位匹配因子。由于相位匹配因子与距离无关，这样可以减少计算量。
        :param fi: 第一个频率
        :param fj: 第二个频率
        :param fk: 第三个频率
        :return: 相位匹配因子
        """
        f = fi + fj - fk  # 四波混频频率
        w = self.c / f  # 转化为波长
        beta = 2 * np.pi * w ** 2 / self.c * np.abs(fi - fk) * np.abs(fj - fk)\
            * (self.D_c + w ** 2 / 2 / self.c * (np.abs(fi - fk) + np.abs(fj - fk)) * self.D_s)
        return beta

    def get_four_wave_mixing(self, fi, fj, fk, pi, pj, pk, beta, z: np.ndarray):
        """
        计算四波混频的功率。
        :param fi: 第一个频率
        :param fj: 第二个频率
        :param fk: 第三个频率
        :param pi: 第一个频率对应的功率
        :param pj: 第二个频率对应的功率
        :param pk: 第三个频率对应的功率
        :param beta: 相位匹配因子
        :param z: 传输距离
        :return: f_fwm: 四波混频所在频率，p_fwm: 四波混频功率
        """
        if np.abs(fi-fj) < 10**6:
            D = 3  # 如果相等，D=3
        else:
            D = 6  # 如果不相等，D=6

        f_fwm = fi + fj - fk  # 四波混频频率
        w_fwm = self.c / f_fwm  # 四波混频波长
        # 有波动
        # eta = self.loss ** 2 / (self.loss ** 2 + beta ** 2) \
        #     * (1 + (4 * np.exp(-self.loss * z) * np.sin(beta * z / 2) ** 2 / (1 - np.exp(-self.loss * z)) ** 2))
        # 无波动
        eta = self.loss ** 2 / (self.loss ** 2 + beta ** 2) \
            * (1 + (4 * np.exp(-self.loss * z) / (1 - np.exp(-self.loss * z)) ** 2))

        eff_distance = (1 - np.exp(-self.loss * z)) / self.loss
        gamma = (32 * np.pi ** 3 * self.e3) / (self.n ** 2 * w_fwm * self.c * self.A_eff)
        p_fwm = eta * (D * gamma) ** 2. * eff_distance ** 2. * pi * pj * pk * np.exp(-self.loss * z)

        return f_fwm, p_fwm

    def get_intercore_four_wave_mixing(self, fi, fj, fk, pi, pj, pk, beta, z):

        if np.abs(fi-fj) < 10**6:
            D = 3  # 如果相等，D=3
        else:
            D = 6  # 如果不相等，D=6

        f_fwm = fi + fj - fk  # 四波混频频率
        w_fwm = self.c / f_fwm  # 四波混频波长

        gamma = (32 * np.pi ** 3 * self.e3) / (self.n ** 2 * w_fwm * self.c * self.A_eff)
        I = np.exp(-self.loss * z) / (self.loss ** 2 + beta ** 2) \
            * (beta * np.sin(beta * z)-self.loss * np.cos(beta * z))
        C = (beta ** 2 - 3 * self.loss ** 2)/(2 * self.loss * (self.loss ** 2 + beta ** 2))

        p_fwm = self.hmn * np.exp(-self.loss * z)/(self.loss ** 2 + beta ** 2) \
                * 256 * np.pi**4 * (2 * np.pi * f_fwm)**2 / (self.n ** 4 * self.c ** 4)\
                * (D * self.e3) ** 2 * pi * pj * pk/self.A_eff ** 2 \
                * (-np.exp(-2 * self.loss * z) / 2 / self.loss - 2 * I + z + C)

        return f_fwm, p_fwm

    def get_backward_intercore_four_wave_mixing(self, fi, fj, fk, pi, pj, pk, beta, z):
        if np.abs(fi-fj) < 1e-5:
            D = 3  # 如果相等，D=3
        else:
            D = 6  # 如果不相等，D=6
        f = fi+fj-fk
        w = self.c/f
        M = 1024*np.pi**6/(self.n**4*w**2*self.c**2)*(D*self.e3)**2/self.A_eff**2*pi*pj*pk
        S = -(np.exp(-4*self.loss*z))/(4*self.loss)-(2*np.exp(-3*self.loss*z))/(9*self.loss**2+beta**2)*\
            (beta*np.sin(beta*z)-3*self.loss*np.cos(beta*z))-np.exp(-2*self.loss*z)/(2*self.loss)
        p = self.recapture_factor_Rayleigh*self.loss_Rayleigh*self.hmn*M/(self.loss**2+beta**2)\
            *(S*z-np.exp(-4*self.loss*z)/(16*self.loss**2)\
              +2*np.exp(-3*self.loss*z)/(9*self.loss**2+beta**2)**2*((9*self.loss**2-beta**2)*np.cos(beta*z)-6*self.loss*beta*np.sin(beta*z))\
              -np.exp(-2*self.loss*z)/(4*self.loss**2)+1/(16*self.loss**2)-2*(9*self.loss**2-beta**2)/\
              (9*self.loss**2+beta**2)**2+1/(4*self.loss**2))
        return f, p

    def get_fwm_power_all(self, ls_f: np.array, ls_p: np.array, function, z: np.ndarray):
        """
        输入一组信道频率和功率，输出产生的所有四波混频及其对应信道。
        :param ls_f: 信道频率频率
        :param ls_p: 信道功率
        :param function: 要计算的函数，可以使用各种四波混频相关的函数
        :param z: 传输距离，请保证输入的是一个数组，而不是一个元素。即使只有一个点也要写成数组。
        :return: out_ls_f: 信道频率; out_ls_p: 信道功率
        """
        index_non_zeros = np.nonzero(ls_p)
        f = ls_f[index_non_zeros]
        p = ls_p[index_non_zeros]
        len_input = len(index_non_zeros[0])
        list_permutations = self.get_fwm_permutations(len_input)
        out_ls_f = ls_f.copy()
        len_distance = len(z)
        len_out_ls_f = len(out_ls_f)
        out_ls_p = np.zeros([len_out_ls_f, len_distance], dtype=np.float)
        for ls in list_permutations:
            beta = self.get_phase_matching_factor(f[ls[0]], f[ls[1]], f[ls[2]])
            out_f, out_p = function(f[ls[0]], f[ls[1]], f[ls[2]], p[ls[0]], p[ls[1]], p[ls[2]], beta, z)
            j1 = np.where(np.abs(out_ls_f - out_f) < 10**8)[0]  # 获得计算的FWM信号在原始信号中的索引。注意np.where返回的是一个长度为1的tuple
            if len(j1) > 2:  # 不应该出现这种情况
                raise RuntimeError('计算出的有两个匹配的值。')
            elif len(j1) == 1:  # 中心频率已存在就添加到对应的功率位置

                out_ls_p[j1, :] = out_ls_p[j1, :] + [out_p, ]
            else:  # 中心频率不存在就添加到末尾
                out_ls_p = np.row_stack((out_ls_p, out_p))
                out_ls_f = np.append(out_ls_f, out_f)
        index = np.argsort(out_ls_f)  # 排序
        out_ls_f = out_ls_f[index]  # 频率由小到大
        out_ls_p = out_ls_p[index]  # 功率和频率对应
        return out_ls_f, out_ls_p

    def get_fwm_power_all2(self, ls_f: np.array, ls_p: np.array, function, z: np.ndarray):
        """
        输入一组信道频率和功率，输出产生在给定输入信道上的四波混频。
        :param ls_f: 信道频率频率，从低频到高频
        :param ls_p: 信道功率
        :param function: 要计算的函数，可以使用各种四波混频相关的函数
        :param z: 传输距离
        :return: out_ls_f: 信道频率; out_ls_p: 信道功率
        """
        # 找出功率不为0的信道
        index_non_zeros = np.nonzero(ls_p)
        f = ls_f[index_non_zeros]
        p = ls_p[index_non_zeros]
        len_input = len(index_non_zeros[0])
        list_permutations = self.get_fwm_permutations(len_input)
        out_ls_f = ls_f.copy()
        len_distance = len(z)
        len_out_ls_f = len(out_ls_f)
        out_ls_p = np.zeros([len_out_ls_f, len_distance], dtype=np.float)
        for ls in list_permutations:
            beta = self.get_phase_matching_factor(f[ls[0]], f[ls[1]], f[ls[2]])
            out_f, out_p = function(f[ls[0]], f[ls[1]], f[ls[2]], p[ls[0]], p[ls[1]], p[ls[2]], beta, z)
            # 获得计算的FWM信号在原始信号中的索引，两个频率相差低于100M时判定为相同。注意np.where返回的是一个长度为1的tuple
            j1 = np.where(np.abs(out_ls_f - out_f) < 10 ** 8)[0]
            if len(j1) > 2:  # 不应该出现这种情况
                raise RuntimeError('计算出的有两个匹配的值。')
            elif len(j1) == 1:  # 中心频率已存在就添加到对应的功率位置，不存在就不管了

                out_ls_p[j1, :] = out_ls_p[j1, :] + [out_p, ]
        return out_ls_f, out_ls_p

    def get_fwm_power_all3(self, ls_f_class, ls_p_class, ls_f_quantum, function, z: np.ndarray):
        """
        输入经典量子的波长，计算落在量子信道上的四波混频。并不限制量子信号和经典信道相同。
        :param ls_f_class: 经典频率
        :param ls_p_class: 经典功率
        :param ls_f_quantum: 量子频率，准确的说是要计算的信道上的频率
        :param function: 函数
        :param z: 传输距离
        :return: out_ls_f量子信道的频率，out_ls_p: 量子信道的功率
        """
        index_non_zeros = np.nonzero(ls_p_class)
        f = ls_f_class[index_non_zeros]
        p = ls_p_class[index_non_zeros]
        len_input = len(index_non_zeros[0])
        list_permutations = self.get_fwm_permutations(len_input)
        out_ls_f = ls_f_quantum.copy()
        len_distance = len(z)
        len_out_ls_f = len(out_ls_f)
        out_ls_p = np.zeros([len_out_ls_f, len_distance], dtype=np.float32)
        for ls in list_permutations:
            # beta = self.get_phase_matching_factor(f[ls[0]], f[ls[1]], f[ls[2]])
            # out_f, out_p = function(f[ls[0]], f[ls[1]], f[ls[2]], p[ls[0]], p[ls[1]], p[ls[2]], beta, z)
            # # 获得计算的FWM信号在原始信号中的索引，两个频率相差低于100M时判定为相同。注意np.where返回的是一个长度为1的tuple
            # j1 = np.where(np.abs(out_ls_f - out_f) < 10 ** 8)[0]
            # if len(j1) > 1:  # 不应该出现这种情况
            #     raise RuntimeError('计算出的有多个匹配的值。')
            # elif len(j1) == 1:  # 中心频率已存在就添加到对应的功率位置，不存在就不管了
            #     out_ls_p[j1, :] = out_p
            out_f = f[ls[0]] + f[ls[1]] - f[ls[2]]
            j1 = np.where(np.abs(out_ls_f - out_f) < 10 ** 5)[0]
            if len(j1) > 1:  # 不应该出现这种情况
                raise RuntimeError('计算出的有多个匹配的值。')
            elif len(j1) == 1:  # 中心频率已存在就添加到对应的功率位置，不存在就不管了
                beta = self.get_phase_matching_factor(f[ls[0]], f[ls[1]], f[ls[2]])
                out_f, out_p = function(f[ls[0]], f[ls[1]], f[ls[2]], p[ls[0]], p[ls[1]], p[ls[2]], beta, z)
                out_ls_p[j1, :] = out_ls_p[j1, :] + [out_p,]
        return out_ls_f, out_ls_p

    @staticmethod
    def get_fwm_permutations(n):
        """
        对于n个数进行分配组合算法，仅针对四波混频
        :param n:
        :return: fwm_permutations，输出一个列表，每个元素是含有三个元素的元组。
        """
        index_list = np.arange(n)
        fwm_permutations = []  # 输出的数组
        for c1 in combinations(index_list, 3):
            # 有三个元素参与的组合
            for c2 in combinations(c1, 2):
                h = []
                for v in c2:
                    h.append(v)
                for v2 in c1:
                    if v2 not in c2:
                        h.append(v2)
                        break
                fwm_permutations.append(tuple(h))

        for c1 in permutations(index_list, 2):
            h = [c1[0], c1[0], c1[1]]
            fwm_permutations.append(tuple(h))

        return fwm_permutations

    # 拉曼散射计算相关
    def get_raman_eta(self, f_pump, f_signal, list_eta_raman, index_center, f_diff):
        """
        获得泵浦光和信号光之间的拉曼散射系数
        :param f_pump: 泵浦光频率
        :param f_signal: 信号光频率
        :param list_eta_raman: 拉曼散射系数数组
        :param index_center: 泵浦光所在标号
        :param f_diff: 拉曼散射系数各个元素之间的信道间隔
        :return: 拉曼散射系数
        """
        index = int(round((f_signal - f_pump)/f_diff))  # 四舍五入取整
        eta = list_eta_raman[index_center + index] * (f_signal / (193.4e12 + index * f_diff))**4
        return eta

    def get_forward_raman_scatter(self, p: np.array, z: np.array, eta):
        """
        计算前向拉曼散射功率
        :param p: 输入功率
        :param z: 传输距离
        :param eta: 拉曼散射系数
        :return: 输出功率
        """
        pout = eta * p * np.exp(-self.loss * z) * z * self.width
        return pout

    def get_forward_raman_scatter2(self, p: np.array, z: np.array, eta):
        return p * np.exp(-self.loss_q * z) * (1-np.exp(- (self.loss_c-self.loss_q) * z))/(self.loss_c-self.loss_q) * eta * self.width

    def get_backward_raman_scatter(self, p: np.array, z: np.array, eta):
        """
        计算后向拉曼散射功率
        :param p: 输入功率
        :param z: 传输距离
        :param eta: 拉曼散射系数
        :return: 输出功率
        """
        pout = eta * p * (1 - np.exp(-2 * self.loss * z)) / (2 * self.loss) * self.width
        return pout

    def get_backward_raman_scatter2(self, p: np.array, z: np.array, eta):
        return p * (1 - np.exp(- (self.loss_c + self.loss_q) * z)) / (self.loss_c + self.loss_q) * eta * self.width

    def get_inter_forward_raman_scatter(self, p, z, eta):
        return eta * p * np.exp(-self.loss_q * z) * ((np.exp((self.loss_q-self.loss_c) * z)-1)/(self.loss_q-self.loss_c)
                                                     -(np.exp((self.loss_q-self.loss_c - 2 * self.hmn) * z)-1)/(self.loss_q-self.loss_c - 2 * self.hmn))* self.width

    def get_inter_backward_raman_scatter(self, p, z, eta):
        return eta * p * ((np.exp(-(self.loss_q + self.loss_c + 2 * self.hmn)*z)-1)/(self.loss_q + self.loss_c + 2 * self.hmn)
                          -(np.exp(-(self.loss_q + self.loss_c)*z)-1)/(self.loss_q + self.loss_c)) * self.width

    def get_raman_power_all(self, ls_f: np.array, ls_p: np.array, function, z: np.ndarray,
                            list_eta_raman, index_center, f_diff):
        """
        计算输入信道上的拉曼散射功率
        :param ls_f: 所有信道的频率
        :param ls_p: 对应的功率
        :param function: 要计算的函数
        :param z: 传输距离
        :param list_eta_raman: 拉曼散射系数表
        :param index_center: 泵浦光索引
        :param f_diff: 拉曼散射系数的频率间隔
        :return: out_ls_p所有信道在每一个距离上对应的功率
        """
        # 找出功率不为0的信道
        z = np.array(z)
        index_non_zeros = np.nonzero(ls_p)
        f = ls_f[index_non_zeros]
        p = ls_p[index_non_zeros]
        # 初始化输出
        len_z = len(z)
        len_out_f = len(ls_f)
        out_ls_p = np.zeros([len_out_f, len_z])
        # 计算
        index_f = 0  # 要计算的信道所在的位置
        for vf1 in ls_f:
            eta_sum = 0
            for vf2, vp in zip(f, p):
                # 没有使用系数直接求合的写法，考虑到可能存在各个信道功率不相等的情况
                eta = self.get_raman_eta(vf2, vf1, list_eta_raman, index_center, f_diff)
                # print(eta)
                out_ls_p[index_f] += function(vp, z, eta)
            index_f += 1
        return out_ls_p

    def get_raman_power_all2(self, ls_f: np.array, ls_p: np.array, ls_quantum: np.ndarray, function, z: np.ndarray,
                            list_eta_raman, index_center, f_diff):
        """
        输出指定信道上的频率
        :param ls_f: 输入信道
        :param ls_p: 输入功率
        :param ls_quantum: 量子信道频率
        :param function: 需要计算的函数
        :param z: 传输距离
        :param list_eta_raman: 拉曼列表
        :param index_center: 拉曼中心频率
        :param f_diff: 拉曼两个间隔差
        :return: 指定量子信道频率上的每个距离上的拉曼噪声
        """
        # 找出功率不为0的信道
        z = np.array(z)
        index_non_zeros = np.nonzero(ls_p)[0]
        f = ls_f[index_non_zeros]
        p = ls_p[index_non_zeros]
        # 初始化输出
        len_z = len(z)
        len_out_f = len(ls_quantum)
        out_ls_p = np.zeros([len_out_f, len_z])
        # 计算
        index_f = 0  # 要计算的信道所在的位置
        for vf1 in ls_quantum:

            for vf2, vp in zip(f, p):
                # 没有使用系数直接求合的写法，考虑到可能存在各个信道功率不相等的情况
                eta = self.get_raman_eta(vf2, vf1, list_eta_raman, index_center, f_diff)
                # print(eta)
                out_ls_p[index_f] += function(vp, z, eta)
            index_f += 1
        return out_ls_p

    def get_raman_power_all_O_quantum_C_classical(self, ls_f, ls_p, ls_quantum, function, z, eta_raman_O):
        # 找出功率不为0的信道
        z = np.array(z)
        index_non_zeros = np.nonzero(ls_p)[0]
        f = ls_f[index_non_zeros]
        p = ls_p[index_non_zeros]
        # 初始化输出
        len_z = len(z)
        len_out_f = len(ls_quantum)
        out_ls_p = np.zeros([len_out_f, len_z])
        # 计算
        index_f = 0  # 要计算的信道所在的位置
        for vf1 in ls_quantum:

            for vf2, vp in zip(f, p):

                eta = eta_raman_O
                # print(eta)
                out_ls_p[index_f] += function(vp, z, eta)
            index_f += 1
        return out_ls_p

    def __str__(self):
        return 'Multicore, hmn={}/m'.format(self.hmn)


if __name__ == '__main__':
    with xlrd.open_workbook('Ramancrosssection25GHz（25GHz间隔）.xls') as f:
        sheet1 = f.sheets()[0]
        sheet1_cols = sheet1.col_values(1)
        coefficient_raman = np.array(sheet1_cols)  # 拉曼散射系数
        coefficient_raman = coefficient_raman[::-1]
        index_center = 300
        f_diff = 25e9  # 25GHz频率