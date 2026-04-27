import pyvisa


class TunableLaserSource:
    def __init__(self, mtp_ip, iqs_ip):
        # MTP设备的局域网IP
        self.mtp_ip = 'TCPIP0::' + mtp_ip + '::inst0::INSTR'
        # IQS设备的局域网IP
        self.iqs_ip = 'TCPIP0::' + iqs_ip + '::inst0::INSTR'
        return

    def set_on_and_off(self, num_chan, state_set):
        if num_chan in [1, 2, 3, 4]:
            # 前四个信道分配至MTP中
            ip = self.mtp_ip
        elif num_chan in [5, 6, 7, 8]:
            # 后四个信道分配至IQS中
            ip = self.iqs_ip
            num_chan = num_chan - 4
        else:
            raise ValueError('Selected channel is out of legal range!')

        if state_set == 'ON' or state_set == 'OFF':
            # 后四个信道由于分配到IQS设备，但IQS的信道编号仍从1开始，所以需要特殊处理
            # 前四个信道的信道编号就不用特殊处理了
            command = 'OUTP1:CHAN' + str(num_chan - 4 * (num_chan > 4)) + ':STATE ' + state_set
        else:
            raise ValueError('Undefined state settings!')

        command_set_state = command
        command_get_state = 'OUTP1:CHAN' + str(num_chan) + ':STATE?'

        # 创建资源管理器
        rm = pyvisa.ResourceManager()
        # 读取设备信息
        # print(rm.list_resources())
        tls = rm.open_resource(ip)
        tls.timeout = 10000
        tls.write_termination = '\n'
        tls.read_termination = '\n'
        try:
            # 不用理会PyCharm的警告，因为打开设备之后特定的类会包含这个命令
            # print(tls.query('*IDN?'))
            response = tls.query(command_get_state)
            # print(response)
            if response == state_set:
                pass
                # print('已达到指定状态：' + state_set)
            else:
                tls.write(command_set_state)
                response = tls.query(command_get_state)
                response.replace('\r', '')
                response.replace('\n', '')
                # if response == state_set:
                #     print('设置状态成功:' + state_set)
                # else:
                #     print('设置状态失败')
            tls.close()
            rm.close()
        except Exception as e:
            # 释放资源后重新抛出异常
            tls.close()
            rm.close()
            raise RuntimeError(f"TLS operation failed: {e}") from e
        finally:
            if tls.is_open:
                tls.close()
            rm.close()
        return

    def setFrequencyAndPower(self, num_chan, freq, launch_power):
        launch_power = round(launch_power * 10) / 10
        if num_chan in [1, 2, 3, 4]:
            # 前四个信道分配至MTP中
            ip = self.mtp_ip
        elif num_chan in [5, 6, 7, 8]:
            # 后四个信道分配至IQS中
            ip = self.iqs_ip
            num_chan = num_chan - 4
        else:
            raise ValueError('Selected channel is out of legal range!')

        command_set_frq = 'SOUR1:CHAN' + str(num_chan) + ':FREQ '+str(freq)
        command_get_frq = r'SOUR1:CHAN' + str(num_chan) + ':FREQ? SET'

        command_set_pow = 'SOUR1:CHAN' + str(num_chan) + ':POW ' + str(launch_power)
        command_get_pow = 'SOUR1:CHAN' + str(num_chan) + ':POW? SET'

        # 创建资源管理器
        rm = pyvisa.ResourceManager()
        # 读取设备信息
        # print(rm.list_resources())
        tls = rm.open_resource(ip)
        tls.timeout = 10000
        tls.write_termination = '\n'
        tls.read_termination = '\n'

        try:
            # 不用理会Pycharm警告，因为打开设备之后特定的类会包含这个命令
            # print(tls.query('*IDN?'))
            tls.write(command_set_pow)
            response = tls.query(command_get_pow)
            if abs(float(response) - launch_power) > 0.05:
                print('设置功率失败')
            else:
                pass
                # print('设置功率成功')

            tls.write(command_set_frq)
            response = tls.query(command_get_frq)
            if abs(float(response) - freq) > 1e3:
                print(response)
                print('设置频率失败')
            else:
                pass
                # print('设置频率成功')
            tls.close()
            rm.close()
        except Exception as e:
            # 释放资源后重新抛出异常
            tls.close()
            rm.close()
            raise RuntimeError(f"TLS operation failed: {e}") from e
        finally:
            if tls.is_open:
                tls.close()
            rm.close()
        return


if __name__ == "__main__":
    t = TunableLaserSource('192.168.1.102', '192.168.1.101')
    # 注意num_chan是端口号，与频率没有严格的对应关系
    for i in range(1,9):
        t.set_on_and_off(i, 'OFF')

    t.set_on_and_off(8, 'ON')
    t.setFrequencyAndPower(8, 193.2e12, 7)

    # launch_power单位是dBm
    # tls1.setFrequencyAndPower(6, 193.5e12, 13.9)
    # t.setFrequencyAndPower(1, 193.4e12, 13.9)
    #tls1.setFrequencyAndPower(3, 193.7e12, 13.9)
