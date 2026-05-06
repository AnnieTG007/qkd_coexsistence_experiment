import random
import xlrd
import numpy as np
import datetime
import time
from openpyxl import Workbook
from pathlib import Path
import config
from config import Config
from device.wavelength_selective_switch import WavelengthSelectiveSwitch
from device.ASE_source import ASESource
from device.optical_spectrum_analyzer import OpticalSpectrumAnalyzer
from device.QKD_log_read import QKDLogRead
from tools.count_down import countdown
from simulation import BB84_SKR_infinite as SKR_simulation

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
    wss = WavelengthSelectiveSwitch(com_power=cfg.device.wss1.com_power, com_control=cfg.device.wss1.com_control, list_att=list_att_initial)
    # wss设备开机
    response = wss.wsspower(set='on')
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
    ase = ASESource(port=ase_settings.port, baud=ase_settings.baud)
    ase.set_target_power_mw(power_mw=ase_settings.target_power_mw)
    return ase

def enum_exp_scheme(cfg: Config):
    """
    枚举实验方案。

    根据配置中的信道名称列表、信道间隔和重复次数，
    随机打乱方案顺序后生成所有待执行的实验方案组合。

    Args:
        cfg: 实验配置对象

    Returns:
        list[dict]: 实验方案列表，每个方案包含 name, list_frequency, spacing, title
    """
    scheme_list = []
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

def exe_exp_scheme(cfg: Config, scheme_list: list, wss: WavelengthSelectiveSwitch, ase: ASESource, debug_mode: bool = False):
    """
    执行实验方案。

    遍历所有实验方案，依次配置 WSS 进行经典信道波长分配，
    采集 QKD 安全密钥率数据和 OSA 频谱图像，并将结果保存至 Excel 文件。

    Args:
        cfg: 实验配置对象
        scheme_list: 由 enum_exp_scheme 生成的实验方案列表
        wss: 已初始化的 WSS 设备对象
        ase: 已初始化的 ASE 设备对象
        debug_mode: 是否输出调试信息，默认 False
    """
    num_c = cfg.experiment.num_c
    # WSS com_port=1 时可用偶数端口，端口2已用于量子/同步信道
    wss_port = np.array([4, 6, 8, 10, 12, 14, 16, 18])[:num_c]
    max_power = cfg.experiment.max_power
    actual_power = cfg.experiment.actual_power
    inv_time = cfg.experiment.inv_time
    spacing_list = np.array(cfg.experiment.spacing_list)

    # 数据保存
    wb = Workbook()
    sheet = wb.active
    sheet.title = '经典-量子共纤传输实验结果'

    # 创建实验根目录（按实验参数命名）
    dir_name = 'data/' + str(spacing_list / 1e9) + 'GHz ' + str(num_c) + 'channel ' + str(
        actual_power) + 'dBm'
    dir_path = Path(__file__).resolve().parent / dir_name
    dir_path.mkdir(parents=True, exist_ok=True)
    # 开始逐个执行预设方案
    for i in range(len(scheme_list)):
        s = scheme_list[i]
        scheme_name = s['name']
        classical_channel_array = s['list_frequency']
        spacing = s['spacing']
        if debug_mode:
            print('scheme_name: ', scheme_name)
            if scheme_name != 'None':
                print(classical_channel_array)
                print('SKR, QBER: ', SKR_simulation(distance=cfg.experiment.distance, noise_after_spd=0))

        # 执行每个方案前，先阻塞所有的端口，相当于让QKD系统空跑
        wss.wss_spa(num_device=1, begin_slot=1, end_slot=772, com_port=1, switch_port=99, att=0)

        if scheme_name != 'None':
            # 设置经典信号波长，设置WSS
            for j in range(len(classical_channel_array)):
                # 获取经典信号频率
                f = classical_channel_array[j]
                # WSS设置
                wss.wss_spa_bandwidth(num_device=1, frequency=f, bandwidth=20e9, com_port=1, switch_port=wss_port[j], att=max(0, max_power - actual_power))

        # 给QKD系统恢复时间
        if debug_mode:
            print('调试信息：QKD系统恢复中')
        time.sleep(inv_time)
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
        countdown(cd_time=inv_time)

        # 记录方案结束的时间戳
        end_time = datetime.datetime.now()
        s['end_time'] = end_time.strftime('%Y-%m-%d %H:%M:%S')
        if debug_mode:
            print(['结束 ', s['title']])

        time.sleep(inv_time)

        # 保存实验结果
        # 为当前方案创建子文件夹（编号+方案名称+信道间隔）
        scheme_folder = f"{i + 1}_{scheme_name}_{spacing}GHz"
        scheme_dir = dir_path / scheme_folder
        scheme_dir.mkdir(parents=True, exist_ok=True)
        # 保存OSA频谱数据及图像（频率范围：量子信道频率 ± 1THz）
        start_freq = cfg.experiment.fq - 1e12
        end_freq = cfg.experiment.fq + 1e12
        scheme_basename = f"scheme_{i + 1}_{scheme_name}_{spacing}GHz"
        with OpticalSpectrumAnalyzer(osa_ip=cfg.device.osa.ip, osa_port=cfg.device.osa.port) as osa:
            osa.save_spectrum_data(start_freq=start_freq, end_freq=end_freq,
                                   save_dir=str(scheme_dir), basename=scheme_basename)

        # 从QKD设备获取SKR数据
        log_file_path = Path(__file__).resolve().parent / 'log'
        log_file_name = 'qkd.alice-bob.log.0'
        scheme_time_list = [(begin_time, end_time)]
        qkd = QKDLogRead(update_log=True, time_list=scheme_time_list, log_file_path=log_file_path,
                         log_file_name=log_file_name, data_file_path=scheme_dir)
        mean_skr = qkd.get_skr_list(id=i + 1)[0]
        qkd.get_key_and_qber(id=i + 1)

        # 保存当前方案数据
        sheet.append([i + 1, s['title']])
        sheet.append(['', 'begin_time', s['begin_time']])
        sheet.append(['', 'end_time', s['end_time']])
        sheet.append(['', 'power(dBm)', actual_power])
        sheet.append(['', 'distance(km)', cfg.experiment.distance / 1000])
        sheet.append(['', 'spacing(GHz)', s['spacing']])
        sheet.append(['', 'secure key rate(bps)', mean_skr])
        sheet.append(['', 'list_frequency'] + s['list_frequency'].tolist())
        wb.save(dir_path / 'data.xlsx')

    print('——所有数据保存完成——')
    return

def main_control(debug_mode: bool = False):
    cfg = config.get_config()
    scheme_list = enum_exp_scheme(cfg)
    # 初始化wss对象
    wss = init_wss(cfg)
    # 初始化ase对象
    ase = init_ase(cfg)
    # 执行实验方案
    exe_exp_scheme(cfg, scheme_list, wss, ase, debug_mode)
    return

if __name__ == "__main__":
    main_control(True)
