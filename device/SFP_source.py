from __future__ import annotations

import json
import math
import socket
import time
from dataclasses import dataclass
from typing import Dict, Optional

try:
    import serial  # pyserial
except ImportError:
    serial = None


C_LIGHT = 299792458.0  # m/s


class TunableSFPError(RuntimeError):
    pass


@dataclass
class ModuleInfo:
    vendor: str = ""
    part_number: str = ""
    serial_number: str = ""

    @classmethod
    def from_dict(cls, d: Dict) -> "ModuleInfo":
        return cls(
            vendor=str(d.get("vendor", "")),
            part_number=str(d.get("pn", d.get("part_number", ""))),
            serial_number=str(d.get("sn", d.get("serial_number", ""))),
        )


class _BaseTransport:
    def close(self) -> None:
        pass

    def request(self, line: str) -> Dict:
        raise NotImplementedError


class _SerialTransport(_BaseTransport):
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 2.0,
        write_timeout: float = 2.0,
        encoding: str = "utf-8",
    ) -> None:
        if serial is None:
            raise ImportError("pyserial 未安装，请先执行: pip install pyserial")
        self._encoding = encoding
        self._ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            write_timeout=write_timeout,
        )
        time.sleep(0.2)
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()

    def request(self, line: str) -> Dict:
        cmd = (line.strip() + "\n").encode(self._encoding)
        self._ser.write(cmd)
        self._ser.flush()

        raw = self._ser.readline()
        if not raw:
            raise TunableSFPError(f"串口无响应: {line}")

        text = raw.decode(self._encoding, errors="replace").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise TunableSFPError(f"串口返回不是合法 JSON: {text}") from e


class _TCPTransport(_BaseTransport):
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 2.0,
        encoding: str = "utf-8",
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._encoding = encoding

    def request(self, line: str) -> Dict:
        data = (line.strip() + "\n").encode(self._encoding)
        with socket.create_connection((self._host, self._port), timeout=self._timeout) as s:
            s.settimeout(self._timeout)
            s.sendall(data)

            chunks = []
            while True:
                ch = s.recv(1)
                if not ch:
                    break
                if ch == b"\n":
                    break
                chunks.append(ch)

        if not chunks:
            raise TunableSFPError(f"TCP 无响应: {line}")

        text = b"".join(chunks).decode(self._encoding, errors="replace").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise TunableSFPError(f"TCP 返回不是合法 JSON: {text}") from e


class TunableSFPController:
    """
    对用户只暴露：
      - 初始化时显示模块信息
      - get_wavelength_nm()
      - set_wavelength_nm()

    板端协议要求：
      INFO
      GET_CH
      SET_CH <n>

    返回一行 JSON。
    """

    def __init__(
        self,
        transport: str,
        *,
        serial_port: Optional[str] = None,
        baudrate: int = 115200,
        host: Optional[str] = None,
        port: Optional[int] = None,
        timeout: float = 2.0,
        channel_wavelength_map_nm: Optional[Dict[int, float]] = None,
        verbose: bool = True,
    ) -> None:
        transport = transport.lower().strip()
        self.verbose = verbose

        if channel_wavelength_map_nm is None:
            self._ch2wl = self._default_96ch_50ghz_map()
        else:
            self._ch2wl = dict(channel_wavelength_map_nm)

        self._wl2ch = self._build_reverse_map(self._ch2wl)

        if transport == "serial":
            if not serial_port:
                raise ValueError("transport='serial' 时必须提供 serial_port")
            self._link = _SerialTransport(
                port=serial_port,
                baudrate=baudrate,
                timeout=timeout,
            )
        elif transport == "tcp":
            if not host or port is None:
                raise ValueError("transport='tcp' 时必须提供 host 和 port")
            self._link = _TCPTransport(
                host=host,
                port=port,
                timeout=timeout,
            )
        else:
            raise ValueError("transport 只能是 'serial' 或 'tcp'")

        info = self._request_ok("INFO")
        self.module_info = ModuleInfo.from_dict(info)

        if self.verbose:
            print("[TunableSFP] 模块已连接")
            print(f"  Vendor : {self.module_info.vendor}")
            print(f"  PN     : {self.module_info.part_number}")
            print(f"  SN     : {self.module_info.serial_number}")

    def close(self) -> None:
        self._link.close()

    def _request_ok(self, cmd: str) -> Dict:
        resp = self._link.request(cmd)
        if not isinstance(resp, dict):
            raise TunableSFPError(f"响应类型错误: {resp!r}")
        if not resp.get("ok", False):
            raise TunableSFPError(resp.get("error", f"命令失败: {cmd}"))
        return resp

    @staticmethod
    def _default_96ch_50ghz_map() -> Dict[int, float]:
        """
        默认使用常见 96x50GHz DWDM 映射：
        ch1 = 191.35 THz, 每通道 +0.05 THz

        注意：这只是工程默认值。
        最终请以你的模块真实 channel plan / OSA 标定结果为准。
        """
        mapping = {}
        for ch in range(1, 97):
            freq_thz = 191.35 + 0.05 * (ch - 1)
            wl_nm = (C_LIGHT / (freq_thz * 1e12)) * 1e9
            mapping[ch] = wl_nm
        return mapping

    @staticmethod
    def _build_reverse_map(ch2wl: Dict[int, float]) -> Dict[float, int]:
        return {round(v, 4): k for k, v in ch2wl.items()}

    def get_channel(self) -> int:
        resp = self._request_ok("GET_CH")
        ch = int(resp["channel"])
        if ch not in self._ch2wl:
            raise TunableSFPError(f"当前 channel={ch} 不在映射表中")
        return ch

    def get_wavelength_nm(self) -> float:
        ch = self.get_channel()
        return self._ch2wl[ch]

    def set_channel(self, channel: int) -> None:
        if channel not in self._ch2wl:
            raise ValueError(f"channel 超出映射范围: {channel}")
        self._request_ok(f"SET_CH {channel}")

    def set_wavelength_nm(self, wavelength_nm: float) -> int:
        """
        将目标波长映射到最近的 channel，然后下发 SET_CH。
        返回实际采用的 channel。
        """
        if not isinstance(wavelength_nm, (float, int)):
            raise TypeError("wavelength_nm 必须是数字")

        target = float(wavelength_nm)
        best_ch = min(self._ch2wl.keys(), key=lambda ch: abs(self._ch2wl[ch] - target))
        best_wl = self._ch2wl[best_ch]

        if self.verbose:
            print(
                f"[TunableSFP] 请求波长 {target:.4f} nm -> "
                f"采用 channel {best_ch} ({best_wl:.4f} nm)"
            )

        self.set_channel(best_ch)
        return best_ch

    def get_module_info(self) -> ModuleInfo:
        return self.module_info

    def __enter__(self) -> "TunableSFPController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

if __name__ == "__main__":
    with TunableSFPController(
            transport="serial",
            serial_port="COM3",  # 改成你的串口号
            baudrate=115200,
            verbose=True,
    ) as sfp:
        wl = sfp.get_wavelength_nm()
        print("当前波长:", wl)

        sfp.set_wavelength_nm(1552.52)

        wl2 = sfp.get_wavelength_nm()
        print("设置后波长:", wl2)
