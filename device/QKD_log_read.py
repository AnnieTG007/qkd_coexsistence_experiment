import paramiko
import re
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path
import pandas as pd

class QKDLogRead:
    def __init__(self, update_log=True, time_list=[],
                 remote_file_path='/home/qkd/log/', remote_file_name='qkd.20t-21r.log.0',
                 log_file_path = Path(__file__).resolve().parent.parent / 'log',
                 log_file_name = 'qkd.alice-bob.log.0',
                 data_file_path = Path(__file__).resolve().parent.parent / 'data'):
        # 是否通过远程连接更新
        self.update_log = update_log
        # ————方案的开始时间和结束时间列表，形式为[(开始1,结束1),(开始2,结束2)……]————
        self.time_list = time_list
        # ————与SFTP远程连接相关，定义IP地址和登录方式，并定义文件位置和名称————
        self.remote_file_path = remote_file_path
        self.remote_file_name = remote_file_name
        self.log_file_path = log_file_path
        self.log_file_name = log_file_name
        self.data_file_path = data_file_path
        self.ip = '192.168.1.20'
        self.port = 56100
        self.user_name = 'qkd'
        self.pwd = 'qasky1234'

    def SFTP_Connection(self):
        # 创建 SSHClient 对象
        ssh_client = paramiko.SSHClient()
        # 添加远程服务器的主机密钥（如果首次连接，需要添加）
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # 连接到远程服务器
        ssh_client.connect(hostname=self.ip, port=self.port, username=self.user_name, password=self.pwd)
        # 创建 SFTP 客户端
        sftp_client = ssh_client.open_sftp()
        # 下载文件
        remote_file = self.remote_file_path + self.remote_file_name
        local_file = self.log_file_path / self.log_file_name
        sftp_client.get(remote_file, str(local_file))
        # 关闭SFTP连接和SSH连接
        sftp_client.close()
        ssh_client.close()
        return

    def get_skr_point_num(self):
        num_list = [0] * len(self.time_list)
        log_file = self.log_file_path / self.log_file_name
        with log_file.open('r', encoding='utf-8') as file:
            for line in file:
                # 仅筛选后处理之后的安全密钥速率
                if 'secure key rate' not in line or 'postprocess' not in line:
                    continue
                # 读取日志的时间戳
                time_slot = line[0:6] + "20" + line[6:17]
                now_time = datetime.strptime(time_slot, r'%m/%d/%Y %H:%M:%S')
                for i in range(len(self.time_list)):
                    start, end = self.time_list[i]
                    if start <= now_time <= end:
                        num_list[i] = num_list[i] + 1
        return num_list

    def get_key_and_qber(self, id):
        info_list = [[] for _ in range(len(self.time_list))]
        log_file = self.log_file_path / self.log_file_name
        with log_file.open('r', encoding='utf-8') as file:
            for line in file:
                # 仅筛选后处理之后的安全密钥速率
                if 'net key' not in line or 'qber' not in line:
                    continue
                # 读取日志的时间戳
                time_slot = line[0:6] + "20" + line[6:17]
                now_time = datetime.strptime(time_slot, r'%m/%d/%Y %H:%M:%S')
                for i in range(len(self.time_list)):
                    start, end = self.time_list[i]
                    if start <= now_time <= end:
                        inv = (now_time - start).total_seconds()
                        # 筛后密钥
                        pattern = r'net key \d+'
                        key = int(re.findall(pattern, line)[0][8:])
                        pattern = r'qber \d+\.\d+'
                        qber = float(re.findall(pattern, line)[0][5:])
                        info_list[i].append({'time_slot': time_slot, 'inv': inv, 'key': key, 'qber': qber})

        excel_path = self.data_file_path / (str(id) + "_QKD_net_key_info.xlsx")

        has_sheet = False  # 是否至少写入过一个 sheet
        with pd.ExcelWriter(excel_path, engine="openpyxl", mode="w") as writer:
            for i in range(len(self.time_list)):
                if len(info_list[i]) == 0:
                    continue

                df = pd.DataFrame(info_list[i])
                df = df[["time_slot", "inv", "key", "qber"]]

                sheet_name = f"scheme_{i + 1}"
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                has_sheet = True

            # —— 兜底：没有任何数据时，也要写一个 sheet ——
            if not has_sheet:
                df_empty = pd.DataFrame(
                    columns=["time_slot", "inv", "key", "qber"]
                )
                df_empty.to_excel(writer, sheet_name="empty", index=False)
        return

    def get_skr_list(self, id):
        if self.update_log:
            # 更新日志
            self.SFTP_Connection()

        info_list = [[] for _ in range(len(self.time_list))]
        skr_list = [0] * len(self.time_list)
        log_file = self.log_file_path / self.log_file_name
        with log_file.open('r', encoding='utf-8') as file:
            for line in file:
                # 仅筛选后处理之后的安全密钥速率
                if 'secure key rate' not in line or 'postprocess' not in line:
                    continue
                # 读取日志的时间戳
                time_slot = line[0:6] + "20" + line[6:17]
                now_time = datetime.strptime(time_slot, r'%m/%d/%Y %H:%M:%S')
                # print(now_time)
                for i in range(len(self.time_list)):
                    start, end = self.time_list[i]
                    # print('*', start, end)
                    # 筛选在方案时间内的数据点
                    if start <= now_time <= end:
                        # SKR的持续时间
                        pattern = r'elapsed \d+\.\d+'
                        duration_time = float(re.findall(pattern, line)[0][8:])
                        # 密钥生成速率
                        pattern = r'rate \d+\.\d+'
                        skr = float(re.findall(pattern, line)[0][5:])
                        info_list[i].append({'time_slot': time_slot, 'inv': (now_time - start).total_seconds(),
                                             'dur': duration_time, 'skr': skr, 'key': skr * duration_time})
                        skr_list[i] = skr_list[i] + skr * duration_time

        excel_path = self.data_file_path / (str(id) + "_QKD_SKR_info.xlsx")
        has_sheet = False  # 是否至少写入过一个 sheet
        with pd.ExcelWriter(excel_path, engine="openpyxl", mode="w") as writer:
            for i in range(len(self.time_list)):
                if len(info_list[i]) == 0:
                    continue

                df = pd.DataFrame(info_list[i])
                df = df[["time_slot", "inv", "dur", "skr", "key"]]

                sheet_name = f"scheme_{i + 1}"
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                has_sheet = True

            # —— 兜底：没有任何数据时，也要写一个 sheet ——
            if not has_sheet:
                df_empty = pd.DataFrame(
                    columns=["time_slot", "inv", "dur", "skr", "key"]
                )
                df_empty.to_excel(writer, sheet_name="empty", index=False)

        # 保存数据
        for i in range(len(self.time_list)):
            if len(info_list[i]) > 0:
                t_list = []
                y_list = []
                start_time = self.time_list[i][0]
                all_duration_time = 0
                for j in range(len(info_list[i])):
                    inv_time = datetime.strptime(info_list[i][j]['time_slot'], r'%m/%d/%Y %H:%M:%S')
                    all_duration_time = all_duration_time + info_list[i][j]['dur']
                    t_list.append((inv_time - start_time).total_seconds())
                    y_list.append(info_list[i][j]['skr'])

                skr_list[i] = skr_list[i] / all_duration_time

                plt.figure()
                plt.title('Secret Key Rate in resource allocation')
                plt.xlabel('time(s)')
                plt.ylabel('secret key rate(bps)')
                plt.plot(t_list, y_list)
                fig_name = self.data_file_path / (str(id) + '_' + str(skr_list[i]) + '.png')
                plt.savefig(fig_name)
        return skr_list


if __name__ == "__main__":
    log_file_p = Path(__file__).resolve().parent.parent / 'log'
    log_file_n = 'qkd.20t-21r.log.5'
    # scheme_time_list = [(datetime(2025, 12, 21, 20, 35, 45),
    #               datetime(2025, 12, 21, 21, 5, 47))]
    scheme_time_list = [(datetime(2025, 12, 21, 18, 54, 53),
                    datetime(2025, 12, 21, 19, 24, 55))]
    qkd = QKDLogRead(update_log=False, time_list=scheme_time_list, log_file_path=log_file_p, log_file_name=log_file_n)
    r = qkd.get_skr_list(2)
    qkd.get_key_and_qber(2)