"""
配置加载模块
"""
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import List


@dataclass
class WSSConfig:
    com_power: str
    com_control: str
    list_att_initial: List[List[float]]


@dataclass
class TLSConfig:
    mtp_ip: str
    iqs_ip: str


@dataclass
class OSAConfig:
    ip: str
    port: int


@dataclass
class QKDConfig:
    ip: str
    port: int
    username: str
    password: str
    log_file_path: str
    log_file_name: str


@dataclass
class DeviceConfig:
    wss: WSSConfig
    tls: TLSConfig
    osa: OSAConfig
    qkd: QKDConfig


@dataclass
class ExperimentConfig:
    distance: float
    max_power: float
    actual_power: float
    buffer_time: int
    inv_time: int
    wait_time: int
    fq: float
    fsyn: float
    spacing: float
    num_c: int
    raman_file: str


@dataclass
class Config:
    device: DeviceConfig
    experiment: ExperimentConfig


def load(config_path: str | None = None) -> Config:
    """加载配置文件"""
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "config.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    device_cfg = raw['device']
    experiment_cfg = raw['experiment']

    return Config(
        device=DeviceConfig(
            wss=WSSConfig(
                com_power=device_cfg['wss']['com_power'],
                com_control=device_cfg['wss']['com_control'],
                list_att_initial=device_cfg['wss']['list_att_initial'],
            ),
            tls=TLSConfig(
                mtp_ip=device_cfg['tls']['mtp_ip'],
                iqs_ip=device_cfg['tls']['iqs_ip'],
            ),
            osa=OSAConfig(
                ip=device_cfg['osa']['ip'],
                port=device_cfg['osa']['port'],
            ),
            qkd=QKDConfig(
                ip=device_cfg['qkd']['ip'],
                port=device_cfg['qkd']['port'],
                username=device_cfg['qkd']['username'],
                password=device_cfg['qkd']['password'],
                log_file_path=device_cfg['qkd']['log_file_path'],
                log_file_name=device_cfg['qkd']['log_file_name'],
            ),
        ),
        experiment=ExperimentConfig(
            distance=experiment_cfg['distance'],
            max_power=experiment_cfg['max_power'],
            actual_power=experiment_cfg['actual_power'],
            buffer_time=experiment_cfg['buffer_time'],
            inv_time=experiment_cfg['inv_time'],
            wait_time=experiment_cfg['wait_time'],
            fq=experiment_cfg['fq'],
            fsyn=experiment_cfg['fsyn'],
            spacing=experiment_cfg['spacing'],
            num_c=experiment_cfg['num_c'],
            raman_file=experiment_cfg['raman_file'],
        ),
    )


# 全局配置实例
_default_config: Config | None = None


def get_config() -> Config:
    """获取全局配置实例（延迟加载）"""
    global _default_config
    if _default_config is None:
        _default_config = load()
    return _default_config
