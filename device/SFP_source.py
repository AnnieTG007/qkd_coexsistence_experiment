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
    def from_dict(cls, data: Dict) -> "ModuleInfo":
        return cls(
            vendor=str(data.get("vendor", "")),
            part_number=str(data.get("pn", data.get("part_number", ""))),
            serial_number=str(data.get("sn", data.get("serial_number", ""))),
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
        timeout: float = 5.0,
        write_timeout: float = 2.0,
        encoding: str = "utf-8",
    ) -> None:
        if serial is None:
            raise ImportError("pyserial is not installed. Run: pip install pyserial")

        self._encoding = encoding
        self._timeout = timeout
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

        deadline = time.monotonic() + self._timeout
        last_text = ""
        while time.monotonic() < deadline:
            raw = self._ser.readline()
            if not raw:
                continue

            text = raw.decode(self._encoding, errors="replace").strip()
            if not text:
                continue

            last_text = text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue

        if last_text:
            raise TunableSFPError(f"Serial response was not JSON: {last_text}")
        raise TunableSFPError(f"Serial timeout waiting for response to: {line}")


class _TCPTransport(_BaseTransport):
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 5.0,
        encoding: str = "utf-8",
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._encoding = encoding

    def request(self, line: str) -> Dict:
        data = (line.strip() + "\n").encode(self._encoding)
        with socket.create_connection((self._host, self._port), timeout=self._timeout) as sock:
            sock.settimeout(self._timeout)
            sock.sendall(data)

            chunks = []
            while True:
                ch = sock.recv(1)
                if not ch:
                    break
                if ch == b"\n":
                    break
                chunks.append(ch)

        if not chunks:
            raise TunableSFPError(f"TCP timeout waiting for response to: {line}")

        text = b"".join(chunks).decode(self._encoding, errors="replace").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise TunableSFPError(f"TCP response was not JSON: {text}") from exc


class TunableSFPController:
    """
    Python-side controller for the Vitis UART/JSON SFP firmware.

    Usage order:
      1. Build the Vitis application with device/sfp.c.
      2. Download/run that ELF on the FPGA/SoC board.
      3. Start this Python controller after the board-side JSON service is
         already running on the serial port.

    This class intentionally does not access SFP I2C/GPIO directly. The board
    firmware owns AXI IIC/GPIO; Python sends high-level commands over serial.

    Board protocol:
      INFO
      GET_CH
      SET_CH <n>
      GET_STATUS
      GET_DDM
      TX ON
      TX OFF
    """

    def __init__(
        self,
        transport: str,
        *,
        serial_port: Optional[str] = None,
        baudrate: int = 115200,
        host: Optional[str] = None,
        port: Optional[int] = None,
        timeout: float = 5.0,
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
                raise ValueError("serial_port is required when transport='serial'")
            self._link = _SerialTransport(
                port=serial_port,
                baudrate=baudrate,
                timeout=timeout,
            )
        elif transport == "tcp":
            if not host or port is None:
                raise ValueError("host and port are required when transport='tcp'")
            self._link = _TCPTransport(
                host=host,
                port=port,
                timeout=timeout,
            )
        else:
            raise ValueError("transport must be 'serial' or 'tcp'")

        info = self._request_ok("INFO")
        self.module_info = ModuleInfo.from_dict(info)

        if self.verbose:
            print("[TunableSFP] module connected")
            print(f"  Vendor : {self.module_info.vendor}")
            print(f"  PN     : {self.module_info.part_number}")
            print(f"  SN     : {self.module_info.serial_number}")

    def close(self) -> None:
        self._link.close()

    def _request_ok(self, cmd: str) -> Dict:
        resp = self._link.request(cmd)
        if not isinstance(resp, dict):
            raise TunableSFPError(f"Unexpected response type: {resp!r}")
        if not resp.get("ok", False):
            raise TunableSFPError(str(resp.get("error", f"Command failed: {cmd}")))
        return resp

    @staticmethod
    def _default_96ch_50ghz_map() -> Dict[int, float]:
        """
        Engineering default for a common 96-channel, 50 GHz DWDM plan:
        ch1 = 191.35 THz, each next channel adds 0.05 THz.

        Replace this with the module vendor channel plan or OSA calibration
        when exact wavelength accuracy matters.
        """
        mapping = {}
        for ch in range(1, 97):
            freq_thz = 191.35 + 0.05 * (ch - 1)
            mapping[ch] = (C_LIGHT / (freq_thz * 1e12)) * 1e9
        return mapping

    @staticmethod
    def _build_reverse_map(ch2wl: Dict[int, float]) -> Dict[float, int]:
        return {round(wavelength, 4): channel for channel, wavelength in ch2wl.items()}

    def get_channel(self) -> int:
        resp = self._request_ok("GET_CH")
        channel = int(resp["channel"])
        if channel not in self._ch2wl:
            raise TunableSFPError(f"Current channel={channel} is not in the wavelength map")
        return channel

    def set_channel(self, channel: int) -> Dict:
        if channel not in self._ch2wl:
            raise ValueError(f"Channel is out of configured range: {channel}")
        return self._request_ok(f"SET_CH {int(channel)}")

    def get_wavelength_nm(self) -> float:
        return self._ch2wl[self.get_channel()]

    def closest_channel_for_wavelength_nm(self, wavelength_nm: float) -> int:
        target = float(wavelength_nm)
        return min(self._ch2wl.keys(), key=lambda ch: abs(self._ch2wl[ch] - target))

    def set_wavelength_nm(self, wavelength_nm: float) -> int:
        if not isinstance(wavelength_nm, (float, int)):
            raise TypeError("wavelength_nm must be numeric")

        channel = self.closest_channel_for_wavelength_nm(float(wavelength_nm))
        wavelength = self._ch2wl[channel]

        if self.verbose:
            print(
                f"[TunableSFP] requested {float(wavelength_nm):.4f} nm -> "
                f"channel {channel} ({wavelength:.4f} nm)"
            )

        self.set_channel(channel)
        return channel

    def get_status(self) -> Dict:
        return self._request_ok("GET_STATUS")

    def get_ddm(self) -> Dict:
        resp = self._request_ok("GET_DDM")
        ddm = dict(resp)

        if "temperature_c_x100" in ddm:
            ddm["temperature_c"] = float(ddm["temperature_c_x100"]) / 100.0
        if "vcc_mv" in ddm:
            ddm["vcc_v"] = float(ddm["vcc_mv"]) / 1000.0
        if "tx_bias_ua" in ddm:
            ddm["tx_bias_ma"] = float(ddm["tx_bias_ua"]) / 1000.0
        if "tx_power_uw" in ddm:
            tx_power_mw = float(ddm["tx_power_uw"]) / 1000.0
            ddm["tx_power_mw"] = tx_power_mw
            ddm["tx_power_dbm"] = self._mw_to_dbm(tx_power_mw)
        if "rx_power_uw" in ddm:
            rx_power_mw = float(ddm["rx_power_uw"]) / 1000.0
            ddm["rx_power_mw"] = rx_power_mw
            ddm["rx_power_dbm"] = self._mw_to_dbm(rx_power_mw)

        return ddm

    def set_tx_enabled(self, enabled: bool) -> Dict:
        return self._request_ok("TX ON" if enabled else "TX OFF")

    def enable_tx(self) -> Dict:
        return self.set_tx_enabled(True)

    def disable_tx(self) -> Dict:
        return self.set_tx_enabled(False)

    def get_module_info(self) -> ModuleInfo:
        return self.module_info

    @staticmethod
    def _mw_to_dbm(power_mw: float) -> float:
        if power_mw <= 0:
            return -100.0
        return 10.0 * math.log10(power_mw)

    def __enter__(self) -> "TunableSFPController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


if __name__ == "__main__":
    with TunableSFPController(
        transport="serial",
        serial_port="COM3",
        baudrate=115200,
        verbose=True,
    ) as sfp:
        print("Current channel:", sfp.get_channel())
        print("Current wavelength:", sfp.get_wavelength_nm())
        sfp.set_wavelength_nm(1552.52)
        print("Updated wavelength:", sfp.get_wavelength_nm())
