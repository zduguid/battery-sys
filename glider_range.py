# /usr/bin/env python3
#
# - Models glider performance in terms of range
# - Allows for graphical display of velocity vs. range relationship
#
# Author: Zach Duguid
# Last Updated: 07/19/2017

import numpy as np
import matplotlib
from matplotlib import pyplot as plt 
from mpl_toolkits.basemap import Basemap
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from matplotlib.patches import Polygon


class GliderModel(object):
    def __init__(self):
        ''' initialize glider model object and define model parameters  
        '''
        # modeling parameters
        self.capacity_li_pri = 12167        # non-rechargable
        self.capacity_li_sec = 3200         # rechargable 
        self.constant_transit_pwr = 5.5     # total transit power [W], assumes 5W mass spectrometer and 0.5W vehicle
        self.constant_survey_pwr = 12.5     # total survey power [W], assumes 12W mass spectrometer and 0.5W vehicles 
        self.c1 = 0.5213                    # coefficient from graphical fit
        self.c2 = 0.3467                    # coefficient from graphical fit

        # graphing parameters 
        self.major_line_width = 3
        self.minor_line_width = 1


    def get_range_data(self, capacity, constant_transit_pwr, constant_survey_pwr, plot_on):
        ''' extracts range data as a function of vehicle velocity and maintains the maximum range achieved   
        '''
        self.max_range = 0                  # max range achieved by glider (entirely transit mode)
        self.max_range_v = None             # speed associated with max range
        self.min_range = 0                  # min range achieved by glider (entirely survey mode)
        self.min_range_v = None             # speed associated with min range
        self.plot_capacity = capacity

        velocity = list(np.linspace(0.00, 2.5, 251))
        percent = range(101)
        v_to_x = 3.6                        # [sec/min]*[min/hr]*[km/m]
        transit_vel_dist = []               # transit distance as function of velocity
        survey_vel_dist = []                # survey distance as function of velocity 
        transit_per_dist = []               # transit distance as function of percent transit travel
        survey_per_dist = []                # survey distance as function of percent transit travel
        tot_dist = []                       # total distance reached via transit and survey travel

        # determine range [km] as a function of velocity [m/s]
        for v in velocity:
            r_transit = (capacity * v_to_x * v) / (constant_transit_pwr + (v/self.c1)**(1/self.c2))
            r_survey =  (capacity * v_to_x * v) / (constant_survey_pwr +  (v/self.c1)**(1/self.c2))
            transit_vel_dist.append(r_transit)
            survey_vel_dist.append(r_survey)

            # check if new maximum range is achieved for transit and survey mode
            if r_transit > self.max_range:
                self.max_range = r_transit
                self.max_range_v = v
            if r_survey > self.min_range:
                self.min_range = r_survey
                self.min_range_v = v 

        # determine range [km] as a function of percent transit travel [%]
        for p in percent:
            transit_per_dist.append((p/100) * self.max_range)
            survey_per_dist.append((1 - (p/100)) * self.min_range)
            tot_dist.append(transit_per_dist[-1] + survey_per_dist[-1])
        
        # plot velocity vs. range and percent transit travel vs. range if plot_on is True         
        if plot_on:
            # plot velocity vs. range
            plt.figure()
            plt.title('Glider Range as Function of Velocity \n (Capacity: ' + str(capacity) + ' WHrs)')
            plt.xlabel('Velocity [m/s]')
            plt.ylabel('Range [km]')
            plt.plot(velocity, transit_vel_dist, 'b', lw=self.major_line_width)
            plt.plot(velocity, survey_vel_dist,  'm', lw=self.major_line_width)
            plt.plot(velocity, [self.max_range]*len(velocity), 'b--', lw=self.minor_line_width)
            plt.plot(velocity, [self.min_range]*len(velocity), 'm--', lw=self.minor_line_width)
            plt.legend(['low power (transit mode)', 'high power (survey mode)'])
            plt.grid()
            plt.show()

            # plot percent transit travel vs. range
            plt.figure()
            plt.title('Glider Range as Function of Power Mode \n (Capacity: ' + str(capacity) + ' WHrs)')
            plt.xlabel('Percentage of Range operated in transit mode [%]')
            plt.ylabel('Range [km]')
            plt.plot(percent, tot_dist,       'k', lw=self.major_line_width)
            plt.plot(percent, transit_per_dist, '--b', lw=self.major_line_width)
            plt.plot(percent, survey_per_dist,  '--m', lw=self.major_line_width)
            plt.legend(['Total Distance', 'Transit Distance', 'Survey Distance'])
            plt.grid()
            plt.show()


if __name__ == '__main__':
    # initialize Glider Model object 
    model = GliderModel()

    # determine model and graphing parameters 
    plot_on = True
    capacity = model.capacity_li_sec
    constant_transit_pwr = model.constant_transit_pwr
    constant_survey_pwr =  model.constant_survey_pwr

    # extract velocity range data and plot
    model.get_range_data(capacity, constant_transit_pwr, constant_survey_pwr, plot_on)

