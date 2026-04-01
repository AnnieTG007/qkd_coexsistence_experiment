# -*- coding: utf-8 -*-
"""
ASE 光源串口控制脚本（含软激活查询/设置）
- 查询设备类型
- 查询工作状态（电流、温度）
- 查询/设置目标功率（并核验）
- 查询/设置软激活；设置功率前自动确保软激活=开

依赖：pyserial   pip install pyserial
"""

import time
import serial


class ASESource:
    def __init__(self, port: str, baud: int = 9600, timeout: float = 2.0):
        self.com_port = port
        self.baud_rate = baud
        self.timeout = timeout
        self.ser = None  # type: serial.Serial | None
        self._device_type = None  # 0/1/2/3

    # -------------------- 串口管理 --------------------
    def openCom(self):
        if self.ser is None or (not self.ser.is_open):
            self.ser = serial.Serial(
                self.com_port,
                self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
        return self.ser

    def closeCom(self):
        if self.ser is not None and self.ser.is_open:
            self.ser.close()
        self.ser = None

    # -------------------- 协议工具 --------------------
    @staticmethod
    def _sum8(values):
        return sum(values) & 0xFF

    def _build_command(self, addr: int, data: bytes | None = None) -> bytes:
        if data is None:
            data = b""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("data 必须是 bytes/bytearray")
        if not (0 <= addr <= 0xFF):
            raise ValueError("addr 必须是 0~255")

        LEN = len(data) + 2
        frame_wo_sum = bytes([0xEF, 0xEF, LEN, addr]) + data
        SUM = self._sum8(frame_wo_sum)
        return frame_wo_sum + bytes([SUM])

    def _write(self, frame: bytes):
        s = self.openCom()
        s.write(frame)

    def _read_exact(self, n: int) -> bytes:
        s = self.openCom()
        buf = bytearray()
        start = time.time()
        while len(buf) < n:
            chunk = s.read(n - len(buf))
            if chunk:
                buf.extend(chunk)
            else:
                if self.timeout is not None and (time.time() - start) > self.timeout:
                    break
        return bytes(buf)

    def _read_response(self) -> bytes:
        # 同步到 ED FA
        s = self.openCom()

        def read_one():
            b = s.read(1)
            return b if b else b""

        b = read_one()
        while b and b[0] != 0xED:
            b = read_one()
        if not b:
            return b""

        b2 = read_one()
        while b2 and b2[0] == 0xED:
            b2 = read_one()
        if not b2 or b2[0] != 0xFA:
            return self._read_response()

        len_bytes = self._read_exact(1)
        if len(len_bytes) != 1:
            return b""
        LEN = len_bytes[0]

        body = self._read_exact(LEN)
        if len(body) != LEN:
            return b""

        frame = bytes([0xED, 0xFA, LEN]) + body
        calc_sum = self._sum8(frame[:-1])
        if calc_sum != frame[-1]:
            raise ValueError(
                f"返回校验错误：calc=0x{calc_sum:02X}, got=0x{frame[-1]:02X}, frame={frame.hex(' ').upper()}"
            )
        return frame

    # -------------------- 设备命令 --------------------
    def get_device_type(self) -> int:
        cmd = self._build_command(0x02, b"")
        print("发送(设备类型):", cmd.hex(" ").upper())
        self._write(cmd)
        resp = self._read_response()
        print("接收(设备类型):", (resp or b"").hex(" ").upper())
        if len(resp) < 4:
            raise RuntimeError("返回帧过短")
        if resp[3] != 0x02:
            raise RuntimeError(f"返回地址不匹配，期望0x02，实际0x{resp[3]:02X}")

        DATA = resp[4:-1]
        dev_type = DATA[13] if len(DATA) >= 14 else (DATA[-1] if DATA else 0)
        if dev_type not in (0, 1, 2, 3):
            print(f"警告：DeviceType 非标准值：{dev_type}")
        self._device_type = dev_type
        return dev_type

    def query_status(self) -> dict:
        if self._device_type is None:
            self.get_device_type()

        cmd = self._build_command(0x00, b"")
        print("发送(状态查询):", cmd.hex(" ").upper())
        self._write(cmd)
        resp = self._read_response()
        print("接收(状态查询):", (resp or b"").hex(" ").upper())

        if len(resp) < 4:
            raise RuntimeError("返回帧过短")
        if resp[3] != 0x00:
            raise RuntimeError(f"返回地址不匹配，期望0x00，实际0x{resp[3]:02X}")

        DATA = resp[4:-1]
        dt = self._device_type
        if dt in (0, 1):
            if len(DATA) < 10:
                raise RuntimeError("返回 DATA 长度不足(类型0/1)")
            cur = DATA[0] * 256 + DATA[1]
            temp = (DATA[8] * 256 + DATA[9]) / 100.0
        else:
            if len(DATA) < 12:
                raise RuntimeError("返回 DATA 长度不足(类型2/3)")
            cur = DATA[2] * 256 + DATA[3]
            temp = (DATA[10] * 256 + DATA[11]) / 100.0

        return {"CurRead_mA": float(cur), "LDTemp_C": float(temp), "DeviceType": int(dt)}

    def query_target_power_mw(self) -> float:
        if self._device_type is None:
            self.get_device_type()

        cmd = self._build_command(0x03, b"")
        print("发送(查询功率):", cmd.hex(" ").upper())
        self._write(cmd)
        resp = self._read_response()
        print("接收(查询功率):", (resp or b"").hex(" ").upper())

        if len(resp) < 7:
            raise RuntimeError("返回帧过短")
        if resp[3] != 0x03:
            raise RuntimeError(f"返回地址不匹配，期望0x03，实际0x{resp[3]:02X}")

        DATA = resp[4:-1]
        if len(DATA) < 2:
            raise RuntimeError("返回 DATA 长度不足以解析功率")
        HSB, LSB = DATA[0], DATA[1]
        raw = HSB * 256 + LSB
        dt = self._device_type
        return (raw / 10.0) if dt in (0, 1, 2) else float(raw)

    # -------------------- 软激活 --------------------
    def query_soft_active(self) -> int:
        """
        查询软激活（ADDR=0x25）
        返回 0 或 1
        文档：发送 EF EF 02 25 05，返回 ED FA 03 25 SoftActive SUM
        """
        cmd = self._build_command(0x25, b"")
        print("发送(查询软激活):", cmd.hex(" ").upper())
        self._write(cmd)
        resp = self._read_response()
        print("接收(查询软激活):", (resp or b"").hex(" ").upper())

        if len(resp) < 6:
            raise RuntimeError("返回帧过短(软激活)")
        if resp[3] != 0x25:
            raise RuntimeError(f"返回地址不匹配，期望0x25，实际0x{resp[3]:02X}")

        DATA = resp[4:-1]
        if len(DATA) < 1:
            raise RuntimeError("返回 DATA 长度不足(软激活)")
        soft = DATA[0]
        return 1 if soft else 0

    def set_soft_active(self, on: bool) -> int:
        """
        设置软激活（ADDR=0x26），on=True/False -> 1/0
        返回回读状态（0/1）
        文档：发送 EF EF 03 26 SoftActive SUM，返回 ED FA 03 25 SoftActive SUM
        """
        soft_val = 1 if on else 0
        cmd = self._build_command(0x26, bytes([soft_val]))
        print("发送(设置软激活):", cmd.hex(" ").upper())
        self._write(cmd)
        resp = self._read_response()
        print("接收(设置软激活回显):", (resp or b"").hex(" ").upper())

        if len(resp) < 6:
            raise RuntimeError("返回帧过短(设置软激活)")
        if resp[3] != 0x25:
            raise RuntimeError(f"返回地址不匹配，期望0x25(回显地址)，实际0x{resp[3]:02X}")

        DATA = resp[4:-1]
        if len(DATA) < 1:
            raise RuntimeError("返回 DATA 长度不足(设置软激活)")
        return 1 if DATA[0] else 0

    def _ensure_soft_active_on(self) -> None:
        """
        确保软激活=1；若未开启则自动开启并确认。
        """
        try:
            state = self.query_soft_active()
            if state != 1:
                print("软激活未开启，正在开启...")
                new_state = self.set_soft_active(True)
                if new_state != 1:
                    raise RuntimeError("软激活开启失败")
                # 给硬件一点稳定时间（视设备需要可调整）
                time.sleep(0.1)
        except Exception as e:
            raise RuntimeError(f"检查/开启软激活失败：{e}")

    # -------------------- 设置功率（自动确保软激活） --------------------
    def set_target_power_mw(self, power_mw: float) -> dict:
        if self._device_type is None:
            self.get_device_type()

        # 先确保软激活=1
        self._ensure_soft_active_on()

        dt = self._device_type
        raw = int(round(power_mw * 10.0)) if dt in (0, 1, 2) else int(round(power_mw))
        if not (0 <= raw <= 0xFFFF):
            raise ValueError("目标功率超出可编码范围 (0~65535)")

        HSB = (raw // 256) & 0xFF
        LSB = raw & 0xFF
        cmd = self._build_command(0x04, bytes([HSB, LSB]))
        print("发送(设置功率):", cmd.hex(" ").upper())
        self._write(cmd)

        resp = self._read_response()
        print("接收(设置功率回显):", (resp or b"").hex(" ").upper())

        echo_ok = False
        echo_mw = None
        if resp and len(resp) >= 7 and resp[3] == 0x03:
            HSB_e, LSB_e = resp[4], resp[5]
            raw_e = HSB_e * 256 + LSB_e
            echo_mw = (raw_e / 10.0) if dt in (0, 1, 2) else float(raw_e)
            echo_ok = (raw_e == raw)

        time.sleep(0.1)
        readback_mw = self.query_target_power_mw()
        ok = echo_ok and (abs(readback_mw - power_mw) < (0.1 if dt in (0, 1, 2) else 1.0))
        return {
            "requested_mW": float(power_mw),
            "echo_mW": float(echo_mw) if echo_mw is not None else None,
            "readback_mW": float(readback_mw),
            "ok": bool(ok),
        }


if __name__ == "__main__":
    # 根据需要修改串口号和设定功率
    port = "COM6"
    baud = 9600
    target_power_mw = 100
    dev = ASE_source(port, baud)
    try:
        # 以下为示例，实际应用时需要哪个用哪个
        dt = dev.get_device_type()
        print(f"[设备类型] DeviceType={dt}")

        # 软激活查询/设置演示
        sa = dev.query_soft_active()
        print(f"[软激活] 当前={sa}")
        if sa == 0:
            print("[软激活] 未开启，尝试开启...")
            print("[软激活] 设置结果=", dev.set_soft_active(True))

        # 查询状态
        st = dev.query_status()
        print(f"[状态] 电流={st['CurRead_mA']} mA, 温度={st['LDTemp_C']} °C")

        # 查询当前功率
        cur_p = dev.query_target_power_mw()
        print(f"[功率] 当前目标功率={cur_p} mW")

        # 设置功率（内部会自动确保软激活=1）
        res = dev.set_target_power_mw(target_power_mw)
        print("[设置功率结果]", res)

    except Exception as e:
        print("发生错误：", e)
    finally:
        dev.closeCom()