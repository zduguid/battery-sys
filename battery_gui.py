#/usr/bin/env python3
#
# - Assesses state of the battery and displays results
# - Allows for charging and discharging control
#
# Author: Zachary Duguid
# Last Updated: 06/21/2017

import serial
import time
import numpy as np
import matplotlib
from matplotlib import pyplot as plt
import matplotlib.cm as cm
import tkinter
from tkinter import Tk, Label, Button


class Bus(serial.Serial):
    def __init__(self, PORT, BAUD, TIME_OUT, WAIT_TIME):
        serial.Serial.__init__(self, PORT, BAUD, timeout=TIME_OUT)
        self.WAIT_TIME = WAIT_TIME
        self.bat_ques_set = set(['?v', '?i', '?p', '?k', '?c'])
        self.bat_pack_set = set(['#bat1', '#bat2', '#bat3', '#bat4'])

    def send_cmd(self,cmd):
        # INPUT: cmd string with proper battery protocal
        # OUTPUT: tuple of latency string and a list of 10 bat_readings strings in hex format
        # send cmd to bus in ascii format
        self.write(cmd.encode('ascii'))
        hex_len = 4         # length of each hex message
        hex_base = 16       # base of hex unit
        ques_len = 2        # length of diagnostic message (not including battery address)
        etx_len = 3
        max_bat_num = 10    # maximum number of batteries on a given battery pack

        # allow bus to gather response
        time.sleep(self.WAIT_TIME)

        #extract full message
        msg = ''
        while self.inWaiting() > 0:
            try:
                msg += self.read(1).decode('utf-8')
            except UnicodeDecodeError:
                pass

        # cmd only echoed, no ETX or 'valid command' response from bus, return None
        if len(msg) == len(cmd):
            return(None)

        # cmd is valid, extract latency value and bat_readings if valid question and bat_pack
        elif (msg[len(cmd)-ques_len:len(cmd)] in self.bat_ques_set) and (msg[:len(cmd)-ques_len] in self.bat_pack_set):
            output = msg[len(cmd)+1:-etx_len]
            latency = int(output[:hex_len],hex_base)
            bat_readings = []
            for i in range(1, max_bat_num + 1):
                bat_readings.append(output[i*(hex_len+1):i*(hex_len+1)+hex_len])
            return(latency, bat_readings)

    def get_time(self, bat):
        # returns a time string for specific bat
        time_cmd = bat + '?t'
        self.write(time_cmd.encode('ascii'))
        time.sleep(self.WAIT_TIME)
        msg = ''
        while self.inWaiting() > 0:
            try:
                msg += self.read(1).decode('utf-8')
            except UnicodeDecodeError:
                pass
        return(msg[8:-4])



class BatteryPack(object):
    def __init__(self, name, start_time, SCAN_TIME, num_bat):
        self.name = name
        self.start_time = start_time
        self.start_time_seconds = self.get_time_in_seconds(start_time)
        self.SCAN_TIME = SCAN_TIME
        self.num_bat = num_bat
        # maintain current and voltage data in nested list format
        self.pack_data = [[[],[]] for i in range(num_bat)]
        # maintain aggregate current in list format
        self.current_sum = []
        # maintain time indices in list format
        self.time = []

    def get_pack_data(self):
        # deep copy to avoid aliasing
        return [element[:] for element in self.pack_data]

    def get_time_in_seconds(self, time_string):
        # time_string in 'dddd hh:mm:ss' format
        s_in_m = 60
        s_in_h = 3600
        s_in_d = 86400
        d = int(time_string[0:4])
        h = int(time_string[5:7])
        m = int(time_string[8:10])
        s = int(time_string[11:13])
        return(s + m*s_in_m + h*s_in_h + d*s_in_d)



class PowerSupply(object):
    def __init__(self, NAME, V_GAIN, V_OFFSET, I_GAIN, I_OFFSET):
        self.name = NAME
        self.v_gain = V_GAIN
        self.v_offset = V_OFFSET
        self.i_gain = I_GAIN
        self.i_offset = I_OFFSET
        self.max_voltage = 15           # conservative value for now
        self.max_current = 0.5          # conservative value for now

    def set_voltage(self, target_voltage, bus):
        # assert that voltage is under the maximum voltage
        if target_voltage <= self.max_voltage:
            input_val = int((target_voltage - self.v_offset)/self.v_gain)
        else:
            input_val = int((self.max_voltage - self.v_offset)/self.v_gain)

        # convert target value to hex command and send via the bus
        input_cmd = '{0:x}'.format(input_val)
        voltage_channel = '!a1.'
        execute = 'x'
        bus.send_cmd(self.name + voltage_channel + str(input_cmd) + execute)

    def set_current(self, target_current, bus):
        # assert that current is under the maximum current
        if target_current <= self.max_current:
            input_val = int((target_current - self.i_offset)/self.i_gain)
        else:
            input_val = int((self.max_current - self.i_offset)/self.i_gain)

        # convert target value to hex command and send via the bus
        input_cmd = '{0:x}'.format(input_val)
        current_channel = '!a2.'
        execute = 'x'
        bus.send_cmd(self.name + current_channel + str(input_cmd) + execute)

    def turn_on_load(self, bus):            #FIXME -- add this function
        pass

    def turn_off_load(self, bus):           #FIXME -- add this function
        pass



if __name__ == "__main__":
    # Bus Parameters
    # PORT = '/dev/cu.usbserial'
    PORT = '/dev/ttyUSB0'
    BAUD = 9600
    TIME_OUT = 1
    SCAN_TIME = 5
    WAIT_TIME = 0.1

    # Battery Pack Parameters
    BAT_LIST = ['#bat1']                    #FIXME -- add new battery pack condtions:   ['#bat1','#bat2','#bat3','#bat4']
    DIAGNOSTIC_CMDS = ['?v','?i']           #FIXME -- add new diagnostic conditions:    ['?v','?i','?p','?k','?c']
    v_index = 0                 # voltage index in BAT#.pack_data
    i_index = 1                 # current index in BAT#.pack_data
    current_threshold = 32000   # used for detecting negative current
    current_adjust = 65536      # used for adjusting negative current
    hex_base = 16               # used in hex -> dec conversion
    bat_pack_count = {'#bat1':2}            #FIXME -- add new battery pack count numbers

    # Power Supply Parameters
    # (max_voltage and max_current can be adjusted within the PowerSupply class)
    VOLTAGE = 15
    CURRENT = 1.5
    PWR_NAME = '#ada'
    V_GAIN = 0.00078141
    V_OFFSET = -0.053842
    I_GAIN = 0.00020677
    I_OFFSET = 0.014475

    # Graphing Parameters
    GRAPH_ON = True
    COLOR_MAP = 'gist_ncar'
    AGGREGATE_CURRENT_ON = True
    LEGEND_ON = True


    # Initializing Bus and PowerSupply objects, set Voltage/Current settings
    bus = Bus(PORT, BAUD, TIME_OUT, WAIT_TIME)
    pwr_supply = PowerSupply(PWR_NAME, V_GAIN, V_OFFSET, I_GAIN, I_OFFSET)
    # pwr_supply.set_voltage(VOLTAGE, bus)
    # pwr_supply.set_current(CURRENT, bus)

    # Initialize desired scan frequency and initialize BatteryPack object(s)
    for bat in BAT_LIST:
        scan_cmd = bat + '!s' + '{0:x}'.format(int(SCAN_TIME)) + '_'
        bus.send_cmd(scan_cmd)
        start_time = bus.get_time(bat)

        if bat == '#bat1':                  #FIXME -- add new battery pack condtions
            num_bat = bat_pack_count[bat]
            bat1 = BatteryPack(bat, start_time, SCAN_TIME, num_bat)

    if GRAPH_ON:
        # Initialize the graph
        NUM_COLORS = bat1.num_bat

        if AGGREGATE_CURRENT_ON:
            fig, (ax0, ax1, ax2) = plt.subplots(nrows=3)
            ax0.set_title('Battery Voltage Over Time (mV)')
            ax0.set_ylabel('Voltage (mV)')
            ax1.set_title('Battery Current Over Time (mA)')
            ax1.set_ylabel('Current (mA)')
            ax2.set_title('Aggregate Current Over Time (mA)')
            ax2.set_ylabel('Current (mA)')
            ax2.set_xlabel('Time (s)')
            ax2.grid()
        else:
            fig, (ax0, ax1) = plt.subplots(nrows=2)
            ax0.set_title('Battery Voltage Over Time (mV)')
            ax0.set_ylabel('Voltage (mV)')
            ax1.set_title('Battery Current Over Time (mA)')
            ax1.set_ylabel('Current (mA)')
            ax1.set_xlabel('Time (s)')

        plt.rc('lines', linewidth=1)
        plt.tight_layout()
        ax0.grid()
        ax1.grid()
        legend_list = ['bat' + str(item+1) for item in range(NUM_COLORS)]

        cm = plt.get_cmap(COLOR_MAP)
        color_list = [matplotlib.colors.rgb2hex(cm(1.*i/NUM_COLORS)[:3]) for i in range(NUM_COLORS)]

    while(True):
        time.sleep(SCAN_TIME-1)

        for bat in BAT_LIST:
            for cmd in DIAGNOSTIC_CMDS:
                try:
                    # add battery readings to pack data and assert that data is of the same length
                    latency, bat_readings = bus.send_cmd(bat+cmd)
                    bat_readings_dec = [int(element,hex_base) for element in bat_readings if element!='']

                    if bat == '#bat1':      #FIXME -- add new battery pack condtions
                        if cmd == '?v':     #FIXME -- add new diagnostic conditions
                            for j in range(bat1.num_bat):
                                bat1.pack_data[j][v_index].append(bat_readings_dec[j])

                        elif cmd == '?i':
                            current_sum = 0

                            for j in range(bat1.num_bat):
                                if bat_readings_dec[j] > current_threshold:
                                    bat_readings_dec[j] = bat_readings_dec[j] - current_adjust

                                if (len(bat1.pack_data[j][v_index]) - 1) == len(bat1.pack_data[j][i_index]):
                                    bat1.pack_data[j][i_index].append(bat_readings_dec[j])
                                    current_sum += bat_readings_dec[j]

                            if (len(bat1.pack_data[j][v_index]) - 1) == len(bat1.current_sum):
                                bat1.current_sum.append(current_sum)

                except TypeError:
                    pass

        # assert that data is of the same length
        if len(bat1.time) == len(bat1.pack_data[0][0])-1:
            bat1.time.append(bat1.get_time_in_seconds(bus.get_time(bat1.name)) - bat1.start_time_seconds)

        if GRAPH_ON:
            for i in range(NUM_COLORS):
                ax0.plot(bat1.time, bat1.pack_data[i][0], color_list[i])
                plt.pause(WAIT_TIME)
                ax1.plot(bat1.time, bat1.pack_data[i][1], color_list[i])
                plt.pause(WAIT_TIME)
            if AGGREGATE_CURRENT_ON:
                ax2.plot(bat1.time, bat1.current_sum, 'r')
                plt.pause(WAIT_TIME)
            if LEGEND_ON:
                ax1.legend(legend_list, loc='center left', bbox_to_anchor=(0, 1.25), ncol=NUM_COLORS, framealpha=1)
