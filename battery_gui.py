# /usr/bin/env python3
#
# - GUI Interface that communicates with the Slocum Glider battery pack system via serial port
# - Allows for graphical and terminal displays of the battery state 
# - Allows for charging and discharging control of the battery pack
# 
# Author: Zach Duguid
# Last Updated: 07/13/2017


import serial
import time
import datetime
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
from matplotlib import pyplot as plt
import matplotlib.cm as cm
import tkinter as tk
from tkinter import messagebox 
import tkinter.font as tkFont
import sys
import glob
import warnings



#############################################################
# SERIAL BUS ################################################
#############################################################
class Bus(serial.Serial):
    def __init__(self, port, baud, time_out, wait_time):
        ''' initialize serial bus object and define valid ques/pack names 
        '''
        serial.Serial.__init__(self, port, baud, timeout=time_out)
        self.wait_time = wait_time                                      # short interval required to recieve battery message
        self.bat_ques_set = set(['?v', '?i', '?p', '?k', 'q', '?c'])    # valid questions
        self.bat_pack_set = set(['#bat1', '#bat2', '#bat3', '#bat4'])   # valid battery pack names


    def send_cmd(self,cmd):
        ''' encodes and sends message (cmd) to Serial Bus
            :raises UnicodeDecodeError:
                when battery response cannot be decoded
            :returns:
                latency and battery readings when a valid ques is sent to a valid battery pack
        '''
        self.write(cmd.encode('ascii')) # send command
        hex_len = 4                     # length of each hex message
        hex_base = 16                   # base of hex system
        ques_len = 2                    # length of battery question (i.e. ?v)
        etx_len = 3                     # length of battery response indicator (i.e. ETX)
        max_bat_num = 10                # maximum number of batteries on a given battery pack

        # allow bus to gather response
        time.sleep(self.wait_time)

        # extract full message
        msg = ''
        while self.inWaiting() > 0:
            # account for the rare instance when a character is unsuccessfully decoded
            try:
                msg += self.read(1).decode('utf-8') 
            except UnicodeDecodeError:
                pass

        # battery response not recieved
        if len(msg) == len(cmd):
            return(None)

        # battery response recieved, extract battery data if a valid ques is sent to a valid battery pack
        elif (msg[len(cmd)-ques_len:len(cmd)] in self.bat_ques_set) and (msg[:len(cmd)-ques_len] in self.bat_pack_set):

            # retrieve battery information in hex format
            bat_readings = [msg[len(cmd)+1:-etx_len][i*(hex_len+1):i*(hex_len+1)+hex_len] for i in range(1, max_bat_num + 1)]

            # retrieve latency information in integer format
            latency = int(msg[len(cmd)+1:-etx_len][:hex_len],hex_base)

            return(latency, bat_readings)



#############################################################
# POWER SUPPLY ##############################################
#############################################################
class PowerSupply(object):
    def __init__(self, name, v_gain, v_offset, i_gain, i_offset):
        ''' initialize power supply object and define maximum current and voltage outputs
        '''
        self.name = name                # name of the power supply channel (i.e. #ada)
        self.v_gain = v_gain            # voltage gain of the power supply 
        self.v_offset = v_offset        # voltage offset of the power supply
        self.i_gain = i_gain            # current gain of the power supply
        self.i_offset = i_offset        # current offset of the power supply
        self.max_voltage = 16           # conservative value for now
        self.max_current = 1            # conservative value for now
        self.voltage_channel = '!a1.'   # name of voltage channel
        self.current_channel = '!a2.'   # name of current channel
        self.execute_str = 'x'          # syntax for the termination of a command
        self.load1_channel = '!p2'      # name of load1 channel 
        self.load2_channel = '!p3'      # name of load2 channel
        self.on_signal_str = '+x'       # syntax for turning load channel on
        self.off_signal_str = '-x'      # syntax for turning load channel off
        self.hex_base = 16              # used in hex -> dec conversion


    def set_voltage(self, target_voltage, bus):
        ''' command power supply to target voltage, subject to maximum voltage limitation
        '''
        if target_voltage <= self.max_voltage:
            input_val = int((target_voltage - self.v_offset)/self.v_gain)
        else:
            input_val = int((self.max_voltage - self.v_offset)/self.v_gain)

        # convert interger command to hex command 
        input_cmd = '{0:x}'.format(input_val)

        # convert to a positive hex command if command is input_cmd is negative
        if int(input_cmd) < 0: 
            input_cmd = '{0:x}'.format(int('ffffffff', self.hex_base) + int(input_cmd) +1)

        # send voltage command to the power supply via the serial bus
        bus.send_cmd(self.name + self.voltage_channel + str(input_cmd) + self.execute_str)


    def set_current(self, target_current, bus):
        ''' command power supply to target current, subject to maximum current limitation
        '''
        if target_current <= self.max_current:
            input_val = int((target_current - self.i_offset)/self.i_gain)
        else:
            input_val = int((self.max_current - self.i_offset)/self.i_gain)

        # convert interger command to hex command 
        input_cmd = '{0:x}'.format(input_val)

        # convert to a positive hex command if command is input_cmd is negative
        if int(input_cmd) < 0: 
            input_cmd = '{0:x}'.format(int('ffffffff', self.hex_base) + int(input_cmd) +1)

        # send current command to the power supply via the serial bus
        bus.send_cmd(self.name + self.current_channel + str(input_cmd) + self.execute_str)


    def set_load(self, load1, load2, bus):
        ''' command load(s) on/off (i.e. resistor loads used to discharge batteries)
        '''
        if load1 == 0:
            bus.send_cmd(self.name + self.load1_channel + self.off_signal_str)
        else:
            bus.send_cmd(self.name + self.load1_channel + self.on_signal_str)
        if load2 == 0:
            bus.send_cmd(self.name + self.load2_channel + self.off_signal_str)
        else:
            bus.send_cmd(self.name + self.load2_channel + self.on_signal_str)



#############################################################
# GUI  ######################################################
#############################################################
class GUI(object):
    def __init__(self, master):
        ''' initialize GUI object, define custom GUI parameters and nomenclature, initialize GUI frames
        '''
        self.master = master
        master.title('Slocum Glider Battery System Tool')
        self.bus_connected = False
        self.scan_time = None 

        # custom GUI parameters (i.e. font styles, GUI colors, etc.)
        self.frame_font = tkFont.Font(family='Helvetica', size=16, weight='bold', slant='italic', underline=1)
        self.label_font = tkFont.Font(family='Helvetica', size=10)
        self.label_font_italic = tkFont.Font(family='Helvetica', size=10, slant='italic')
        self.label_font_bold = tkFont.Font(family='Helvetica', size=10, weight='bold')
        self.pad = 5
        self.light_grey = '#ddd'
        self.dark_grey = '#ccc'
        self.pwr_off_color = 'red'
        self.connect_color = 'blue'
        self.relief_style = 'ridge'
        self.graph_title = 'Slocum Glider Battery System Graph'
        self.current_threshold = 32000      # used for detecting negative current
        self.current_adjust = 65536         # used for adjusting negative current
        self.hex_base = 16                  # used in hex -> dec conversion
        self.color_map = 'gist_ncar'        # used for establishing the graph colors 

        # battery pack information and nomenclature
        self.list_pack_names = ['Pack 1', 'Pack 2', 'Pack 3', 'Pack 4']
        self.dict_pack_to_nums = {'Pack 1':8, 'Pack 2':10, 'Pack 3':9, 'Pack 4':10}
        self.dict_pack_to_name = {'Pack 1':'payload pack', 'Pack 2':'aft-long pack', 'Pack 3':'aft-short pack', 'Pack 4':'pitch pack'}
        self.dict_code_to_pack = {'#bat1':'Pack 1', '#bat2':'Pack 2', '#bat3':'Pack 3', '#bat4':'Pack 4'}
        self.dict_pack_to_code = {'Pack 1':'#bat1', 'Pack 2':'#bat2', 'Pack 3':'#bat3', 'Pack 4':'#bat4'}
        self.dict_pack_to_bat = {}
        self.dict_bat_to_code = {}
        self.dict_bat_to_packindex = {}
        self.total_bat_count = 0
        
        for name in self.list_pack_names:
            self.dict_pack_to_bat[name] = []
            for i in range(1, self.dict_pack_to_nums[name]+1):
                self.total_bat_count += 1
                self.dict_pack_to_bat[name].append('B'+str(self.total_bat_count))
                self.dict_bat_to_code['B'+str(self.total_bat_count)] = self.dict_pack_to_code[name]
                self.dict_bat_to_packindex['B'+str(self.total_bat_count)] = i-1

        self.dict_axis_info = {'?v'   : 'Voltage (mV)',
                               '?i'   : 'Current (mA)',
                               '?ai'  : 'Aggregate Current (mA)',
                               '?p'   : 'Percent Charge (%)',
                               '?k'   : 'Temperature (C)',
                               '?q'   : 'Charge State (mAhrs)',
                               '?c'   : 'Desired Charge (mA)',
                               'time' : 'Time'}

        # initialize main container
        self.frame_master = tk.Frame(master, bg='bisque')
        self.frame_master.grid(row=0, column=0, sticky='nsew')
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

        # initialize different GUI groups
        self.init_frame_containers()    # frames within main container
        self.init_pwr_group()           # power supply commands
        self.init_bat_group()           # batter pack commands 
        self.init_gra_group()           # graphical commands
        self.init_trm_group()           # terminal commands
        self.init_bot_group()           # bottom frame commands


    def get_serial_ports(self):
        """ Lists serial port names
            :raises EnvironmentError:
                On unsupported or unknown platforms
            :returns:
                A list of the serial ports available on the system
        """
        if sys.platform.startswith('win'):
            ports = ['COM%s' % (i + 1) for i in range(256)]

        # check raspberry pi serial ports
        elif sys.platform.startswith('linux'): 
            ports = glob.glob('/dev/tty*')

        # check macbook serial ports
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/cu.*')

        else:
            raise EnvironmentError('Unsupported platform')

        result = []
        for port in ports:
            try:
                s = serial.Serial(port)
                s.close()
                result.append(port)
            except(OSError, serial.SerialException):
                pass
        return(result)



    #############################################################
    # CALLBACK FUNCTIONS  #######################################
    #############################################################
    def callback_pwr_ex(self):
        ''' command the power supply off
            :raises error message:
                if there is not a connection with the serial bus
                if invalid current/voltage command is sent 
        '''
        # check serial bus connection
        if not self.bus_connected:
            messagebox.showerror('ERROR', 'You are not connected to the Serial Bus')

        else:
            # extract user entered parameters 
            desired_voltage = self.entry_pwr_v.get()
            desired_current = self.entry_pwr_i.get()
            load1 = self.var_pwr_l1.get()
            load2 = self.var_pwr_l2.get()

            # confirm correct format of user variables
            try:
                desired_voltage = float(desired_voltage)
                desired_current = float(desired_current)

                # send relevant power supply commands via the serial bus
                self.pwr_supply.set_voltage(desired_voltage, self.bus)
                self.pwr_supply.set_current(desired_current, self.bus)
                self.pwr_supply.set_load(load1, load2, self.bus)
                print('>> Voltage, Current, Load commands sent')

            # display error message if incorrected data format is used
            except ValueError:
                messagebox.showerror('ERROR', 'Invalid Voltage and/or Current Command, please insert a valid number')
                self.entry_pwr_v.delete(0, tk.END)


    def callback_bat_ex(self):
        ''' execute battery pack window commands
            :raises error message:
                if there is not a connection with the serial bus
                if invalid scan command is sent
        '''
        # check serial bus connection
        if not self.bus_connected:
            messagebox.showerror('ERROR', 'You are not connected to the Serial Bus')

        else:
            # extract user entered parameters 
            desired_scan_time = self.entry_bat_scan.get()

            try: 
                # confirm correct format of user variables
                desired_scan_time = float(desired_scan_time)
                desired_scan_time = int(desired_scan_time)

                # set user entered parameter to integer value
                self.entry_bat_scan.delete(0, tk.END)
                self.entry_bat_scan.insert(0, desired_scan_time)

                # display error message if scan time is zero or less 
                if desired_scan_time <= 0:
                    messagebox.showerror('ERROR', 'Invalid Scan Time Command, please insert a valid number')
                    self.entry_bat_scan.delete(0, tk.END)

                else:
                    # send scan time to the batteries via the serial bus
                    self.scan_time = desired_scan_time
                    print('>> Scan time, relay commands sent')

            # display error message if incorrected data format is used      
            except ValueError:
                messagebox.showerror('ERROR', 'Invalid Scan Time Command, please insert a valid number')
                self.entry_bat_scan.delete(0, tk.END)
 

    def callback_gra_ex(self):
        ''' execute graph creation dependent on user inputs
            :raises error message:
                if there is not a connection with the serial bus
                if the user has not specified battery scan time
                if the user has not selected batteries to graph
                if the user has not selected variables to graph
        '''
        # check serial bus connection
        if not self.bus_connected:
            messagebox.showerror('ERROR', 'You are not connected to the Serial Bus')

        # check that scan time has been specified    
        elif self.scan_time == None:
            messagebox.showerror('ERROR', 'Please enter a valid Scan Time in the Battery Pack window')

        # check that batteries to plot have been specified
        elif ((self.var_gra_b1.get() + 
               self.var_gra_b2.get() + 
               self.var_gra_b3.get() + 
               self.var_gra_b4.get()) ==0):
            messagebox.showerror('ERROR', 'Please select one or more batteries to graph')

        # check that variables to plot have been specified
        elif ((self.var_gra_v.get() + 
               self.var_gra_i.get() + 
               self.var_gra_ai.get() + 
               self.var_gra_p.get() +
               self.var_gra_k.get() + 
               self.var_gra_q.get() +
               self.var_gra_c.get()) == 0):
            messagebox.showerror('ERROR', 'Please select one or more variables to graph')

        else:
            # begin the graphing process 
            print('>> New graph created')

            # initialize graph specific parameters
            bat_list = []
            var_list = []
            pack_data = {}

            # determine battery and question commands to send to the batteries via the serial bus
            if self.var_gra_b1.get() == 1:
                bat_list.append('#bat1')

            if self.var_gra_b2.get() == 1:
                bat_list.append('#bat2')

            if self.var_gra_b3.get() == 1:
                bat_list.append('#bat3')

            if self.var_gra_b4.get() == 1:
                bat_list.append('#bat4')

            if self.var_gra_v.get() == 1:
                var_list.append('?v')

            if self.var_gra_ai.get() == 1:
                var_list.append('?i')
                var_list.append('?ai')
                self.var_gra_i.set(1)

            if self.var_gra_i.get() == 1:
                if '?i' not in var_list:
                    var_list.append('?i')

            if self.var_gra_p.get() == 1:
                var_list.append('?p')

            if self.var_gra_k.get() == 1:
                var_list.append('?k')

            if self.var_gra_q.get() == 1:
                var_list.append('?q')

            if self.var_gra_c.get() == 1:
                var_list.append('?c')

            # determine the appropriate legend(s) for the user specified graph
            legend_list_ai = [self.dict_code_to_pack[code] for code in bat_list]
            legend_list = []
            for bat in bat_list:
                legend_list.extend(self.dict_pack_to_bat[self.dict_code_to_pack[bat]])

            # configure battery scan time and initialize pack_data variable
            for bat in bat_list:

                # determine scan command
                scan_cmd = bat + '!s' + '{0:x}'.format(self.scan_time) + '_'

                # send scan command to each battery via the serial bus
                self.bus.send_cmd(scan_cmd)

                # initialize pack_data variable
                pack_data[bat] = {}
                pack_data[bat]['time'] = []
                for var in var_list:
                    if var == '?ai':
                        pack_data[bat][var] = []
                    else:
                        pack_data[bat][var] = [[] for i in range(self.dict_pack_to_nums[self.dict_code_to_pack[bat]])]

            # initialize figure for plotting
            fig, ax = plt.subplots(nrows=len(var_list))
            
            # set plot labels for when one variable is selected
            if len(var_list) == 1:
                ax.set_title(self.graph_title)
                ax.set_ylabel(self.dict_axis_info[var_list[0]])
                ax.set_xlabel(self.dict_axis_info['time'])
                ax.legend(legend_list)
                plt.rc('lines', linewidth=1)
                plt.tight_layout()
                ax.grid()

            # set plot labels for when more than one variable is selected
            else:
                ax[0].set_title(self.graph_title)
                for i in range(len(var_list)):
                    ax[i].set_ylabel(self.dict_axis_info[var_list[i]])
                    ax[i].set_xlabel(self.dict_axis_info['time'])
                    plt.rc('lines', linewidth=1)
                    plt.tight_layout()
                    ax[i].grid()

            # specficy graphing parameters (i.e. text display, colors, etc.)
            plt.gcf().autofmt_xdate()
            num_colors = sum([self.dict_pack_to_nums[self.dict_code_to_pack[bat]] for bat in bat_list])
            cm = plt.get_cmap(self.color_map)
            color_list = [matplotlib.colors.rgb2hex(cm(1.*i/num_colors)[:3]) for i in range(num_colors)]
            color_list_ai = [matplotlib.colors.rgb2hex(cm(1.*i/len(bat_list))[:3]) for i in range(len(bat_list))]

            # enter infinite loop
            while(True):

                # pause to allow batteries to acquire new scan data
                time.sleep(self.scan_time)

                # interate through the batteries to be questioned
                for bat in bat_list:

                    # extract the current UTC time
                    pack_data[bat]['time'].append(datetime.datetime.utcnow())

                    # iterate through the variables to be questioned
                    for var in var_list:

                        # extract latency and bat_readings data (when aggregate current not requested)
                        if var != '?ai':
                            latency, bat_readings = self.bus.send_cmd(bat+var)

                            # decode the bat_readings data into integer format
                            bat_readings_int = [int(element,self.hex_base) for element in bat_readings if element!='']

                            # convert temperature data from K*10 -> C as necessary
                            if var == '?k':
                                bat_readings_int = [reading/10 - 273.15 for reading in bat_readings_int]

                            # convert current data to negative values as necessary (negative indicates battery discharge) 
                            elif var == '?i':
                                bat_readings_int = [reading - self.current_adjust if reading > self.current_threshold else reading for reading in bat_readings_int]

                            # add converted bat_reading_int data to pack_data variable
                            for i in range(self.dict_pack_to_nums[self.dict_code_to_pack[bat]]):
                                pack_data[bat][var][i].append(bat_readings_int[i])

                        # if aggregate current is requested, sum over the current readings of the individual batteries, then add to pack_data
                        else:
                            pack_data[bat][var].append(sum([pack_data[bat]['?i'][bat_num][-1] for bat_num in range(len(pack_data[bat]['?i']))]))

                # plotting process for when one variable is selected
                if len(var_list) == 1:
                    for i in range(len(legend_list)):

                        # identify the current battery
                        cur_bat = legend_list[i]
                        ax.plot(pack_data[self.dict_bat_to_code[cur_bat]]['time'], 
                                pack_data[self.dict_bat_to_code[cur_bat]][var_list[0]][self.dict_bat_to_packindex[cur_bat]],
                                color_list[i])

                # plotting process for when more than one variable is selected
                else:
                    for v in range(len(var_list)):

                        # plotting behavior for non-aggregate-current variables
                        if var_list[v] != '?ai':
                            for i in range(len(legend_list)):

                                # identify the current battery
                                cur_bat = legend_list[i]
                                ax[v].plot(pack_data[self.dict_bat_to_code[cur_bat]]['time'], 
                                           pack_data[self.dict_bat_to_code[cur_bat]][var_list[v]][self.dict_bat_to_packindex[cur_bat]],
                                           color_list[i])

                        # plotting behavior for aggregate current behavior
                        else:
                            for i in range(len(bat_list)):
                                ax[v].plot(pack_data[bat_list[i]]['time'],
                                           pack_data[bat_list[i]]['?ai'],
                                           color_list_ai[i])

                # pause plot in order for new data to update
                plt.pause(self.bus.wait_time)


    def callback_trm_ex(self):
        ''' execute terminal plotting creation dependent on user inputs
            :raises error message:
                if there is not a connection with the serial bus
                if the user has not specified battery scan time
                if the user has not selected batteries to graph
                if the user has not selected variables to graph
        '''
        # check serial bus connection
        if not self.bus_connected:
            messagebox.showerror('ERROR', 'You are not connected to the Serial Bus')

        # check that scan time has been specified    
        elif self.scan_time == None:
            messagebox.showerror('ERROR', 'Please enter a valid Scan Time in the Battery Pack window')

        # check that batteries to plot have been specified
        elif ((self.var_trm_b1.get() + 
               self.var_trm_b2.get() + 
               self.var_trm_b3.get() + 
               self.var_trm_b4.get()) ==0):
            messagebox.showerror('ERROR', 'Please select one or more batteries to graph')

        # check that variables to plot have been specified
        elif ((self.var_trm_v.get() + 
               self.var_trm_i.get() + 
               self.var_trm_ai.get() + 
               self.var_trm_p.get() +
               self.var_trm_k.get() + 
               self.var_trm_q.get() +
               self.var_trm_c.get()) == 0):
            messagebox.showerror('ERROR', 'Please select one or more variables to graph')

        else:
            # begin the graphing process 
            print('>> New terminal plot created')

            # initialize graph specific parameters
            bat_list = []
            var_list = []
            pack_data = {}

            # determine battery and question commands to send to the batteries via the serial bus
            if self.var_trm_b1.get() == 1:
                bat_list.append('#bat1')

            if self.var_trm_b2.get() == 1:
                bat_list.append('#bat2')

            if self.var_trm_b3.get() == 1:
                bat_list.append('#bat3')

            if self.var_trm_b4.get() == 1:
                bat_list.append('#bat4')

            if self.var_trm_v.get() == 1:
                var_list.append('?v')

            if self.var_trm_ai.get() == 1:
                var_list.append('?i')
                var_list.append('?ai')
                self.var_gra_i.set(1)

            if self.var_trm_i.get() == 1:
                if '?i' not in var_list:
                    var_list.append('?i')

            if self.var_trm_p.get() == 1:
                var_list.append('?p')

            if self.var_trm_k.get() == 1:
                var_list.append('?k')

            if self.var_trm_q.get() == 1:
                var_list.append('?q')

            if self.var_trm_c.get() == 1:
                var_list.append('?c')

            # determine the appropriate legend(s) for the user specified graph
            legend_list_ai = [self.dict_code_to_pack[code] for code in bat_list]
            legend_list = []
            for bat in bat_list:
                legend_list.extend(self.dict_pack_to_bat[self.dict_code_to_pack[bat]])

            # configure battery scan time and initialize pack_data variable
            for bat in bat_list:

                # determine scan command
                scan_cmd = bat + '!s' + '{0:x}'.format(self.scan_time) + '_'

                # send scan command to each battery via the serial bus
                self.bus.send_cmd(scan_cmd)

                # initialize pack_data variable
                pack_data[bat] = {}
                pack_data[bat]['time'] = []
                for var in var_list:
                    if var == '?ai':
                        pack_data[bat][var] = []
                    else:
                        pack_data[bat][var] = [[] for i in range(self.dict_pack_to_nums[self.dict_code_to_pack[bat]])]

            # enter infinite loop
            while(True):

                # pause to allow batteries to acquire new scan data
                time.sleep(self.scan_time)

                print('\n')
                # display the current UTC time
                print('- Time: '+ str(datetime.datetime.utcnow()))

                # interate through the batteries to be questioned
                for bat in bat_list:

                    # extract the current UTC time
                    pack_data[bat]['time'].append(datetime.datetime.utcnow())

                    # iterate through the variables to be questioned
                    for var in var_list:

                        # extract latency and bat_readings data (when aggregate current not requested)
                        if var != '?ai':
                            latency, bat_readings = self.bus.send_cmd(bat+var)

                            # decode the bat_readings data into integer format
                            bat_readings_int = [int(element,self.hex_base) for element in bat_readings if element!='']

                            # convert temperature data from K*10 -> C as necessary
                            if var == '?k':
                                bat_readings_int = [int(reading/10 - 273.15) for reading in bat_readings_int]

                            # convert current data to negative values as necessary (negative indicates battery discharge) 
                            elif var == '?i':
                                bat_readings_int = [reading - self.current_adjust if reading > self.current_threshold else reading for reading in bat_readings_int]

                            # add converted bat_reading_int data to pack_data variable
                            for i in range(self.dict_pack_to_nums[self.dict_code_to_pack[bat]]):
                                pack_data[bat][var][i].append(bat_readings_int[i])

                            # print relevant data 
                            print('-', self.dict_code_to_pack[bat], self.dict_axis_info[var], [bat_readings_int[i] for i in range(self.dict_pack_to_nums[self.dict_code_to_pack[bat]])])

                        # if aggregate current is requested, sum over the current readings of the individual batteries, then add to pack_data
                        else:
                            pack_data[bat][var].append(sum([pack_data[bat]['?i'][bat_num][-1] for bat_num in range(len(pack_data[bat]['?i']))]))
                            print('-', self.dict_code_to_pack[bat], self.dict_axis_info[var], pack_data[bat][var][-1])


    def callback_POWER_OFF(self):
        ''' commands power supply to zero voltage, zero current, and both loads off
            :raises error message:
                if there is not a connection with the serial bus
        '''
        # check serial bus connection
        if not self.bus_connected:
            messagebox.showerror('ERROR', 'You are not connected to the Serial Bus')

        # send relevant commands to the powersupply 
        else:
            desired_current = 0
            desired_voltage = 0 
            load1 = 0
            load2 = 0
            self.pwr_supply.set_voltage(desired_voltage, self.bus)
            self.pwr_supply.set_current(desired_current, self.bus)
            self.pwr_supply.set_load(load1, load2, self.bus) 
            print('>> POWER OFF command sent')


    def callback_connect(self):
        ''' connects to serial port and initializes serial bus object
            :raises error message:
                if no serial ports are avaible (either macbook of raspi port)
        '''
        # look for available serial ports 
        available_ports = self.get_serial_ports()

        # custom serial vus parameters
        mac_port = '/dev/cu.usbserial'
        pi_port = '/dev/ttyUSB0'
        baud = 9600
        time_out = 1
        wait_time = 0.1
        
        # custom power supply parameters 
        pwr_name = '#ada'
        v_gain = 0.00078141
        v_offset = -0.053842
        i_gain = 0.00020677
        i_offset = 0.014475

        # macbook serial port available
        if mac_port in available_ports:
            print('>> Connecting to serial port:', mac_port)
            self.bus = Bus(mac_port, baud, time_out, wait_time)
            self.pwr_supply = PowerSupply(pwr_name, v_gain, v_offset, i_gain, i_offset)
            self.bus_connected = True

        # raspberry pi serial port available 
        elif pi_port in available_ports:
            print('>> Connecting to serial port:', pi_port)
            self.bus = Bus(pi_port, baud, time_out, wait_time)
            self.pwr_supply = PowerSupply(pwr_name, v_gain, v_offset, i_gain, i_offset)
            self.bus_connected = True

        # no serial port is available 
        else:
            self.bus_connected = False
            messagebox.showerror("ERROR", "Serial Bus not available")


    def init_frame_containers(self):
        #############################################################
        # MAIN WINDOW CONTAINER #####################################
        #############################################################
        self.frame_main_pwr = tk.Frame(self.frame_master, bg=self.light_grey, bd=self.pad, relief=self.relief_style)
        self.frame_main_bat = tk.Frame(self.frame_master, bg=self.light_grey, bd=self.pad, relief=self.relief_style)
        self.frame_main_gra = tk.Frame(self.frame_master, bg=self.light_grey, bd=self.pad, relief=self.relief_style)
        self.frame_main_trm = tk.Frame(self.frame_master, bg=self.light_grey, bd=self.pad, relief=self.relief_style)
        self.frame_main_bot = tk.Frame(self.frame_master, bg=self.light_grey, bd=self.pad, relief=self.relief_style)

        self.frame_main_pwr.grid(row=0, column=0, ipadx=self.pad, ipady=self.pad, sticky='nsew')
        self.frame_main_bat.grid(row=0, column=1, ipadx=self.pad, ipady=self.pad, sticky='nsew')
        self.frame_main_gra.grid(row=1, column=0, ipadx=self.pad, ipady=self.pad, sticky='nsew')
        self.frame_main_trm.grid(row=1, column=1, ipadx=self.pad, ipady=self.pad, sticky='nsew')
        self.frame_main_bot.grid(row=2, column=0, ipadx=self.pad, ipady=self.pad, sticky='nsew', columnspan=2)


    def init_pwr_group(self):
        #############################################################
        # POWER SUPPLY CONTAINER ####################################
        #############################################################
        self.label_pwr_title = tk.Label(self.frame_main_pwr, text='Power Supply', font=self.frame_font, bg=self.light_grey)
        self.label_pwr_v = tk.Label(self.frame_main_pwr, text='Voltage:', font=self.label_font_bold, bg=self.light_grey)
        self.label_pwr_i = tk.Label(self.frame_main_pwr, text='Current:', font=self.label_font_bold, bg=self.light_grey)
        self.label_pwr_v2 = tk.Label(self.frame_main_pwr, text='(V)', font=self.label_font, bg=self.light_grey)
        self.label_pwr_i2 = tk.Label(self.frame_main_pwr, text='(A)', font=self.label_font, bg=self.light_grey)
        self.label_pwr_l1 = tk.Label(self.frame_main_pwr, text='Load 1:', font=self.label_font_bold, bg=self.light_grey)
        self.label_pwr_l2 = tk.Label(self.frame_main_pwr, text='Load 2:', font=self.label_font_bold, bg=self.light_grey)
        self.entry_pwr_v = tk.Entry(self.frame_main_pwr, highlightbackground=self.light_grey)
        self.entry_pwr_v.insert(0,0.0)
        self.entry_pwr_i = tk.Entry(self.frame_main_pwr, highlightbackground=self.light_grey)
        self.entry_pwr_i.insert(0,0.0)
        self.var_pwr_l1 = tk.IntVar()
        self.var_pwr_l2 = tk.IntVar()
        self.checkbut_pwr_l1 = tk.Checkbutton(self.frame_main_pwr, bg=self.light_grey, variable=self.var_pwr_l1)
        self.checkbut_pwr_l2 = tk.Checkbutton(self.frame_main_pwr, bg=self.light_grey, variable=self.var_pwr_l2)
        self.but_pwr_ex = tk.Button(self.frame_main_pwr, text="EXECUTE", highlightbackground=self.light_grey, command=self.callback_pwr_ex)

        self.label_pwr_title.grid(row=0, columnspan=1, column=0, sticky='nsew')
        self.label_pwr_v.grid(row=1, column=0, sticky='e')
        self.label_pwr_i.grid(row=2, column=0, sticky='e')
        self.label_pwr_v2.grid(row=1, column=2, sticky='w')
        self.label_pwr_i2.grid(row=2, column=2, sticky='w')
        self.label_pwr_l1.grid(row=3, column=0, sticky='e')
        self.label_pwr_l2.grid(row=4, column=0, sticky='e')
        self.entry_pwr_v.grid(row=1, column=1, sticky='nsew')
        self.entry_pwr_i.grid(row=2, column=1, sticky='nsew')
        self.checkbut_pwr_l1.grid(row=3,column=1, sticky='w')
        self.checkbut_pwr_l2.grid(row=4,column=1, sticky='w')
        self.but_pwr_ex.grid(row=5, column=3, sticky='e')


    def init_bat_group(self):
        #############################################################
        # BATTERY PACK CONTAINER ####################################
        #############################################################
        self.label_bat_title = tk.Label(self.frame_main_bat, text='Batter Pack',   font=self.frame_font, bg=self.light_grey)
        self.label_bat_scan = tk.Label(self.frame_main_bat, text='Scan Time:',    font=self.label_font_bold, bg=self.light_grey)
        self.label_bat_scan2 = tk.Label(self.frame_main_bat, text='(s)',           font=self.label_font, bg=self.light_grey)
        self.label_bat_relay = tk.Label(self.frame_main_bat, text='Relays On:', font=self.label_font_bold, bg=self.light_grey)
        self.label_bat_bat1 = tk.Label(self.frame_main_bat, text='(payload)', font=self.label_font_italic, bg=self.light_grey)
        self.label_bat_bat2 = tk.Label(self.frame_main_bat, text='(aft-long)', font=self.label_font_italic, bg=self.light_grey)
        self.label_bat_bat3 = tk.Label(self.frame_main_bat, text='(aft-short)', font=self.label_font_italic, bg=self.light_grey)
        self.label_bat_bat4 = tk.Label(self.frame_main_bat, text='(pitch pack)', font=self.label_font_italic, bg=self.light_grey)
        self.entry_bat_scan = tk.Entry(self.frame_main_bat, highlightbackground=self.light_grey)
        self.entry_bat_scan.insert(0, 5)
        self.dict_bat_relay_var = {} # contains check button variables 
        self.dict_bat_relay_but = {} # contains check button objects
        self.but_bat_ex =tk.Button(self.frame_main_bat, text="EXECUTE", highlightbackground=self.light_grey, command=self.callback_bat_ex)

        self.label_bat_title.grid(row=0, column=0, columnspan=1, sticky='nsew')
        self.label_bat_scan.grid(row=1, column=0, sticky='e')
        self.label_bat_scan2.grid(row=1, column=12, sticky='w')
        self.label_bat_relay.grid(row=2, column=0, sticky='e')
        self.label_bat_bat1.grid(row=3, column=15, sticky='w')
        self.label_bat_bat2.grid(row=4, column=15, sticky='w')
        self.label_bat_bat3.grid(row=5, column=15, sticky='w')
        self.label_bat_bat4.grid(row=6, column=15, sticky='w')
        self.entry_bat_scan.grid(row=1, column=1, columnspan=10, sticky='nsew')

        # create relay check buttons, variables associated with check buttons, and labels
        max_bat_count = max(self.dict_pack_to_nums.values())
        for relay_index in range(max_bat_count):
            tk.Label(self.frame_main_bat, text='r'+str(relay_index+1), font=self.label_font, bg=self.light_grey).grid(row=2, column=1+relay_index)

        for name_index in range(len(self.list_pack_names)):
            tk.Label(self.frame_main_bat, text=self.list_pack_names[name_index], font=self.label_font, bg=self.light_grey).grid(row=3+name_index, column=0, sticky='e')

            for relay_index in range(self.dict_pack_to_nums[self.list_pack_names[name_index]]):
                relay_name = self.list_pack_names[name_index] + 'r' + str(relay_index+1)
                self.dict_bat_relay_var[relay_name] = tk.IntVar()
                self.dict_bat_relay_but[relay_name] = tk.Checkbutton(self.frame_main_bat, bg=self.light_grey, variable=self.dict_bat_relay_var[relay_name], state='disabled')
                self.dict_bat_relay_but[relay_name].grid(row=3+name_index, column=1+relay_index)

        self.but_bat_ex.grid(row=10, column=15, sticky='e')


    def init_gra_group(self):
        #############################################################
        # GRAPH OPTIONS CONTAINER ###################################
        #############################################################
        self.label_gra_title = tk.Label(self.frame_main_gra, text='Graph Options', font=self.frame_font, bg=self.light_grey)
        self.label_gra_bat_options = tk.Label(self.frame_main_gra, text='Battery Packs to Plot:', font=self.label_font_bold, bg=self.light_grey)
        self.var_gra_b1 = tk.IntVar()
        self.var_gra_b2 = tk.IntVar()
        self.var_gra_b3 = tk.IntVar()
        self.var_gra_b4 = tk.IntVar()
        self.checkbut_gra_b1 = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_b1)
        self.checkbut_gra_b2 = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_b2)
        self.checkbut_gra_b3 = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_b3)
        self.checkbut_gra_b4 = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_b4)  
        self.label_gra_bat_1 = tk.Label(self.frame_main_gra, text='Pack 1', font=self.label_font, bg=self.light_grey)
        self.label_gra_bat_2 = tk.Label(self.frame_main_gra, text='Pack 2', font=self.label_font, bg=self.light_grey)
        self.label_gra_bat_3 = tk.Label(self.frame_main_gra, text='Pack 3', font=self.label_font, bg=self.light_grey)
        self.label_gra_bat_4 = tk.Label(self.frame_main_gra, text='Pack 4', font=self.label_font, bg=self.light_grey)
        self.label_gra_plt_options = tk.Label(self.frame_main_gra, text='Variables to Plot:', font=self.label_font_bold, bg=self.light_grey)
        self.var_gra_v = tk.IntVar()
        self.var_gra_i = tk.IntVar()
        self.var_gra_ai= tk.IntVar()
        self.var_gra_p = tk.IntVar()
        self.var_gra_k = tk.IntVar()
        self.var_gra_q = tk.IntVar()
        self.var_gra_c = tk.IntVar()
        self.checkbut_gra_v = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_v)
        self.checkbut_gra_i = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_i)
        self.checkbut_gra_ai= tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_ai) 
        self.checkbut_gra_p = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_p)
        self.checkbut_gra_k = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_k)
        self.checkbut_gra_q = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_q)
        self.checkbut_gra_c = tk.Checkbutton(self.frame_main_gra, bg=self.light_grey, variable=self.var_gra_c)
        self.label_gra_v = tk.Label(self.frame_main_gra, text='Voltage (mV)', font=self.label_font, bg=self.light_grey)
        self.label_gra_i = tk.Label(self.frame_main_gra, text='Current (mA)', font=self.label_font, bg=self.light_grey)
        self.label_gra_ai= tk.Label(self.frame_main_gra, text='Aggregate Current (mA)', font=self.label_font, bg=self.light_grey)
        self.label_gra_p = tk.Label(self.frame_main_gra, text='Percent Charge (%)', font=self.label_font, bg=self.light_grey)
        self.label_gra_k = tk.Label(self.frame_main_gra, text='Temperature (C)', font=self.label_font, bg=self.light_grey)
        self.label_gra_q = tk.Label(self.frame_main_gra, text='Charge State (mAhrs)', font=self.label_font, bg=self.light_grey)
        self.label_gra_c = tk.Label(self.frame_main_gra, text='Desired Charge Rate (mA)', font=self.label_font, bg=self.light_grey)
        self.but_gra_ex = tk.Button(self.frame_main_gra, text='EXECUTE', highlightbackground=self.light_grey, command=self.callback_gra_ex)

        self.label_gra_title.grid(row=0, column=0, columnspan=1, sticky='nsew')
        self.label_gra_bat_options.grid(row=1, column=0, sticky='e')
        self.checkbut_gra_b1.grid(row=1, column=1, sticky='w')
        self.checkbut_gra_b2.grid(row=2, column=1, sticky='w')
        self.checkbut_gra_b3.grid(row=3, column=1, sticky='w')
        self.checkbut_gra_b4.grid(row=4, column=1, sticky='w')
        self.label_gra_bat_1.grid(row=1, column=2, sticky='w')
        self.label_gra_bat_2.grid(row=2, column=2, sticky='w')
        self.label_gra_bat_3.grid(row=3, column=2, sticky='w')
        self.label_gra_bat_4.grid(row=4, column=2, sticky='w')
        self.label_gra_plt_options.grid(row=5, column=0, sticky='e')
        self.checkbut_gra_v.grid(row=5, column=1, sticky='w')
        self.checkbut_gra_i.grid(row=6, column=1, sticky='w')
        self.checkbut_gra_ai.grid(row=7, column=1, sticky='w')
        self.checkbut_gra_p.grid(row=8, column=1, sticky='w')
        self.checkbut_gra_k.grid(row=9, column=1, sticky='w')
        self.checkbut_gra_q.grid(row=10, column=1, sticky='w')
        self.checkbut_gra_c.grid(row=11, column=1, sticky='w')
        self.label_gra_v.grid(row=5, column=2, sticky='w')
        self.label_gra_i.grid(row=6, column=2, sticky='w')
        self.label_gra_ai.grid(row=7, column=2, sticky='w')
        self.label_gra_p.grid(row=8, column=2, sticky='w')
        self.label_gra_k.grid(row=9, column=2, sticky='w')
        self.label_gra_q.grid(row=10, column=2, sticky='w')
        self.label_gra_c.grid(row=11, column=2, sticky='w')
        self.but_gra_ex.grid(row=12, column=3, sticky='e')


    def init_trm_group(self):
        #############################################################
        # TERMINAL OPTIONS CONTAINER ################################
        #############################################################
        self.label_trm_title = tk.Label(self.frame_main_trm, text='Terminal Options',  font=self.frame_font, bg=self.light_grey)
        self.label_trm_bat_options = tk.Label(self.frame_main_trm, text='Battery Packs to Plot:', font=self.label_font_bold, bg=self.light_grey)
        self.var_trm_b1 = tk.IntVar()
        self.var_trm_b2 = tk.IntVar()
        self.var_trm_b3 = tk.IntVar()
        self.var_trm_b4 = tk.IntVar()
        self.checkbut_trm_b1 = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_b1)
        self.checkbut_trm_b2 = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_b2)
        self.checkbut_trm_b3 = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_b3)
        self.checkbut_trm_b4 = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_b4)  
        self.label_trm_bat_1 = tk.Label(self.frame_main_trm, text='Pack 1', font=self.label_font, bg=self.light_grey)
        self.label_trm_bat_2 = tk.Label(self.frame_main_trm, text='Pack 2', font=self.label_font, bg=self.light_grey)
        self.label_trm_bat_3 = tk.Label(self.frame_main_trm, text='Pack 3', font=self.label_font, bg=self.light_grey)
        self.label_trm_bat_4 = tk.Label(self.frame_main_trm, text='Pack 4', font=self.label_font, bg=self.light_grey)
        self.label_trm_plt_options = tk.Label(self.frame_main_trm, text='Variables to Plot:', font=self.label_font_bold, bg=self.light_grey)
        self.var_trm_v = tk.IntVar()
        self.var_trm_i = tk.IntVar()
        self.var_trm_ai= tk.IntVar()
        self.var_trm_p = tk.IntVar()
        self.var_trm_k = tk.IntVar()
        self.var_trm_q = tk.IntVar()
        self.var_trm_c = tk.IntVar()
        self.var_trm_f = tk.IntVar()
        self.checkbut_trm_v = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_v)
        self.checkbut_trm_i = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_i)
        self.checkbut_trm_ai= tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_ai)
        self.checkbut_trm_p = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_p)
        self.checkbut_trm_k = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_k)
        self.checkbut_trm_q = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_q)
        self.checkbut_trm_c = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_c)
        self.checkbut_trm_f = tk.Checkbutton(self.frame_main_trm, bg=self.light_grey, variable=self.var_trm_f)
        self.label_trm_v = tk.Label(self.frame_main_trm, text='Voltage (mV)', font=self.label_font, bg=self.light_grey)
        self.label_trm_i = tk.Label(self.frame_main_trm, text='Current (mA)', font=self.label_font, bg=self.light_grey)
        self.label_trm_ai= tk.Label(self.frame_main_trm, text='Aggregate Current (mA)', font=self.label_font, bg=self.light_grey)
        self.label_trm_p = tk.Label(self.frame_main_trm, text='Percent Charge (%)', font=self.label_font, bg=self.light_grey)
        self.label_trm_k = tk.Label(self.frame_main_trm, text='Temperature (K)', font=self.label_font, bg=self.light_grey)
        self.label_trm_q = tk.Label(self.frame_main_trm, text='Charge State (mAhrs)', font=self.label_font, bg=self.light_grey)
        self.label_trm_c = tk.Label(self.frame_main_trm, text='Desired Charge Rate (mA)', font=self.label_font, bg=self.light_grey)
        self.label_trm_f = tk.Label(self.frame_main_trm, text='IEB Status Flags', font=self.label_font, bg=self.light_grey)
        self.but_trm_ex = tk.Button(self.frame_main_trm, text='EXECUTE', highlightbackground=self.light_grey, command=self.callback_trm_ex)

        self.label_trm_title.grid(row=0, column=0, columnspan=1, sticky='nsew')
        self.label_trm_bat_options.grid(row=1, column=0, sticky='e')
        self.checkbut_trm_b1.grid(row=1, column=1, sticky='w')
        self.checkbut_trm_b2.grid(row=2, column=1, sticky='w')
        self.checkbut_trm_b3.grid(row=3, column=1, sticky='w')
        self.checkbut_trm_b4.grid(row=4, column=1, sticky='w')
        self.label_trm_bat_1.grid(row=1, column=2, sticky='w')
        self.label_trm_bat_2.grid(row=2, column=2, sticky='w')
        self.label_trm_bat_3.grid(row=3, column=2, sticky='w')
        self.label_trm_bat_4.grid(row=4, column=2, sticky='w')
        self.label_trm_plt_options.grid(row=5, column=0, sticky='e')
        self.checkbut_trm_v.grid(row=5, column=1, sticky='w')
        self.checkbut_trm_i.grid(row=6, column=1, sticky='w')
        self.checkbut_trm_ai.grid(row=7, column=1, sticky='w')
        self.checkbut_trm_p.grid(row=8, column=1, sticky='w')
        self.checkbut_trm_k.grid(row=9, column=1, sticky='w')
        self.checkbut_trm_q.grid(row=10, column=1, sticky='w')
        self.checkbut_trm_c.grid(row=11, column=1, sticky='w')
        self.checkbut_trm_f.grid(row=12, column=1, sticky='w')
        self.label_trm_v.grid(row=5, column=2, sticky='w')
        self.label_trm_i.grid(row=6, column=2, sticky='w')
        self.label_trm_ai.grid(row=7, column=2, sticky='w')
        self.label_trm_p.grid(row=8, column=2, sticky='w')
        self.label_trm_k.grid(row=9, column=2, sticky='w')
        self.label_trm_q.grid(row=10, column=2, sticky='w')
        self.label_trm_c.grid(row=11, column=2, sticky='w')
        self.label_trm_f.grid(row=12, column=2, sticky='w')
        self.but_trm_ex.grid(row=13, column=3, sticky='e')


    def init_bot_group(self):
        #############################################################
        # BOTTOM CONTAINER ##########################################
        #############################################################
        self.but_bot_off = tk.Button(self.frame_main_bot, text='POWER OFF', highlightbackground=self.pwr_off_color, command=self.callback_POWER_OFF)
        self.but_bot_close = tk.Button(self.frame_main_bot, text='close', highlightbackground=self.pwr_off_color, command=self.master.destroy)
        self.but_bot_connect = tk.Button(self.frame_main_bot, text='Connect to Serial Bus', highlightbackground=self.connect_color, command=self.callback_connect)

        self.but_bot_off.grid(row=1, column=1, sticky='w')
        self.but_bot_close.grid(row=1, column=2, sticky='e')
        self.but_bot_connect.grid(row=1, column=3, sticky='e')


#############################################################
# MAIN ######################################################
#############################################################
if __name__ == "__main__":
    warnings.filterwarnings("ignore",".*GUI is implemented.*")
    root = tk.Tk()
    gui = GUI(root)
    root.mainloop()

