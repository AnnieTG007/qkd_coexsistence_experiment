import socket
import re
import pandas as pd
import time
from pathlib import Path
import numpy as np

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
        self.buffer_size = InputBufferSize

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
                data = self._client.recv(self.buffer_size)
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

    def _measure_bandwidth(self, wavelengths: np.ndarray, powers: np.ndarray,
                          ref_power: float, threshold_db: float) -> tuple[float, float, float]:
        """
        测量指定衰减值对应的带宽。

        参数:
            wavelengths: 波长数组 (m)
            powers: 功率数组 (dBm)
            ref_power: 参考功率 (dBm)，通常为峰值功率
            threshold_db: 衰减值 (dB)，如 3 表示 peak - 3dB

        返回:
            (low_freq, high_freq, bandwidth)
            其中 freq 单位为 Hz
        """
        threshold_power = ref_power - threshold_db

        # 找到超过阈值的区间
        above_threshold = powers >= threshold_power

        if not np.any(above_threshold):
            return 0.0, 0.0, 0.0

        # 找到第一个和最后一个超过阈值的索引
        indices = np.where(above_threshold)[0]
        low_idx = indices[0]
        high_idx = indices[-1]

        # 转换波长为频率 (Hz)
        c = 299792458  # 光速 m/s
        low_freq = c / wavelengths[low_idx]
        high_freq = c / wavelengths[high_idx]
        bandwidth = high_freq - low_freq

        return low_freq, high_freq, bandwidth

    def save_spectrum_data(self,
                           start_freq: float,
                           end_freq: float,
                           save_dir: str | None = None,
                           basename: str | None = None,
                           sweep_points: int | None = None) -> dict:
        """
        执行光谱扫描，保存频谱数据、图像，并测量3dB/30dB带宽。
        """

        def _check_osa_error(where: str = ""):
            err = self.send_command(":SYST:ERR?", expect_response=True, timeout=2.0).strip()
            # 无错误通常返回 0 或 0,"No error"
            if not err.startswith("0"):
                raise RuntimeError(f"OSA error after {where}: {err}")

        def _parse_ascii_csv_floats(resp: str, name: str) -> np.ndarray:
            vals = [x.strip() for x in resp.split(",") if x.strip()]
            if not vals:
                raise ValueError(f"{name} response is empty.")
            try:
                return np.array([float(v) for v in vals], dtype=float)
            except ValueError as e:
                raise ValueError(f"{name} contains non-numeric data: {resp[:200]!r}") from e

        def _get_trace_points(trace_name: str) -> int:
            resp = self.send_command(f":TRACe:DATA:SNUMber? {trace_name}",
                                     expect_response=True, timeout=10.0).strip()
            try:
                return int(float(resp))
            except ValueError as e:
                raise ValueError(f"Invalid SNUMBER response for {trace_name}: {resp!r}") from e

        if save_dir is None:
            save_dir_path = Path(__file__).resolve().parent / "data" / "spectrum"
        else:
            save_dir_path = Path(save_dir).expanduser().resolve() / "spectrum"

        save_dir_path.mkdir(parents=True, exist_ok=True)

        if basename is None:
            basename = time.strftime("spectrum_%Y%m%d_%H%M%S")

        preferred_trace = "TRA"
        all_traces = ["TRA", "TRB", "TRC", "TRD", "TRE", "TRF", "TRG"]

        # 0. 清空旧错误队列
        try:
            while True:
                err = self.send_command(":SYST:ERR?", expect_response=True, timeout=2.0).strip()
                if err.startswith("0"):
                    break
        except Exception:
            pass

        # 1. 清空所有旧 trace 数据，避免读到旧波形
        self.send_command(":TRACe:DELete:ALL", expect_response=False)

        # 2. 设置扫描范围
        self.send_command(f":SENSe:WAVelength:STARt {start_freq}HZ", expect_response=False)
        _check_osa_error("set start")

        self.send_command(f":SENSe:WAVelength:STOP {end_freq}HZ", expect_response=False)
        _check_osa_error("set stop")

        # 3. 设置扫描点数（可选）
        if sweep_points is not None:
            self.send_command(f":SENSe:SWEep:POINts {sweep_points}", expect_response=False)
            _check_osa_error("set sweep points")

        # 4. 尽量把 TRA 设成活动写入曲线
        self.send_command(f":TRACe:ACTive {preferred_trace}", expect_response=False)
        _check_osa_error("set active trace")

        self.send_command(f":TRACe:ATTRibute:{preferred_trace} WRITe", expect_response=False)
        _check_osa_error("set trace attribute write")

        self.send_command(f":TRACe:STATe:{preferred_trace} ON", expect_response=False)
        _check_osa_error("set trace state on")

        # 5. 单次扫描
        self.send_command(":INITiate:SMODe SINGle", expect_response=False)
        _check_osa_error("set single sweep mode")

        self.send_command("*CLS", expect_response=False)

        self.send_command(":INITiate", expect_response=False)
        _check_osa_error("start sweep")

        # 6. 等待扫描完成
        t0 = time.time()
        max_wait_s = 120.0
        while True:
            resp = self.send_command(":STAT:OPER:EVEN?", expect_response=True, timeout=2.0)
            try:
                if int(float(resp)) & 1:
                    break
            except Exception:
                pass

            if time.time() - t0 > max_wait_s:
                err = self.send_command(":SYST:ERR?", expect_response=True, timeout=2.0)
                raise TimeoutError(f"Spectrum sweep wait exceeded {max_wait_s}s, last error: {err}")

            time.sleep(0.2)

        # 7. 查询当前活动曲线
        active_trace = self.send_command(":TRACe:ACTive?", expect_response=True, timeout=5.0).strip()

        # 8. 查询所有 trace 的数据点数，找真正有数据的那条
        trace_points = {}
        selected_trace = None
        for tr in all_traces:
            try:
                n = _get_trace_points(tr)
            except Exception:
                n = -1
            trace_points[tr] = n
            if selected_trace is None and n > 0:
                selected_trace = tr

        # 优先用 TRA；如果 TRA 没数据，但别的 trace 有数据，就自动切换
        if trace_points.get(preferred_trace, 0) > 0:
            selected_trace = preferred_trace

        if selected_trace is None:
            err = self.send_command(":SYST:ERR?", expect_response=True, timeout=2.0).strip()
            raise ValueError(
                f"No trace has data after sweep. active_trace={active_trace}, "
                f"trace_points={trace_points}, SYST:ERR? -> {err}"
            )

        # 9. 读取真正有数据的 trace 前，强制设为 ASCII 格式
        # self.send_command(":FORMat:DATA ASCii", expect_response=False)
        # _check_osa_error("set data format ascii")

        x_resp = self.send_command(f":TRACe:DATA:X? {selected_trace}",
                                   expect_response=True, timeout=30.0)
        y_resp = self.send_command(f":TRACe:DATA:Y? {selected_trace}",
                                   expect_response=True, timeout=30.0)

        # 可选调试输出
        print("X head:", repr(x_resp[:120]))
        print("Y head:", repr(y_resp[:120]))

        wavelengths = _parse_ascii_csv_floats(x_resp, f"{selected_trace} X")  # 单位 m
        powers = _parse_ascii_csv_floats(y_resp, f"{selected_trace} Y")

        if len(wavelengths) != len(powers):
            raise ValueError(
                f"{selected_trace} X/Y length mismatch: len(X)={len(wavelengths)}, len(Y)={len(powers)}"
            )

        if len(wavelengths) == 0:
            raise ValueError(f"{selected_trace} parsed data is empty.")

        # 10. 排序
        sort_idx = np.argsort(wavelengths)
        wavelengths = wavelengths[sort_idx]
        powers = powers[sort_idx]

        # 11. 保存频谱数据 CSV
        spectrum_csv_path = save_dir_path / f"{basename}.csv"
        df_spectrum = pd.DataFrame({
            "trace": [selected_trace] * len(wavelengths),
            "wavelength_m": wavelengths,
            "power": powers
        })
        df_spectrum.to_csv(spectrum_csv_path, index=False)

        # 12. 保存频谱图像
        image_bmp_path = self.save_current_image(
            save_dir=str(save_dir_path.parent),
            basename=basename,
            color=True,
            fmt="bmp"
        )

        # 13. 计算带宽
        peak_idx = np.argmax(powers)
        peak_power = float(powers[peak_idx])
        peak_wavelength = float(wavelengths[peak_idx])

        c = 299792458.0
        peak_freq = c / peak_wavelength

        low_3db, high_3db, bw_3db = self._measure_bandwidth(
            wavelengths, powers, peak_power, 3
        )
        low_30db, high_30db, bw_30db = self._measure_bandwidth(
            wavelengths, powers, peak_power, 30
        )

        # 14. 保存带宽结果 CSV
        bandwidth_csv_path = save_dir_path / f"{basename}_bandwidth.csv"
        df_bw = pd.DataFrame([{
            "trace": selected_trace,
            "active_trace_after_sweep": active_trace,
            "peak_power": peak_power,
            "peak_wavelength_m": peak_wavelength,
            "peak_freq_hz": peak_freq,
            "3dB_low_freq_hz": low_3db,
            "3dB_high_freq_hz": high_3db,
            "3dB_bandwidth_hz": bw_3db,
            "30dB_low_freq_hz": low_30db,
            "30dB_high_freq_hz": high_30db,
            "30dB_bandwidth_hz": bw_30db,
        }])
        df_bw.to_csv(bandwidth_csv_path, index=False)

        return {
            "trace_used": selected_trace,
            "active_trace_after_sweep": active_trace,
            "trace_points": trace_points,
            "spectrum_csv": str(spectrum_csv_path),
            "image_bmp": str(image_bmp_path),
            "bandwidth_csv": str(bandwidth_csv_path),
            "peak_power": peak_power,
            "peak_freq": peak_freq,
            "3dB_bandwidth": bw_3db,
            "30dB_bandwidth": bw_30db,
        }

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

def save_current_data(start_freq, end_freq, path_dir='./../data', name_id=1):
    import config as cfg_module
    cfg = cfg_module.get_config()
    with OpticalSpectrumAnalyzer(osa_ip=cfg.device.osa.ip, osa_port=cfg.device.osa.port) as osa:
        osa.auto_sweep(max_wait_s=120)
        path = osa.save_current_image(save_dir=path_dir, basename="my_capture_" + str(name_id))
        data = osa.save_spectrum_data(start_freq=start_freq, end_freq=end_freq)
        print(data)
        print("Saved to:", path)
    return

if __name__ == '__main__':
    save_current_data(start_freq=191.2e12, end_freq=191.5e12,path_dir='./../data', name_id=1)
