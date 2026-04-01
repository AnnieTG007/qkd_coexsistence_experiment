import xlrd
import os
import numpy as np
import datetime
import time
from openpyxl import Workbook
from pathlib import Path

from tools.count_down import countdown
import device
import simulation

# 光纤长度
DISTANCE = 10e3
# 激光源发射功率（单位：dBm）
MAX_POWER = 13
# 经典信号实际发射功率（单位：dBm）
ACTUAL_POWER = 13
# 缓冲时间（单位：秒），用来等待设备调整完成
BUFFER_TIME = 600
# QKD采集时间（单位：秒）
INV_TIME = 2400
# QKD等待时间（单位：秒），密钥量不够时的单位等待时间
wait_time = 600

with xlrd.open_workbook('Ramancrosssection25GHz（25GHz间隔）.xls') as f:
    sheet1 = f.sheets()[0]
    sheet1_cols = sheet1.col_values(1)
    coefficient_raman = np.array(sheet1_cols)  # 拉曼散射系数
    coefficient_raman = coefficient_raman[::-1]
    index_center = 300
    f_diff = 25e9  # 25GHz频率

def classical_signal_array(scheme_name='interleave', num_classic = 8, spacing=50e9, fq=193.5e12, fsyn=193.3e12):
    channel_array = np.zeros(num_classic)
    if scheme_name == 'interleave':
        num_half = num_classic // 2
        relative_neg = np.zeros(num_half)
        relative_pos = np.zeros(num_half)
        for ind in range(num_half):
            relative_neg[ind] = ind - num_half - 0.5
            relative_pos[ind] = ind + 1.5
        channel_array = np.concatenate((relative_neg * spacing + min(fq,fsyn), relative_pos * spacing + max(fq,fsyn)))
    elif scheme_name== 'test':
        relative = np.array([5, 6, 7, 8, 9, 10])
        channel_array = relative * spacing + fq
    elif scheme_name == 'neg_interleave':
        relative = np.zeros(num_classic)
        for i in range(num_classic):
            relative[i] = i - num_classic - 0.5
        channel_array = relative * spacing + min(fsyn, fq)
    elif scheme_name == 'qEFS':
        relative_neg = np.array([-4, -3, -2, -1])
        relative_pos = np.array([1, 2, 3, 4])
        channel_array = np.concatenate((relative_neg * spacing + min(fq, fsyn), relative_pos * spacing + max(fq, fsyn)))
    elif scheme_name == 'CCA':
        relative = np.zeros(num_classic)
        for i in range (num_classic):
            relative[i] = i - num_classic
        channel_array = relative * spacing + fsyn
    elif scheme_name == 'CCA_anti':
        relative = np.zeros(num_classic)
        for i in range (num_classic):
            relative[i] = i + 1
        channel_array = relative * spacing + fq
    elif scheme_name == 'qUFS':
        mcf = simulation.MulticoreFiber()
        start_list = np.arange(-num_classic, 0, 50e9 / spacing)
        min_noise = 1
        channel_array = np.zeros(num_classic)
        for start in start_list:
            c_list = np.zeros(num_classic)
            k = start
            ind = 0
            while ind < num_classic:
                f = fq + k * spacing
                if f < 193.25e12 or f > 193.55e12:
                    c_list[ind] = f
                    ind = ind + 1
                k = k + 1
            p = np.ones(num_classic) * 10 ** (ACTUAL_POWER / 10 - 3)
            z = np.array([DISTANCE])
            func1 = mcf.get_inter_forward_raman_scatter
            noise1 = mcf.get_raman_power_all2(c_list, p, np.array([fq]), func1, z, coefficient_raman, index_center,
                                              f_diff)
            func2 = mcf.get_intercore_four_wave_mixing
            noise2 = mcf.get_fwm_power_all3(c_list, p, np.array([fq]), func2, z)
            if noise2[1] > 0:
                continue
            if min_noise > noise1:
                min_noise = noise1
                channel_array = c_list
    elif scheme_name == 'None':
        channel_array = np.zeros(num_classic)
    else:
        raise ValueError('Unknown scheme: {}'.format(scheme_name))
    return channel_array

def SKR_simulation(c_list, fq=193.5e12):
    mcf = simulation.MulticoreFiber()
    pdBm = ACTUAL_POWER
    p = np.ones(len(c_list)) * 10 ** (pdBm / 10 - 3)
    z = np.array([DISTANCE])
    func1 = mcf.get_forward_raman_scatter
    noise1 = mcf.get_raman_power_all2(c_list, p, np.array([fq]), func1, z, coefficient_raman, index_center,
                                      f_diff)
    func2 = mcf.get_four_wave_mixing
    noise2 = mcf.get_fwm_power_all3(c_list, p, np.array([fq]), func2, z)[1]

    spd_eff = 0.1  # 探测效率为10%
    Planck_constant = 6.62607015 * 10 ** (-34)  # 普朗克常量J·s
    IL = 8  # DWDM插入损耗(8dB)
    gate_time = 1 * 10 ** (-9)  # 探测时间可以为2010 ps，即2.01 ns，也可以是1 ns，这个根据实验去改就是了
    work_wave = 1550 * 1e-9  # 等效工作波长
    c_v = 299792458  # 光速m/s
    noise = (noise1 + noise2) * work_wave * gate_time * spd_eff * 10 ** (-0.1 * IL) / (Planck_constant * c_v)
    skr, qber = simulation.BB84_SKR_finite(DISTANCE, noise)
    return skr, qber

if __name__ == "__main__":
    # spacing = 100e9
    # num_c = 6
    # c1 = classical_signal_array('CCA', num_classic=num_c, spacing=spacing)
    # print(c1)
    # print('CCA SKR, QBER: ', SKR_simulation(c1))
    #
    # c2 = classical_signal_array('JOCA', num_classic=num_c, spacing=spacing)
    # print(c2)
    # print('JOCA SKR, QBER: ', SKR_simulation(c2))
    #
    # c3 = classical_signal_array('CCA_anti', num_classic=num_c, spacing=spacing)
    # print(c3)
    # print('CCA_anti SKR, QBER: ', SKR_simulation(c3))
    #
    # c4 = classical_signal_array('interleave', num_classic=num_c, spacing=spacing)
    # print(c4)
    # print('interleave SKR, QBER: ', SKR_simulation(c4))
    # exit()

    DEBUG_MODE = True
    num_c = 8
    action_time = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')

    # 列举实验所需的信道间隔
    spacing_list = np.array([100e9])
    # 列举实验所需的方案名称（包括提出方案和对比方案）
    scheme_name_list = [] # 'neg_interleave', 'interleave', 'CCA_anti'
    import random
    for i in range(1):
        a = ['CCA_anti','qUFS','interleave', 'None']
        # random.shuffle(a)
        scheme_name_list = scheme_name_list + a

    # 初始化WSS过程
    list_att_initial = np.zeros((2, 2, 20))
    wss1 = device.WSS('COM5', 'COM6', list_att_initial)
    # WSS设备开机
    response = wss1.wsspower('on')
    # WSS设备所用的端口号
    wss_port = np.arange(2, 2*num_c+1, 2)
    wss1.wss_spa(1, 1, 772, 1, 99, 0)
    wss1.wss_spa(2, 1, 772, 1, 99, 0)
    # 这里原本为了保证量子信号隔离度，需要WSS阻塞量子信道所在频率
    fq = 193.5e12
    fsyn = 193.3e12
    wss1.wss_spa_bandwidth(2, fq, 25e9, 1, 2, 0)
    wss1.wss_spa_bandwidth(2, fsyn, 100e9, 1, 2, 0)

    # 初始化TLS过程
    tls1 = device.TLS('192.168.1.102', '192.168.1.101')
    # tls所用的端口号
    tls_port = np.arange(1, num_c+1)
    # TLS设备开机
    for j in tls_port:
        tls1.set_on_and_off(j, 'ON')

    # 依次调整所有变量（方案名称、信道间隔、经典信号发射功率等），形成实验方案
    list_scheme = []
    for spacing in spacing_list:
        for scheme_name in scheme_name_list:
            classical_channel_array = classical_signal_array(scheme_name=scheme_name, num_classic=num_c, spacing=spacing)
            s = {'name':scheme_name, 'list_frequency': classical_channel_array, 'spacing': spacing / 1e9}
            s['title'] = "Scheme_name: {}, Spacing:{} GHz".format(s['name'], s['spacing'])
            list_scheme.append(s)

    # 数据保存
    wb = Workbook()
    sheet = wb.active
    sheet.title = '共纤传输实验结果'

    # 开始进行信道分配方案，注意要打时间戳
    # 开始逐个执行预设方案
    for i in range(len(list_scheme)):
        s = list_scheme[i]
        scheme_name = s['name']
        classical_channel_array = s['list_frequency']
        spacing = s['spacing']
        if DEBUG_MODE:
            print('scheme_name: ',scheme_name)
            if scheme_name != 'None':
                print(classical_channel_array)
                print('SKR, QBER: ', SKR_simulation(classical_channel_array))

        # 执行每个方案前，先阻塞所有的端口
        wss1.wss_spa(1, 1, 772, 1, 99, 0)

        if scheme_name != 'None':
            # 设置经典信号波长，设置TLS和WSS
            for j in range(len(classical_channel_array)):
                # 获取经典信号频率
                f = classical_channel_array[j]
                # TLS设置
                tls1.setFrequencyAndPower(tls_port[j], f, MAX_POWER)
                # WSS设置
                num_device = 1
                num_comPort = 1
                wss1.wss_spa_bandwidth(1, f, 20e9, 1, wss_port[j], max(0, MAX_POWER - ACTUAL_POWER))
                # wss1.wss_spa(1, 1, 772, 1, wss_port[j], max(0, MAX_POWER - ACTUAL_POWER))

        # 给QKD系统恢复时间
        if DEBUG_MODE:
            print('调试信息：QKD系统恢复中')
        time.sleep(BUFFER_TIME)
        if DEBUG_MODE:
            print('调试信息：QKD系统恢复完成')

        if DEBUG_MODE:
            print(classical_channel_array)
            print('循环次数：', i + 1)
            print(['开始执行方案：', s['title']])

        # 记录方案开始的时间戳
        begin_time = datetime.datetime.now()
        s['begin_time'] = begin_time.strftime('%Y-%m-%d %H:%M:%S')

        # 静态方案执行过程
        countdown(INV_TIME)

        # 记录方案结束的时间戳
        end_time = datetime.datetime.now()
        s['end_time'] = end_time.strftime('%Y-%m-%d %H:%M:%S')
        if DEBUG_MODE:
            print(['结束 ', s['title']])

        time.sleep(BUFFER_TIME)

        # 保存实验结果
        dir_name = 'data/' + str(spacing_list / 1e9) + 'GHz ' + str(num_c) + 'channel ' + str(ACTUAL_POWER) + 'dBm ' + action_time
        dir_path = Path(__file__).resolve().parent / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        # 保存OSA图像
        # device.save_current_image(dir_path, i+1)

        # 从QKD设备获取SKR数据
        log_file_path = Path(__file__).resolve().parent / 'log'
        log_file_name = 'qkd.alice-bob.log.0'
        scheme_time_list = [(begin_time, end_time)]
        qkd = device.QKD(update_log=True, time_list=scheme_time_list, log_file_path=log_file_path,
                                log_file_name=log_file_name, data_file_path=dir_path)
        mean_skr = qkd.get_skr_list(i+1)[0]
        qkd.get_key_and_qber(i+1)

        # 保存当前方案数据
        s = list_scheme[i]
        sheet.append([i + 1, s['title']])
        sheet.append(['', 'begin_time', s['begin_time']])
        sheet.append(['', 'end_time', s['end_time']])
        sheet.append(['', 'power(dBm)', ACTUAL_POWER])
        sheet.append(['', 'distance(km)', DISTANCE])
        sheet.append(['', 'spacing(GHz)', s['spacing']])
        sheet.append(['', 'secure key rate(bps)', mean_skr])
        sheet.append(['', 'list_frequency'] + s['list_frequency'].tolist())
        wb.save(dir_path / 'data.xlsx')

print('——所有数据保存完成——')