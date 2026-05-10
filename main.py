import random
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
from device.tunable_laser_source import TunableLaserSource
from device.SFP_source import TunableSFPController, C_LIGHT
from tools.count_down import countdown

# ————————全局常数区————————
# 光纤长度（单位：m）
DISTANCE = 10e3
# 激光源发射功率（单位：dBm）
MAX_POWER = 13
# 经典信号实际发射功率（单位：dBm）
ACTUAL_POWER = 13
# QKD开机采集时间/关闭经典信道缓冲时间（单位：秒）
INV_TIME = 3600

def classical_signal_array(cfg: Config):
    return []

def init_wss(cfg:Config):
    # 定义wss初始端口衰减（全部为0）
    list_att_initial = np.array(cfg.device.wss1.list_att_initial)
    # 定义wss端口设置
    wss_port = cfg.device.wss_port
    # 定义wss对象
    wss = WavelengthSelectiveSwitch(com_power=cfg.device.wss1.com_power, com_control=cfg.device.wss1.com_control, list_att=list_att_initial)
    # wss设备开机
    response = wss.wsspower(set='on')
    # 如果开机异常，打印返回信息
    if 'OK' not in response:
        print(response)

    # 本实验中总共用到4个wss
    # 1号设备的隔离度较好（25 dB）com口1用于用于二级（涉及量子信道）MUX，com口2用于二级（涉及量子信道）DEMUX
    # 2号设备的隔离度较差（20 dB）com口1用于用于一级（只涉及经典信道）MUX，com口2用于用于一级（只涉及经典信道）DEMUX
    for device_id in range(1, 3):
        for com_id in range(1, 3):
            # 初始化时阻塞所有端口
            wss.wss_spa(num_device=device_id, begin_slot=1, end_slot=772, com_port=com_id,  switch_port=99, att=0)

    # 将量子信道所在的1号设备2号端口对应量子信道和同步信道频率衰减修改为0
    for com_id in range(1, 3):
        wss.wss_spa_bandwidth(num_device=1, frequency=cfg.experiment.fq, bandwidth=20e9, com_port=com_id,
                              switch_port=wss_port['quantum'], att=0)
        wss.wss_spa_bandwidth(num_device=1, frequency=cfg.experiment.fsyn, bandwidth=100e9, com_port=com_id,
                              switch_port=wss_port['quantum'], att=0)

    return wss

def init_ase(cfg:Config):
    ase_settings = cfg.device.ase
    ase = ASESource(port=ase_settings.port, baud=ase_settings.baud)
    ase.set_target_power_mw(power_mw=ase_settings.target_power_mw)
    return ase

def init_tls(cfg: Config):
    """初始化 TLS 设备对象"""
    tls_settings = cfg.device.tls
    return TunableLaserSource(mtp_ip=tls_settings.mtp_ip, iqs_ip=tls_settings.iqs_ip)


def init_sfp(cfg: Config):
    """初始化 SFP 可调谐模块"""
    sfp_settings = cfg.device.sfp
    return TunableSFPController(
        transport=sfp_settings.transport,
        serial_port=sfp_settings.serial_port,
        baudrate=sfp_settings.baudrate,
    )


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
        # 这里需要调整方案前后的执行顺序，也可能会对QKD产生影响，需要通过随机化排除这一点
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

def exe_exp_scheme(cfg: Config, scheme_list: list, wss: WavelengthSelectiveSwitch, ase: ASESource,
                    debug_mode: bool = False, tls: TunableLaserSource = None,
                    sfp: TunableSFPController = None):
    """
    执行实验方案。

    遍历所有实验方案，依次调用 exe_exp_single_scheme 执行单个方案，
    并将结果汇总保存至 Excel 文件。

    Args:
        cfg: 实验配置对象
        scheme_list: 由 enum_exp_scheme 生成的实验方案列表
        wss: 已初始化的 WSS 设备对象
        ase: 已初始化的 ASE 设备对象
        debug_mode: 是否输出调试信息，默认 False
        tls: TLS 设备对象（TLS 模式时需要）
        sfp: SFP 设备对象（SFP 模式时需要）
    """
    num_c = cfg.experiment.num_c
    actual_power = cfg.experiment.actual_power

    wb = Workbook()
    sheet = wb.active
    sheet.title = '经典-量子共纤传输实验结果'

    dir_name = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dir_path = Path(__file__).resolve().parent / dir_name
    dir_path.mkdir(parents=True, exist_ok=True)

    for i in range(len(scheme_list)):
        exe_exp_single_scheme(cfg, scheme_list[i], i, wss, dir_path, sheet, wb, debug_mode,
                              tls=tls, sfp=sfp, ase=ase)

    print('——所有数据保存完成——')
    return


def exe_exp_single_scheme(cfg: Config, s: dict, i: int, wss: WavelengthSelectiveSwitch,
                           dir_path: Path, sheet, wb: Workbook, debug_mode: bool = False,
                           tls: TunableLaserSource = None, sfp: TunableSFPController = None,
                           ase: ASESource = None):
    """
    执行单个实验方案。
    配置 WSS 经典信道波长分配，采集 QKD 安全密钥率数据和 OSA 频谱图像，
    并将结果保存至对应的子文件夹和汇总 Excel。

    Args:
        cfg: 实验配置对象
        s: 单个实验方案字典，包含 name, list_frequency, spacing, title
        i: 方案序号（从0开始）
        wss: 已初始化的 WSS 设备对象
        dir_path: 实验数据保存根目录
        sheet: Excel 汇总工作表
        wb: Excel 工作簿
        debug_mode: 是否输出调试信息
        tls: TLS 设备对象（TLS 模式时需要）
        sfp: SFP 设备对象（SFP 模式时需要）
        ase: ASE 设备对象（SFP/OTN 模式时需要）
    """
    num_c = cfg.experiment.num_c
    wss_port = cfg.device.wss_port
    max_power = cfg.experiment.max_power
    actual_power = cfg.experiment.actual_power

    scheme_name = s['name']
    classical_channel_array = s['list_frequency']
    spacing = s['spacing']

    if debug_mode:
        print('scheme_name: ', scheme_name)

    # 初始化wss对象，包括阻塞所有端口，设置量子信道衰减为0
    init_wss(cfg)

    # 设置经典信道
    if scheme_name != 'None':
        light_source_type = cfg.experiment.light_source.type
        if light_source_type == 'TLS':
            bandwidth = cfg.experiment.light_source.tls_bandwidth
        elif light_source_type == 'SFP':
            bandwidth = cfg.experiment.light_source.sfp_bandwidth
        elif light_source_type == 'OTN':
            bandwidth = cfg.experiment.light_source.otn_bandwidth
        else:
            raise ValueError(f"不支持的光源类型: {light_source_type}")

        num_channels = len(classical_channel_array)
        fq = cfg.experiment.fq

        # 按距离量子信道远近排序，距离相同时优先低频
        sorted_indices = sorted(
            range(num_channels),
            key=lambda i: (abs(classical_channel_array[i] - fq), classical_channel_array[i])
        )

        # 真实光源数量上限
        if light_source_type == 'TLS':
            max_count = cfg.experiment.light_source.tls_max_count
        elif light_source_type == 'SFP':
            max_count = cfg.experiment.light_source.sfp_max_count
        elif light_source_type == 'OTN':
            max_count = cfg.experiment.light_source.otn_max_count
        else:
            raise ValueError(f"不支持的光源类型: {light_source_type}")

        real_indices = set(sorted_indices[:max_count])  # 前 max_count 个用真实光源

        # 对经典侧的量子频率阻塞以增加隔离度（全局操作，移至循环外）
        wss.wss_spa_bandwidth(num_device=2, frequency=cfg.experiment.fq, bandwidth=20e9, com_port=1,
                              switch_port=99, att=0)
        wss.wss_spa_bandwidth(num_device=2, frequency=cfg.experiment.fsyn, bandwidth=100e9, com_port=1,
                              switch_port=99, att=0)

        # —— 真实光源配置 ——
        for j in range(max_count):
            idx = sorted_indices[j]
            fc = classical_channel_array[idx]

            # 打通经典信道（暂时设定为0衰减，通过电光衰来调控）
            for com_id in range(1, 3):
                wss.wss_spa_bandwidth(num_device=2, frequency=fc, bandwidth=bandwidth, com_port=com_id,
                                      switch_port=wss_port['real_source'], att=0)
                wss.wss_spa_bandwidth(num_device=1, frequency=fc, bandwidth=bandwidth, com_port=com_id,
                                      switch_port=wss_port['wdm_classical'], att=0)

            # —— 真实光源控制 ——
            if light_source_type == 'TLS':
                tls.setFrequencyAndPower(j + 1, fc, actual_power)
                tls.set_on_and_off(j + 1, 'ON')
            elif light_source_type == 'SFP':
                wavelength_nm = (C_LIGHT / fc) * 1e9
                sfp.set_wavelength_nm(wavelength_nm)
                sfp.enable_tx()
            elif light_source_type == 'OTN':
                user_input = input(
                    f"OTN设备需手动设置，请将信道频率设为 {fc / 1e12:.4f} THz 后"
                    f"输入 y 继续，输入 n 终止进程: "
                )
                if user_input.lower() != 'y':
                    print("用户终止进程")
                    return

        # —— 超出真实光源数量的信道全部用 ASE 假光 ——
        if num_channels > max_count:
            ase.set_target_power_mw(cfg.device.ase.target_power_mw)

        # —— ASE 假光 WSS 配置 ——
        for j in range(max_count, num_channels):
            idx = sorted_indices[j]
            fc = classical_channel_array[idx]
            wss.wss_spa_bandwidth(num_device=2, frequency=fc, bandwidth=bandwidth, com_port=1,
                                   switch_port=wss_port['ase_source'], att=0)

    # 给QKD系统恢复时间
    inv_time = cfg.experiment.inv_time
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

    # 为当前方案创建子文件夹并保存OSA频谱数据
    scheme_folder = f"{i + 1}_{scheme_name}_{spacing}GHz_{actual_power}dBm"
    scheme_dir = dir_path / scheme_folder
    scheme_dir.mkdir(parents=True, exist_ok=True)
    start_freq = cfg.experiment.fq - 1e12
    end_freq = cfg.experiment.fq + 1e12
    scheme_basename = f"scheme_{i + 1}_{scheme_name}_{spacing}GHz_{actual_power}dBm"
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

    # 保存当前方案数据到汇总表
    sheet.append([i + 1, s['title']])
    sheet.append(['', 'begin_time', s['begin_time']])
    sheet.append(['', 'end_time', s['end_time']])
    sheet.append(['', 'power(dBm)', actual_power])
    sheet.append(['', 'distance(km)', cfg.experiment.distance / 1000])
    sheet.append(['', 'spacing(GHz)', s['spacing']])
    sheet.append(['', 'secure key rate(bps)', mean_skr])
    sheet.append(['', 'list_frequency'] + s['list_frequency'].tolist())
    wb.save(dir_path / 'data.xlsx')

def main_control(debug_mode: bool = False):
    cfg = config.get_config()
    scheme_list = enum_exp_scheme(cfg)
    # 初始化wss对象
    wss = init_wss(cfg)
    # 初始化ase对象
    ase = init_ase(cfg)

    # 根据光源类型按需初始化
    light_source_type = cfg.experiment.light_source.type
    tls = init_tls(cfg) if light_source_type == 'TLS' else None
    sfp = init_sfp(cfg) if light_source_type == 'SFP' else None

    # 执行实验方案
    exe_exp_scheme(cfg, scheme_list, wss, ase, debug_mode, tls=tls, sfp=sfp)
    return

if __name__ == "__main__":
    main_control(True)
