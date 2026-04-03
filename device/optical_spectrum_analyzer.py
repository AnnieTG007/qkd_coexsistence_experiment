import socket
import pandas as pd
import numpy as np
import time
from pathlib import Path
from scipy import constants


class OpticalSpectrumAnalyzer:
    def __init__(self, osa_ip, osa_port, Timeout=5, Terminator='\r\n', InputBufferSize=1024):
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
            self._client.connect((self.serverip, self.port))
            self.login(self._client)
        except Exception as e:
            self.disconnect()
            raise ConnectionError(f'ERROR 连接or登录 失败: {e}')

    def disconnect(self):
        if self._client:
            self._client.close()
            self._client = None

    def send_command(self, command: str, expect_response: bool = True, timeout: float | None = None) -> str:
        if not command.endswith("\n"):
            command += "\n"

        old_timeout = None
        if timeout is not None:
            old_timeout = self._client.gettimeout()
            self._client.settimeout(timeout)

        chunks = []
        try:
            self._client.sendall(command.encode())

            if not expect_response:
                return b"".join(chunks).decode(errors='ignore').strip()

            while True:
                data = self._client.recv(self.buffersize)
                if not data:
                    break
                chunks.append(data)
                # OSA 以 \r\n 结尾，收到换行符或连接关闭即表明响应完整
                if b"\n" in data:
                    break

            return b"".join(chunks).decode(errors='ignore').strip()

        except socket.timeout:
            # 超时不代表发送失败（如 *CLS 无响应），返回已收到的碎片
            return b"".join(chunks).decode(errors='ignore').strip()
        except Exception as e:
            raise IOError(f"命令 '{command.strip()}' 发送失败: {e}") from e
        finally:
            if old_timeout is not None:
                self._client.settimeout(old_timeout)

    def login(self, client):
        try:
            resp = self.send_command('OPEN "anonymous"', True, timeout=5.0)
            print(f"LOGIN resp: {resp!r}")
            if 'AUTHENTICATE' in resp:
                self._client.sendall(b"AUTHENTICATE NONE\n")
                # 认证成功后会收到 ready，先等待一会再清空
                time.sleep(3.0)
                # 清空缓冲区
                self._client.settimeout(3.0)
                buf = b''
                try:
                    while True:
                        d = self._client.recv(4096)
                        if not d:
                            break
                        buf += d
                except socket.timeout:
                    pass
                finally:
                    self._client.settimeout(self.timeout)
                print(f"After AUTHENTICATE NONE buf: {buf!r}")
                # 清除 OSA 命令处理状态
                self.send_command("*CLS", expect_response=False)
                time.sleep(1.0)
        except Exception as e:
            print(f"LOGIN error: {e}")
        time.sleep(0.5)

    def __enter__(self):
        self.tcp_connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    # ── 私有：扫频辅助 ────────────────────────────────────────────────

    def _sweep_and_wait(self, start_freq: float, end_freq: float) -> None:
        """设置频率范围（Hz → nm）并执行一次单次扫频，等待完成。"""
        # Hz → nm: lambda = c / f
        start_nm = constants.c / start_freq * 1e9
        end_nm = constants.c / end_freq * 1e9

        self.send_command("*CLS", False)
        time.sleep(0.3)
        self.send_command(f":SENSe:WAVelength:STARt {start_nm}E-9", False)
        self.send_command(f":SENSe:WAVelength:STOP {end_nm}E-9", False)
        self.send_command(":SENSe:SWEep:POINts:AUTO OFF", False)
        self.send_command(":SENSe:SWEep:POINts 1001", False)
        self.send_command(":FORMAT:DATA ASCII", False)
        self.send_command(":TRACE:ACTIVE TRA", False)
        self.send_command(":INITiate:SMODe SINGle", False)
        self.send_command("*CLS", False)
        self.send_command(":INITiate", False)

        t0 = time.time()
        while True:
            self.send_command(":STATus:OPERation:EVENt?", True, 2.0)  # 清除残留
            resp = self.send_command(":STATus:OPERation:EVENt?", True, 2.0)
            try:
                if int(float(resp)) == 0:
                    break
            except Exception:
                pass
            if time.time() - t0 > 120:
                raise TimeoutError("OSA sweep timeout (>120s)")
            time.sleep(0.5)

    def _get_wavelength_nm(self) -> np.ndarray:
        """获取当前 trace 的波长数组（单位：nm）。

        OSA :TRACe[:DATA]:X? 返回波长数据，单位为米（m）。
        """
        self.send_command(":TRACe:DATA:SNUMber? TRA", True, 5.0)  # 清除残留
        snum_resp = self.send_command(":TRACe:DATA:SNUMber? TRA", True, 10.0)
        snum = int(float(snum_resp)) if snum_resp.strip() else 0
        if snum == 0:
            raise IOError("OSA trace 数据为空（0 点），请确认扫频范围和光学信号")

        self.send_command(":TRACe:DATA:X? TRA", True, 5.0)  # 清除残留
        raw = self.send_command(":TRACe:DATA:X? TRA", True, 30.0)
        # OSA 返回米（m），转为 nm（×1e9）
        values_m = np.array([float(v) for v in raw.split(',') if v.strip()])
        return values_m * 1e9

    def _get_trace_data(self) -> np.ndarray:
        """获取当前 trace 的功率谱数组（dBm）。"""
        self.send_command(":TRACe:DATA:Y? TRA", True, 5.0)  # 清除残留
        raw = self.send_command(":TRACe:DATA:Y? TRA", True, 30.0)
        return np.array([float(v) for v in raw.split(',') if v.strip()])

    # ── 公开API ──────────────────────────────────────────────────────

    def save_spectrum_data(self, start_freq: float, end_freq: float,
                           save_dir: str = './data', name_prefix: str = 'spectrum') -> str:
        """执行一次扫频并将频谱数据保存为 CSV 文件。

        Args:
            start_freq: 起始频率 (Hz)，例如 191.5e12
            end_freq:    结束频率 (Hz)，例如 196.5e12
            save_dir:    保存目录
            name_prefix: 文件名前缀

        Returns:
            保存的文件路径（字符串）
        """
        import datetime
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        self._sweep_and_wait(start_freq, end_freq)
        time.sleep(1.0)

        wl_nm = self._get_wavelength_nm()
        trace = self._get_trace_data()

        if wl_nm.shape != trace.shape:
            raise ValueError(f"波长与功率数据长度不一致: {wl_nm.shape} vs {trace.shape}")

        # 计算对应的频率 THz
        freq_thz = constants.c / (wl_nm * 1e-9) * 1e-12

        ts = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
        filename = f"{name_prefix}_{ts}.csv"
        filepath = save_path / filename

        df = pd.DataFrame({
            'wavelength_nm': wl_nm,
            'frequency_THz': freq_thz,
            'power_dBm': trace
        })
        df.to_csv(filepath, index=False)
        print(f"[OSA] 频谱数据已保存: {filepath}")
        return str(filepath)

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

        need = 2 + n_digits
        if len(header) < need:
            header += self._recv_exact(need - len(header), chunk_size=chunk_size)

        size_str = header[2:2 + n_digits].decode(errors='strict')
        data_len = int(size_str)

        data_start = 2 + n_digits
        already = len(header) - data_start
        data = bytearray()
        if already > 0:
            data.extend(header[data_start:])

        if already < data_len:
            data.extend(self._recv_exact(data_len - already, chunk_size=chunk_size))

        return bytes(data)

    def save_screen_image(self, save_dir: str = '../data',
                          name_prefix: str = 'osa_screen',
                          color: bool = True,
                          fmt: str = "bmp",
                          storage: str = "int") -> str:
        """截取并保存 OSA 屏幕图像。

        依据用户手册：先用 :MMEM:STOR:GRAP 保存图像到仪器内存，
        再用 :MMEM:DATA? 配合 query_binary_block 读取文件数据。

        Args:
            save_dir:    保存目录
            name_prefix: 文件名前缀（不含扩展名）
            color:       是否彩色（True=color, False=mono）
            fmt:         图像格式（bmp/png 等）
            storage:     存储位置（int/EXT）

        Returns:
            保存的文件路径（字符串）
        """
        import datetime
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        ext = fmt.lower().lstrip('.')
        storage_arg = storage.lower()

        # 1) 在仪器侧生成文件（不带扩展名）
        color_arg = "color" if color else "mono"
        self.send_command(
            f':MMEM:STOR:GRAP {color_arg},{ext},"{name_prefix}",{storage_arg}',
            expect_response=False
        )

        # 2) 用 query_binary_block 读取二进制数据
        remote_name = f"{name_prefix}.{ext}"
        image_data = self.query_binary_block(f':MMEM:DATA? "{remote_name}",{storage_arg}')

        # 3) 写入本机目录
        local_path = save_path / remote_name
        local_path.write_bytes(image_data)

        print(f"[OSA] 屏幕图像已保存: {local_path} ({len(image_data)} bytes)")
        return str(local_path)


def save_current_image(path_dir='../data', name_id=1):
    """保存 OSA 频谱数据（CSV）以及屏幕图像（PNG）的便捷 CLI 函数。"""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config as cfg_module
    cfg = cfg_module.get_config()
    with OpticalSpectrumAnalyzer(osa_ip=cfg.device.osa.ip, osa_port=cfg.device.osa.port) as osa:
        csv_path = osa.save_spectrum_data(
            start_freq=191.3e12,
            end_freq=191.5e12,
            save_dir=path_dir,
            name_prefix=f'spectrum_{name_id}'
        )
        print("频谱已保存:", csv_path)
        img_path = osa.save_screen_image(
            save_dir=path_dir,
            name_prefix=f'osa_screen_{name_id}'
        )
        print("屏幕图像已保存:", img_path)
    return csv_path, img_path


if __name__ == '__main__':
    save_current_image()
