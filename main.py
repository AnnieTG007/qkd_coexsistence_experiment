import xlrd
import numpy as np
import datetime
import time
from openpyxl import Workbook
from pathlib import Path
import config
from config import Config
from tools.count_down import countdown
import device

# ————————全局常数区————————
# 光纤长度（单位：m）
DISTANCE = 10e3
# 激光源发射功率（单位：dBm）
MAX_POWER = 13
# 经典信号实际发射功率（单位：dBm）
ACTUAL_POWER = 13
# QKD开机采集时间/关闭经典信道缓冲时间（单位：秒）
INV_TIME = 2400

def classical_signal_array(cfg: Config):
    return []

def init_wss(cfg:Config):
    # 定义wss初始端口衰减（全部为0）
    list_att_initial = np.array(cfg.device.wss1.list_att_initial)
    # 定义wss对象
    wss = device.WSS(cfg.device.wss1.com_power, cfg.device.wss1.com_control, list_att_initial)
    # wss设备开机
    response = wss.wsspower('on')
    # 如果开机异常，打印返回信息
    if 'OK' not in response:
        print(response)

    # 初始化时阻塞所有端口，所用wss为2×20，num_device1用于MUX，num_device2用于DEMUX
    for i in range(1, 3):
        wss.wss_spa(num_device=i, begin_slot=1, end_slot=772, com_port=1,  switch_port=99, att=0)

    # 将量子信道所在的2号端口对应量子信道和同步信道频率衰减修改为0
    for i in range(1, 3):
        wss.wss_spa_bandwidth(num_device=i, frequency=cfg.experiment.fq, bandwidth=20e9, com_port=1, switch_port=2, att=0)
        wss.wss_spa_bandwidth(num_device=i, frequency=cfg.experiment.fsyn, bandwidth=100e9, com_port=1,  switch_port=2, att=0)

    return wss

def init_ase(cfg:Config):
    ase_settings = cfg.device.ase
    ase = device.ASE(ase_settings.port, ase_settings.baud)
    ase.set_target_power_mw(ase_settings.target_power_mw)
    return ase

def init_tls(cfg=config.get_config()):
    # 初始化TLS过程
    tls = device.TLS(cfg.device.tls.mtp_ip, cfg.device.tls.iqs_ip)
    # tls所用的端口号
    tls_port = np.arange(1, num_c + 1)
    # TLS设备开机
    for j in tls_port:
        tls.set_on_and_off(j, 'ON')
    return tls

def enum_exp_scheme(cfg: Config):
    scheme_list = []

    import random
    spacing_list = np.array(cfg.experiment.spacing_list)
    scheme_name_list = []

    # 重复实验，避免偶发性对SKR数值的影响
    for i in range(cfg.experiment.repetition):
        a = cfg.experiment.scheme_name_list.copy()
        # 这里，
        random.shuffle(a)
        scheme_name_list.extend(a)

    # 依次调整所有变量（方案名称以及信道间隔等），形成实验方案
    for spacing in spacing_list:
        for scheme_name in scheme_name_list:
            classical_channel_array = classical_signal_array(cfg)
            s = {'name': scheme_name, 'list_frequency': classical_channel_array, 'spacing': spacing / 1e9}
            s['title'] = "Scheme_name: {}, Spacing:{} GHz".format(s['name'], s['spacing'])
            scheme_list.append(s)
    return scheme_list

def main_control(debug_mode:bool = True, num_c:int = 3):
    cfg = config.get_config()
    action_time = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    scheme_list = enum_exp_scheme(cfg)

    # 初始化wss对象
    wss = init_wss(cfg)
    ase = init_ase(cfg)



    # 数据保存
    wb = Workbook()
    sheet = wb.active
    sheet.title = '经典-量子共纤传输实验结果'

    # 开始进行信道分配方案，注意要打时间戳
    # 开始逐个执行预设方案
    for i in range(len(list_scheme)):
        s = list_scheme[i]
        scheme_name = s['name']
        classical_channel_array = s['list_frequency']
        spacing = s['spacing']
        if debug_mode:
            print('scheme_name: ', scheme_name)
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
        if debug_mode:
            print('调试信息：QKD系统恢复中')
        time.sleep(BUFFER_TIME)
        if debug_mode:
            print('调试信息：QKD系统恢复完成')

        if debug_mode:
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
        if debug_mode:
            print(['结束 ', s['title']])

        time.sleep(BUFFER_TIME)

        # 保存实验结果
        dir_name = 'data/' + str(spacing_list / 1e9) + 'GHz ' + str(num_c) + 'channel ' + str(
            ACTUAL_POWER) + 'dBm ' + action_time
        dir_path = Path(__file__).resolve().parent / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        # 保存OSA图像
        device.save_current_image(dir_path, i + 1)

        # 从QKD设备获取SKR数据
        log_file_path = Path(__file__).resolve().parent / 'log'
        log_file_name = 'qkd.alice-bob.log.0'
        scheme_time_list = [(begin_time, end_time)]
        qkd = device.QKD(update_log=True, time_list=scheme_time_list, log_file_path=log_file_path,
                         log_file_name=log_file_name, data_file_path=dir_path)
        mean_skr = qkd.get_skr_list(i + 1)[0]
        qkd.get_key_and_qber(i + 1)

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
    return

if __name__ == "__main__":
    main_control(True)
