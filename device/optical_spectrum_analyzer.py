import socket
import re
import pandas as pd
import time
from pathlib import Path


def val(string):
    match = re.match(r"[-+]?\d*\.?\d+", string)
    return float(match.group()) if match else 0


class OpticalSpectrumAnalyzer:
    def __init__(self, osa_ip, osa_port, Timeout = 5, Terminator = '\r\n', InputBufferSize=1024):
        self._client = None
        self.serverip = osa_ip
        self.port = osa_port
        self.timeout = Timeout
        self.terminator = Terminator
        self.buffersize = InputBufferSize

    def tcp_connect(self):
        if self._client is not None:
            raise ConnectionError("ERROR 连接 已经存在，请先关闭!!!")
        self._client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._client.settimeout(self.timeout)
        try:
            # 连接到服务器(需要指定IP地址和端口)
            self._client.connect((self.serverip, self.port))
            # print(f'已连接到 {self.serverip} --port:{self.port}')
            self.login(self._client)
            # print('---------- OSA控制和查询阶段 ----------')
        except Exception as e:
            self.disconnect()
            raise ConnectionError(f'ERROR 连接or登录 失败: {e}')

    def disconnect(self):
        if self._client:
            self._client.close()
            self._client = None
            # print('连接 已关闭')

    def send_command(self, command: str, expect_response: bool = True, timeout: float | None = None) -> str:
        """
        发送 SCPI 命令。支持对单条命令临时指定 timeout（秒）。
        """
        if not command.endswith("\n"):
            command += "\n"

        old_timeout = None
        if timeout is not None:
            old_timeout = self._client.gettimeout()
            self._client.settimeout(timeout)

        try:
            self._client.sendall(command.encode())

            if not expect_response:
                return ""

            # 典型 SCPI 响应都很短，但仍建议读到 '\n'
            chunks = []
            while True:
                data = self._client.recv(self.buffersize)
                if not data:
                    break
                chunks.append(data)
                if b"\n" in data:
                    break

            return b"".join(chunks).decode(errors="ignore").strip()

        except Exception as e:
            raise IOError(f"命令 '{command.strip()}' 发送失败: {e}") from e
        finally:
            if old_timeout is not None:
                self._client.settimeout(old_timeout)

    def _recv_until(self, predicate, chunk_size: int = 4096, max_bytes: int = 2_000_000) -> bytes:
        """Receive bytes until predicate(buffer) is True or max_bytes exceeded."""
        buf = bytearray()
        while True:
            if len(buf) > max_bytes:
                raise IOError(f"接收数据超过上限 {max_bytes} bytes，可能未按预期返回二进制块。")
            chunk = self._client.recv(chunk_size)
            if not chunk:
                raise IOError("连接已关闭，未收到完整数据。")
            buf.extend(chunk)
            if predicate(buf):
                return bytes(buf)

    def _recv_exact(self, n: int, chunk_size: int = 4096) -> bytes:
        """Receive exactly n bytes."""
        buf = bytearray()
        while len(buf) < n:
            chunk = self._client.recv(min(chunk_size, n - len(buf)))
            if not chunk:
                raise IOError("连接已关闭，未收到完整数据。")
            buf.extend(chunk)
        return bytes(buf)

    def query_binary_block(self, command: str, chunk_size: int = 4096) -> bytes:
        """发送查询命令并按 IEEE 488.2 definite-length block (#<N><len><data>) 接收二进制数据。"""
        if self._client is None:
            raise ConnectionError("ERROR 未连接到设备，请先连接!!!")

        # 发送查询命令
        self._client.sendall((command + self.terminator).encode())

        # 先拿到 '#' 和长度字段
        header = self._recv_until(
            lambda b: len(b) >= 2 and b[0:1] == b'#' and 48 <= b[1] <= 57,
            chunk_size=chunk_size
        )

        if header[0:1] != b'#':
            raise IOError(f"二进制块头错误，期望 '#', 实际为: {header[:16]!r}")

        n_digits = header[1] - ord('0')
        if n_digits <= 0:
            raise IOError(f"二进制块长度位数非法: {n_digits}")

        # 确保已收齐长度字符串
        need = 2 + n_digits
        if len(header) < need:
            header += self._recv_exact(need - len(header), chunk_size=chunk_size)

        size_str = header[2:2 + n_digits].decode(errors='strict')
        data_len = int(size_str)

        # header 后面可能已经带了一部分数据
        data_start = 2 + n_digits
        already = len(header) - data_start
        data = bytearray()
        if already > 0:
            data.extend(header[data_start:])

        if already < data_len:
            data.extend(self._recv_exact(data_len - already, chunk_size=chunk_size))

        # 设备一般会在块后附加 terminator（LF/EOI），这里不强制读取/剥离
        return bytes(data)

    def save_current_image(self,
                           save_dir=None,
                           basename=None,
                           color: bool = True,
                           fmt: str = "bmp",
                           storage: str = "int") -> str:
        """保存当前屏幕图像到本机，并返回保存路径。

        依据用户手册示例：先用 :MMEM:STOR:GRAP 保存图像到仪器内存，再用 :MMEM:DATA? 读回文件数据。"""
        if basename is None:
            basename = time.strftime("osa_screen_%Y%m%d_%H%M%S")

        ext = fmt.lower().lstrip('.')
        storage = storage.lower()

        # 1) 在仪器侧生成文件（不带扩展名）
        color_arg = "color" if color else "mono"
        self.send_command(f':MMEM:STOR:GRAP {color_arg},{ext},"{basename}",{storage}', expect_response=False)

        # 2) 读回文件二进制（带扩展名）
        remote_name = f"{basename}.{ext}"
        data = self.query_binary_block(f':MMEM:DATA? "{remote_name}",{storage}')

        # 3) 写入本机 data/ 目录
        if save_dir is None:
            save_dir_path = (Path(__file__).resolve().parent / "data")
        else:
            save_dir_path = Path(save_dir).expanduser().resolve()

        save_dir_path.mkdir(parents=True, exist_ok=True)
        local_path = save_dir_path / remote_name
        local_path.write_bytes(data)
        return str(local_path)

    def auto_sweep(self, max_wait_s: float = 60.0, poll_interval_s: float = 0.2):
        """
        AUTO sweep: 设置 AUTO 模式 + 发起 sweep + 轮询等待结束
        """
        self.send_command(":INITiate:SMODe AUTO", expect_response=False)
        self.send_command("*CLS", expect_response=False)
        self.send_command(":INITiate", expect_response=False)

        t0 = time.time()
        while True:
            # 轮询事件寄存器（返回很快，不会长时间阻塞）
            resp = self.send_command(":STAT:OPER:EVEN?", expect_response=True, timeout=2.0)
            try:
                if int(float(resp)) != 0:
                    break
            except Exception:
                # 偶发非数字，忽略继续
                pass

            if time.time() - t0 > max_wait_s:
                # 超时后做两件事：读一下错误队列，便于定位；然后兜底改单次扫
                err = self.send_command(":SYST:ERR?", expect_response=True, timeout=2.0)
                raise TimeoutError(f"AUTO sweep 等待超过 {max_wait_s}s，最后错误队列: {err}")

            time.sleep(poll_interval_s)

    def wdm_analyze(self, dmask_db: float = -999):
        """
        执行 WDM analysis，并让仪器切换到 WDM 分析结果显示。
        dmask_db: 通道检测门限；-999 表示关闭 mask（手册定义）。
        """
        # 1) 选择 WDM 分析类别
        self.send_command(":CALCulate:CATegory WDM", expect_response=False)

        # 2) 可选：设置 WDM 通道 mask 阈值（低于该阈值的峰不识别为信道）
        # -999 表示 Mask OFF
        self.send_command(f":CALCulate:PARameter:WDM:DMASk {dmask_db}DB", expect_response=False)

        # 3) 执行分析
        self.send_command(":CALCulate", expect_response=False)
        return

    def login(self, client):
        response = self.send_command('OPEN "anonymous"',True)
        # print(f'设备响应 open anonymous: {response}')
        response = self.send_command(' ',True)
        # print(f'设备响应 密码: {response}')
        response = self.send_command('*STB?',True)
        # print(f'设备响应 STB: {response}')

    # 支持with语句
    def __enter__(self):
        self.tcp_connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

def save_current_image(path_dir='./../data', name_id=1):
    with OpticalSpectrumAnalyzer(osa_ip="192.168.1.113", osa_port=10001) as osa:
        # osa.auto_sweep(max_wait_s=120)
        path = osa.save_current_image(save_dir=path_dir, basename="my_capture_" + str(name_id))
        # osa.wdm_analyze(dmask_db=-999)
        # path = osa.save_current_image(save_dir=path_dir, basename="my_capture_wdm_" + str(name_id))
        print("Saved to:", path)
    return

def OSA_read(a: float, b: float):
    info_list = []
    with OpticalSpectrumAnalyzer('192.168.1.113', 10001) as osa1:
        cmd_list = ["*IDN?", r":SENSe:WAV:STARt " + str(a) + r"HZ;STOP " + str(b) + r"HZ",
                    r":sens:sens mid", r":sens:sweep:points:auto on",
                    r":init:smode 1", r"*CLS", r":init"]

        for cmd in cmd_list:
            if '?' in cmd:
                # print(f'--查询: {cmd}')
                osa1.send_command(cmd, True)
                # print(f'返回值: {response}')
            else:
                # print(f'--命令: {cmd}')
                osa1.send_command(cmd, expect_response=False)

        c = r":stat:oper:even?"
        while True:
            response = osa1.send_command(c, True)
            if val(response) != 0:
                break

        cmd_list = [r":calc:category swth", r":CALCulate:CATegory OSNR", r":calc"]
        # r":calc:data:nch?", r":calc:data?",  r":calc:data:cwav?",

        for cmd in cmd_list:
            osa1.send_command(cmd, expect_response=False)

        cmd_list = [r":calc:data:cpow?"]
        # r":calc:data:csnr?",
        # snr_list = [0 for i in range(n)]
        # noise_list = [0 for i in range(n)]
        n = 0
        for cmd in cmd_list:
            response = osa1.send_command(cmd, True)
            # if 'snr' in cmd:
            #     snr_list_temp = response.split(',')
            #     print(len(snr_list_temp))
            #     for k in range(n):
            #         # 信噪比单位dB
            #         snr_list[k] = float(snr_list_temp[k])
            if 'power_c' in cmd:
                pow_list_temp = response.split(',')
                n = len(pow_list_temp)
                pow_list = [0 for i in range(n)]
                for k in range(n):
                    # 经典信号功率 dBm
                    pow_list[k] = float(pow_list_temp[k])
                    # noise_list[k] = float(pow_list_temp[k]) - float(snr_list_temp[k])

        for k in range(n):
            info_list[k]['power_c'] = pow_list[k]
            # info_list[k]['snr'] = snr_list[k]
            # info_list[k]['noise'] = pow_list[k] - snr_list[k]
    max_pow = -1000
    id = -1
    for k in range(n):
        if info_list[k]['power_c'] > max_pow:
            max_pow = info_list[k]['power_c']
            id = k
    if id == -1:
        return None
    else:
        return info_list[id]


if __name__ == '__main__':
    save_current_image()
    # info = OSA_read(192.7e12-50e9, 192.7e12+50e9)
    # print(info)