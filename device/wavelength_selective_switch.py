import math
import time
import serial
import numpy as np


class WavelengthSelectiveSwitch:
    """
        com_power: 控制开关机的端口名字
        com_control: 控制设备交换的端口名字
        list_att: 默认的每个端口做的衰减补偿
        terminator: 设置起始和终止字符，默认CR
    """
    def __init__(self, com_power: str, com_control: str, list_att: np.array, terminator ='\r'):
        self.com_power = com_power
        self.com_control = com_control
        self.list_att_initial = list_att
        self.terminator = terminator

    def openCom(self, ord):
        # 打开一个串口
        if ord == 'power':
            obj_wss = serial.Serial(self.com_power, 115200, timeout=2)
        elif ord == 'control':
            obj_wss = serial.Serial(self.com_control, 115200, timeout=2)
        else:
            raise ValueError('只有power和control两个选项')
        return obj_wss

    def wsspower(self, set):
        if set.lower() not in ('on', 'off'):
            raise ValueError('只有on和off两个选项')
        # 发送命令
        command = 'power ' + set + self.terminator
        s = None
        try:
            if self.com_power == 'None':
                return
            s = self.openCom('power')
            # configureTerminator(objwss, "CR"); ???
            s.write(command.encode('utf-8'))
            response = self.read_wss_response(s)
        except Exception as e:
            print(f'无法打开串口 or 无法发送命令：{str(e)}')
            response = '---ERROR---'
        finally:
            if s is not None and s.is_open:
                s.close()
                # print("-power-串口管理器已关闭串口")
        return response


    def read_wss_response(self, objwss):
        # 睡眠，等待返回值传完
        time.sleep(0.5)
        response = []
        while objwss.in_waiting > 1:#???  一行数据结 束符号？？？数据终止符号？？？
            line = objwss.read_until(b'\r\n').decode('utf-8').rstrip()#???self.terminator.encode()
            response.append(line)
            # print('收到：{}'.format(line))
        if 'OK' not in response:
            print(f'收到：{response}')
        # 应该try 考虑报错吗？？？
        return response

    # 实现控制命令
    def wss_spa(self, num_device, begin_slot, end_slot, com_port, switch_port, att, unitofatt='dB'):
        '''
        ————功能———— 切换和设置衰减
        num_device设备是1还是2
        begin_slot开始的切片索引--频隙
        end_slot结束的切片索引
        com_port公共口索引（1 或者 2）
        switch_port交换口索引（1到20）
        att衰减，单位dB
        '''
        # 有效值校准
        if att < 0:
            raise ValueError('wss衰减输入的是正值，请处理一下负号')
        # 单位设置
        if unitofatt.lower() == 'dB'.lower():
            att = att
        elif unitofatt.lower() == 'noUnit':
            # dB 和 倍数之间的转换
            att = -10*math.log(att/10)
        else:
            raise ValueError('单位选取错误')
        # 只取整数部分
        att = round(att)
        # command =[ 'SPA 1 1:772,1:2,0']
        if com_port != 99 and switch_port !=99:# 99 ??
            att_adjust = self.list_att_initial[num_device-1][com_port-1][switch_port-1]
            att = round((att + att_adjust) * 10) # 单位：cB, 1 dB = 10 cB
        command = 'SPA {} {}:{},{}:{},{}'.format(num_device, begin_slot, end_slot, com_port, switch_port, att)
        command = command + self.terminator
        s = None
        try:
            s = self.openCom('control')
            s.write(command.encode('utf-8'))
            response = self.read_wss_response(s)
        except Exception as e:
            print(f'无法打开串口 or 无法发送命令：{e}')
            response = '---ERROR---'
        finally:
            if s is not None and s.is_open:
                s.close()
                # print("-control-串口管理器已关闭串口")
        return response

    def wss_spa_bandwidth(self, num_device, frequency, bandwidth, com_port, switch_port, att, unitofatt='dB'):
        f0 = 191.32500e12
        slice_width = 6.25e9
        f = frequency
        center_slice = round((f - f0) / slice_width) + 1
        number_of_slices = round(bandwidth / slice_width)
        if number_of_slices % 2 == 0:
            # 偶数切片  -2 -1 0 1
            begin_slot = int(center_slice - number_of_slices / 2)
            end_slot = int(center_slice + number_of_slices / 2 - 1)
        else:
            # 奇数切片   -1 0 1
            begin_slot = int(center_slice - (number_of_slices - 1) / 2)
            end_slot = int(center_slice + (number_of_slices - 1) / 2)
        # print(f'num_device:{num_device}, slot:{begin_slot}-{end_slot}, com_port:{com_port}, switch_port:{switch_port}')
        response = self.wss_spa(num_device, begin_slot, end_slot, com_port, switch_port, att, unitofatt)
        return response


if __name__ == "__main__":
    list_att_initial = np.zeros((2, 2, 20))
    wss = WavelengthSelectiveSwitch('COM5', 'COM6', list_att_initial)
    response = wss.wsspower('on')
    print(f'开机回复：{response}')

    wss.wss_spa(1, 1, 772, 1, 99, 0)
    wss.wss_spa( 2, 1,772, 1, 99, 0)
    # response = wss.wss_spa(1, 1, 772, 1, 16, 10)
    # print(f'设置回复：{response}')
    # response = wss.wss_spa(2, 1, 772, 1, 2, 0)
    # print(f'设置回复：{response}')

    fq = 193.5e12
    fsyn = 193.3e12
    response = wss.wss_spa_bandwidth(2, fq, 25e9, 1, 2, 0)
    print(f'设置回复：{response}')
    response = wss.wss_spa_bandwidth(2, fsyn, 100e9, 1, 2, 0)
    print(f'设置回复：{response}')

    # list_att_initial = np.zeros((2, 2, 20))
    # wss1 = WavelengthSelectiveSwitch('None', 'COM6', list_att_initial) # 没通
    # wss = WavelengthSelectiveSwitch('COM5', 'COM8', list_att_initial)
    # response = wss.wsspower('on')
    # print(f'开机回复：{response}')
    # # response = wss.wss_spa_bandwidth(1, 193.5e12, 25e9, 1, 12, 0)
    # # print(f'设置回复：{response}')
    # #
    # # # 获得指定中心频率和带宽的切片范围
    # # # command = 'SPA 1 1:772,1:2, 0';
    # # # sw_port = 1
    # #
    # # response = wss.wss_spa(1, 1, 772, 1, 1, 0)
    # # print(f'设置回复：{response}')
    # time.sleep(1)
    # response = wss1.wss_spa(1, 1, 772, 1, 99, 0)
    # print(f'设置回复：{response}')
    # # response = wss1.wss_spa(1, 1, 772, 1, 2, 0)
    # # print(f'设置回复：{response}')
    # response = wss1.wss_spa_bandwidth(1, 193.5e12, 25e9, 1, 2, 2.5)
    # print(f'设置回复：{response}')
    # response = wss1.wss_spa_bandwidth(1, 193.3e12, 100e9, 1, 2, 2.5)
    # print(f'设置回复：{response}')
    # #
    # # try:
    # #     s = serial.Serial('COM8', 115200, timeout=2)
    # #     s.write('SPA? 2\r'.encode())
    # #     time.sleep(0.5)
    # #     response = []
    # #     while s.in_waiting > 1:#???  一行数据结束符号？？？数据终止符号？？？
    # #         line = s.read_until(b'\r\n').decode('utf-8').rstrip()#???
    # #         response.append(line)
    # #         print('收到：{}'.format(line))
    # #     print('正常运行')
    # # except Exception as e:
    # #     print(f'无法打开串口 or 无法发送命令：{e}')
    # # finally:
    # #     if s is not None and s.is_open:
    # #         s.close()
    # #         print("-control-串口管理器已关闭串口")