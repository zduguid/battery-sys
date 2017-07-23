# /usr/bin/env python3
#
# - Models glider performance in terms of range
# - Allows for graphical display of speed vs. range relationship for different current conditions
#
# Author: Zach Duguid
# Last Updated: 07/23/2017


import math
import numpy as np
import matplotlib
from matplotlib import pyplot as plt 
from mpl_toolkits.basemap import Basemap
from mpl_toolkits.mplot3d import Axes3D
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
        self.T_range = 0                    # max range achieved by glider (entirely transit mode)
        self.T_range_v = None               # speed associated with max range
        self.S_range = 0                    # min range achieved by glider (entirely survey mode)
        self.S_range_v = None               # speed associated with min range

        # graphing parameters   
        self.major_line_width = 3           # width of thick graph lines 
        self.minor_line_width = 1           # width of small graph lines
        self.inset_size = '20%'             # size of inset map
        self.R = 6378.1                     # radius of the Earth [km] 
        self.T_range_color = 'b'            # transit mode color
        self.S_range_color = 'm'            # survey mode color 
        self.B_range_color = 'darkorange'   # buoyancy transit mode color
        self.total_color = 'k'              # total range color 
        self.base_land = 'peachpuff'        # base map land color
        self.base_water = 'powderblue'      # base map water color
        self.base_lines = 0.2               # base map line width
        self.inset_threshold = 1.5e7        # threshold for inset plotting
        self.inset_land = 'white'           # inset map land color 
        self.inset_water = 'grey'           # inset map water color 
        self.inset_box = 'red'              # inset map box color 
        self.brng_list = np.linspace(0, math.pi*2, 100)         # list of radian values between 0 and 2*Pi for plotting circles
        self.error_term = math.pi/(len(self.brng_list))         # error term for determining angle equivalance (angles are floats, won't be exactly equal)


    def get_range_data(self, constant_transit_pwr, constant_survey_pwr):
        ''' extracts range data as a function of through-water-speed and maintains the maximum range achieved   
        '''
        # get list of velocties, ocean currents, and percents to determine desired data
        velocity = [float(element) for element in (np.linspace(0.00, 2.5, 251))]
        ocean_currents = [str(round(element, 2)) for element in np.linspace(0.00, 1.78, 179)]
        percent = range(101)

        # initialize lists for speed vs. range plot for the user specified ocean current speed
        self.T_vel_dist = []                # transit distance as function of speed
        self.S_vel_dist = []                # survey distance as function of speed
        self.T_per_dist = []                # transit distance as function of percent transit travel
        self.S_per_dist = []                # survey distance as function of percent transit travel
        self.total_dist = []                # total distance reached via transit and survey travel

        # initialize buoyancy parameters from previously performed study
        self.B_range_v = 0.37               # buoyancy speed [m/s] 
        self.B_range_p = 6.7                # buoyancy power [W]
        self.B_range_t = (self.capacity / self.B_range_p)*3600      # buoyancy time [s]
        self.B_range_x = (self.B_range_v * self.B_range_t)/1000     # buoyance range [km]

        # initialize 
        self.T_current_x = []               # transit max range dependent on ocean current c
        self.S_current_x = []               # survey max range dependent on ocean current c
        self.T_current_v = []               # transit speed associated with max transit range, ocean current c
        self.S_current_v = []               # survey speed associated with max transit range, ocean current c
        self.T_current_p = []               # transit power associated with max transit range, ocean current c
        self.S_current_p = []               # survey power associated with max transit range, ocean current c
        self.T_current_y = []               # transit range if traveling at the zero current optimization values
        self.S_current_y = []               # survey range if traveling at the zero current optimization values
        self.T_current_i = []               # percent increase in peformance when optimizing with ocean current speed
        self.S_current_i = []               # percent increase in peformance when optimizing with ocean current speed

        # iterate through different ocean current scenarious, [m/s]
        for c in ocean_currents:

            # reset range values to zero for the new current scenario
            T_range = 0
            S_range = 0

            # determine range [km] as a function of speed [m/s] (v represents through-water-speed)
            for v in velocity:

                # v_total represents maximum ground speed (when v and self.current_speed are in the same direction)
                v_total = v + float(c)

                # determine propulsive power needed to achieve speed v 
                prop_power = self.get_prop_power(v)

                # determine range achieved in transit and survey modes 
                total_range_T = (self.capacity * 3600/1000 * v_total) / (constant_transit_pwr + prop_power)
                total_range_S = (self.capacity * 3600/1000 * v_total) / (constant_survey_pwr +  prop_power)
                prop_range_T = (self.capacity * 3600/1000 * v) / (constant_transit_pwr + prop_power)
                prop_range_S = (self.capacity * 3600/1000 * v) / (constant_survey_pwr +  prop_power)

                # append values if the ocean current c is the same as the user specified speed
                if c == str(self.current_speed):
                    self.T_vel_dist.append(total_range_T)
                    self.S_vel_dist.append(total_range_S)

                # check if new maximum range is achieved for transit and survey mode
                if total_range_T > T_range:
                    T_range = total_range_T                         # [km], maximize this term
                    T_range_x = prop_range_T                        # [km], use this term when applying ocean currents
                    T_range_v = v                                   # [m/s]
                    T_range_p = prop_power + constant_transit_pwr   # [W]       
                    T_range_t = (self.capacity/T_range_p)*3600      # [s]

                if total_range_S > S_range:
                    S_range = total_range_S                         # [km], maximize this term
                    S_range_x = prop_range_S                        # [km], use this term when applying ocean currents
                    S_range_v = v                                   # [m/s]
                    S_range_p = prop_power + constant_survey_pwr    # [W]
                    S_range_t = (self.capacity/S_range_p)*3600      # [s]  

            # extract values if the ocean current c is the same as the user specified speed
            if c == str(self.current_speed):
                self.T_range = T_range
                self.T_range_x = T_range_x
                self.T_range_v = T_range_v
                self.T_range_p = T_range_p
                self.T_range_t = T_range_t
                self.S_range = S_range
                self.S_range_x = S_range_x
                self.S_range_v = S_range_v
                self.S_range_p = S_range_p
                self.S_range_t = S_range_t

            # append values associated with ocean-current-optimized paramters 
            self.T_current_x.append(T_range)
            self.S_current_x.append(S_range)
            self.T_current_v.append(T_range_v)
            self.S_current_v.append(S_range_v)
            self.T_current_p.append(T_range_p)
            self.S_current_p.append(S_range_p)
            self.T_current_y.append(((self.T_current_v[0]+float(c))*(self.capacity/self.T_current_p[0])*3600)/1000) 
            self.S_current_y.append(((self.S_current_v[0]+float(c))*(self.capacity/self.S_current_p[0])*3600)/1000)
            self.T_current_i.append((self.T_current_x[-1] - self.T_current_y[-1])/ self.T_current_y[-1])
            self.S_current_i.append((self.S_current_x[-1] - self.S_current_y[-1])/ self.S_current_y[-1])

        # determine range, [km], as a function of percent transit travel [%]
        for p in percent:
            self.T_per_dist.append((p/100) * self.T_range)
            self.S_per_dist.append((1 - (p/100)) * self.S_range)
            self.total_dist.append(self.T_per_dist[-1] + self.S_per_dist[-1])
                 
        if 'speed-range' in self.plot_set:
            # plot speed vs. range
            plt.figure(figsize=(10,6.5))
            plt.title('Glider Range as Function of Speed \n (Capacity: ' + str(self.capacity) + ' WHrs) \n (Ocean Currents: ' + str(self.current_speed) + ' m/s)', fontweight='bold')
            plt.xlabel('Speed [m/s]')
            plt.ylabel('Range [km]')
            plt.plot(velocity, self.T_vel_dist, self.T_range_color, lw=self.major_line_width)
            plt.plot(velocity, self.S_vel_dist, self.S_range_color, lw=self.major_line_width)
            plt.plot(velocity, [self.T_range]*len(velocity), self.T_range_color+'--', lw=self.minor_line_width)
            plt.plot(velocity, [self.S_range]*len(velocity), self.S_range_color+'--', lw=self.minor_line_width)
            plt.legend(['Low Power (Transit Mode)', 'High Power (Survey Mode)'])
            plt.grid()
            plt.show()

        if 'percent-range' in self.plot_set:
            # plot percent transit travel vs. range
            plt.figure(figsize=(10,6.5))
            plt.title('Glider Range as Function of Power Mode \n (Capacity: ' + str(self.capacity) + ' WHrs) \n (Ocean Currents: ' + str(self.current_speed) + ' m/s)', fontweight='bold')
            plt.xlabel('Percentage of Power used in transit mode [%]')
            plt.ylabel('Range [km]')
            plt.plot(percent, self.total_dist, self.total_color, lw=self.major_line_width)
            plt.plot(percent, self.T_per_dist, self.T_range_color+'--', lw=self.major_line_width)
            plt.plot(percent, self.S_per_dist, self.S_range_color+'--', lw=self.major_line_width)
            plt.legend(['Total Range', 'Transit Range', 'Survey Range'])
            plt.grid()
            plt.show()

        if '3d-transit-range' in self.plot_set:
            # create a 3d-plot that shows range as a function of vehicle speed and ocean current speed
            fig = plt.figure(figsize=(10,6.5))
            ax = fig.add_subplot(111, projection='3d')
            x = y = np.arange(0, 2.5, 0.1)
            X, Y = np.meshgrid(x, y)
            z = np.array([self.get_range(x, y, self.capacity, self.constant_transit_pwr) for x,y in zip(np.ravel(X), np.ravel(Y))])
            Z = z.reshape(X.shape)
            ax.plot_surface(X, Y, Z, cmap='gnuplot')
            ax.set_title('Glider Range as Function of Vehicle Speed and Ocean Current Speed \n (Capacity: ' + str(self.capacity) + ' WHrs)', fontweight='bold')
            ax.set_xlabel('Vehicle Speed [m/s]')
            ax.set_ylabel('Ocean Current Speed [m/s]')
            plt.show()

        if '3d-survey-range' in self.plot_set:
            # create a 3d-plot that shows range as a function of vehicle speed and ocean current speed
            fig = plt.figure(figsize=(10,6.5))
            ax = fig.add_subplot(111, projection='3d')
            x = y = np.arange(0, 2.5, 0.1)
            X, Y = np.meshgrid(x, y)
            z = np.array([self.get_range(x, y, self.capacity, self.constant_survey_pwr) for x,y in zip(np.ravel(X), np.ravel(Y))])
            Z = z.reshape(X.shape)
            ax.plot_surface(X, Y, Z, cmap='gnuplot')
            ax.set_title('Glider Range as Function of Vehicle Speed and Ocean Current Speed \n (Capacity: ' + str(self.capacity) + ' WHrs)', fontweight='bold')
            ax.set_xlabel('Vehicle Speed [m/s]')
            ax.set_ylabel('Ocean Current Speed [m/s]')
            plt.show()

        if 'current-range' in self.plot_set:
            # plot ocean current speed vs. attainable range
            plt.figure(figsize=(10,6.5))
            plt.title('Glider Range as Function of Ocean Current Speed \n (Capacity: ' + str(self.capacity) + ' WHrs)', fontweight='bold')
            plt.xlabel('Ocean Current Speed [m/s]')
            plt.ylabel('Range [km]')
            plt.plot(ocean_currents, self.T_current_x, self.T_range_color, lw=self.major_line_width)
            plt.plot(ocean_currents, self.T_current_y, self.T_range_color+'--', lw=self.minor_line_width)
            plt.plot(ocean_currents, self.S_current_x, self.S_range_color, lw=self.major_line_width)
            plt.plot(ocean_currents, self.S_current_y, self.S_range_color+'--', lw=self.minor_line_width)
            plt.legend(['Transit Range (Optimized)', 'Transit Range (Original)', 'Survey Range (Optimized)', 'Survey Range (Original)'])
            plt.grid()
            plt.show()

        if 'current-increase' in self.plot_set:
            # plot ocean current speed vs. percent increase value
            plt.figure(figsize=(10,6.5))
            plt.title('Glider Range Increase as Function of Ocean Current Speed \n (Capacity: ' + str(self.capacity) + ' WHrs)', fontweight='bold')
            plt.xlabel('Ocean Current Speed [m/s]')
            plt.ylabel('Percent [%]')
            plt.plot(ocean_currents, self.T_current_i, self.T_range_color, lw=self.major_line_width)
            plt.plot(ocean_currents, self.S_current_i, self.S_range_color, lw=self.major_line_width)
            plt.legend(['Transit Mode', 'Survey Mode'])
            plt.grid()
            plt.show()

        if 'current-speed' in self.plot_set:
            # plot ocean current speed vs. optimal vehicle speed
            plt.figure(figsize=(10,6.5))
            plt.title('Glider Speed as Function of Ocean Current Speed \n (Capacity: ' + str(self.capacity) + ' WHrs)', fontweight='bold')
            plt.xlabel('Ocean Current Speed [m/s]')
            plt.ylabel('Glider Speed [m/s]')
            plt.plot(ocean_currents, self.T_current_v, self.T_range_color, lw=self.major_line_width)
            plt.plot(ocean_currents, self.S_current_v, self.S_range_color, lw=self.major_line_width)
            plt.legend(['Transit Mode', 'Survey Mode'])
            plt.grid()
            plt.show()

        if 'current-power' in self.plot_set:
            # plot ocean current speed vs. optimal thrust value
            plt.figure(figsize=(10,6.5))
            plt.title('Vehcile Power as Function of Ocean Current Speed \n (Capacity: ' + str(self.capacity) + ' WHrs)', fontweight='bold')
            plt.xlabel('Ocean Current Speed [m/s]')
            plt.ylabel('Power [W]')
            plt.plot(ocean_currents, self.T_current_p, self.T_range_color, lw=self.major_line_width)
            plt.plot(ocean_currents, [constant_transit_pwr]*len(ocean_currents), self.T_range_color+'--', lw=self.minor_line_width)
            plt.plot(ocean_currents, self.S_current_p, self.S_range_color, lw=self.major_line_width)
            plt.plot(ocean_currents, [constant_survey_pwr]*len(ocean_currents), self.S_range_color+'--', lw=self.minor_line_width)
            plt.legend(['Transit Power', 'Transit Hotel Load', 'Survey Power', 'Survey Hotel Load'])
            plt.grid()
            plt.show()

    def get_range(self, vehicle_speed, current_speed, capacity, hotel_pwr):
        ''' determines the range of the glider given necessary parameters
        '''
        v_total = vehicle_speed + current_speed

        # determine propulsive power needed to achieve speed v 
        prop_power = self.get_prop_power(vehicle_speed)

        # determine range and return
        return((capacity * 3600/1000 * v_total) / (hotel_pwr + prop_power))


    def get_prop_power(self, v):
        ''' determines propulsive power needed to achieve v, the through-water-speed
        '''
        return((v/self.c1)**(1/self.c2))


    def get_new_lat_lon(self, lat1, lon1, dist, brng):
        ''' determines new lat-lon coordinates given a reference cooridnate pair, a distance, and a bearing angle
            :important note:
                for this formula to work, all terms must be in radians 
        '''
        lat2 = math.asin((math.sin(lat1) * math.cos(dist/self.R)) + (math.cos(lat1) * math.sin(dist/self.R) * math.cos(brng)))
        dlon = math.atan2((math.sin(brng) * math.sin(dist/self.R) * math.cos(lat1)), (math.cos(dist/self.R) - math.sin(lat1) * math.sin(lat2)))
        lon2 = ((lon1 - dlon + math.pi) % (2*math.pi)) - math.pi
        return(lat2,lon2)


    def get_range_perimeter(self, lat, lon, dist):
        ''' determines the achievable range of the glider while traveling at a range-optimizing speed   
        '''
        # convert current lat and lon from degrees to radians
        lat1 = math.radians(lat)
        lon1 = math.radians(lon)

        # initialize lat and lon lists
        lat_list = []
        lon_list = [] 

        # iterate through terms between 0 and 2*Pi to account for all travel angles
        for brng in self.brng_list:
            
            # determine new lat lon coordinates 
            lat2,lon2 = self.get_new_lat_lon(lat1, lon1, dist, brng)

            # add lat and lon angles in degrees to lat and lon lists    
            lat_list.append(math.degrees(lat2))
            lon_list.append(math.degrees(lon2))

        return(lat_list, lon_list)


    def apply_ocean_currents(self, lat_list, lon_list, dist):
        ''' determines how ocean currents effect the reachable area of the glider 
        '''
        # initialize new lat and lon lists
        new_lat_list = []
        new_lon_list = [] 
        brng = math.radians(self.current_dir)

        # iterate through the current lat and lon list
        for i in range(len(lat_list)):
            lat1 = math.radians(lat_list[i])
            lon1 = math.radians(lon_list[i])

            # determine the lat lon coordinates after factoring in ocean currents 
            lat2,lon2 = self.get_new_lat_lon(lat1, lon1, dist, brng)

            # add lat and lon angles in degrees to new lat and lon lists 
            new_lat_list.append(math.degrees(lat2))
            new_lon_list.append(math.degrees(lon2))

        return(new_lat_list, new_lon_list)


    def apply_drift_adjustment(self, lat_list, lon_list, speed):
        ''' determines necessary range adjustment if the water current is faster than the glider speed
        '''
        # initialize new lat and lon lists
        new_lat_list = []
        new_lon_list = []
        
        # if the glider speed is faster than the currents, no action is needed 
        if self.current_speed <= speed:
            return(lat_list, lon_list)

        # else adjust lat and lon coordinates such that the achievable range is more accurate
        else:

            # determine the angles that are perpendicular to, and opposite of, the water current direction [rad] 
            perp1, perp2 = math.radians(self.current_dir + 90), math.radians(self.current_dir - 90)
            opp = math.radians(self.current_dir) - math.pi 

            # assert that perpendicular angle #1 is positive
            if perp1 < 0:
                perp1 += math.pi*2

            # assert that perpendicular angle #1 is positive
            if perp2 < 0:
                perp2 += math.pi*2

            # assert that the angle opposite of the current direction is positive
            if opp < 0:
                opp += math.pi*2

            # assert that perp1 is lower than perp2
            if perp1 > perp2:
                perp1, perp2 = perp2, perp1

            # iterate through the lat lon coordinates
            for i in range(len(self.brng_list)):

                # keep the relevant coordinates 
                if (((self.brng_list[i] < perp1) and (self.brng_list[i] < perp2) and (self.brng_list[i] < opp)) or ((self.brng_list[i] > perp1) and (self.brng_list[i] > perp2) and (self.brng_list[i] > opp))):
                    new_lat_list.append(lat_list[i])
                    new_lon_list.append(lon_list[i])

                # add the starting glider location in order to make the necessary range adjustment for the glider
                if abs(self.brng_list[i] - perp2) < self.error_term:
                    new_lat_list.append(self.lat)
                    new_lon_list.append(self.lon)

            return(new_lat_list, new_lon_list)


    def get_map_display_plot(self):
        ''' creates a visual display of the glider range overlayed on the world map
        '''
        # draw basemap and glider image
        fig = plt.figure(figsize=(6.5,6.5))
        ax = fig.add_subplot(111)
        glider_im = plt.imread('glider.png')
        bmap = Basemap(projection='lcc', width=self.map_width, height=self.map_width, lat_0=self.lat, lon_0=self.lon, resolution='c', ax=ax)
        bmap.fillcontinents(color=self.base_land, lake_color=self.base_water)
        bmap.imshow(glider_im, interpolation='lanczos', origin='upper', zorder=10)
        bmap.drawcountries(linewidth=self.base_lines)
        bmap.drawstates(linewidth=self.base_lines)
        bmap.drawcoastlines(linewidth=self.base_lines)
        bmap.drawmapboundary(fill_color=self.base_water)
        plt.title('Glider Range from Nassau, Bahamas \n (Capacity: ' + str(self.capacity) + ' WHrs) \n (Ocean Currents: ' + str(self.current_speed) + ' m/s)', fontweight='bold')

        # determine achievable range limits
        self.lat_list_T, self.lon_list_T = self.get_range_perimeter(self.lat, self.lon, self.T_range_x)
        self.lat_list_S, self.lon_list_S = self.get_range_perimeter(self.lat, self.lon, self.S_range_x)
        self.lat_list_B, self.lon_list_B = self.get_range_perimeter(self.lat, self.lon, self.B_range_x)

        # make necessary range limit adjustments if the current is non-zero
        if self.current_speed > 0:

            # keep a copy of the original lat lon coordinates in case the are needed later 
            self.lat_list_T_copy = [element for element in self.lat_list_T]
            self.lat_list_S_copy = [element for element in self.lat_list_S]
            self.lat_list_B_copy = [element for element in self.lat_list_B]

            # account for the ocean currents 
            self.lat_list_T, self.lon_list_T = self.apply_ocean_currents(self.lat_list_T, self.lon_list_T, (self.T_range_t * self.current_speed)/1000)
            self.lat_list_S, self.lon_list_S = self.apply_ocean_currents(self.lat_list_S, self.lon_list_S, (self.S_range_t * self.current_speed)/1000)
            self.lat_list_B, self.lon_list_B = self.apply_ocean_currents(self.lat_list_B, self.lon_list_B, (self.B_range_t * self.current_speed)/1000)

            # make drift adjustment for the range limits as necessary
            self.lat_list_T, self.lon_list_T = self.apply_drift_adjustment(self.lat_list_T, self.lon_list_T, self.T_range_v)
            self.lat_list_S, self.lon_list_S = self.apply_drift_adjustment(self.lat_list_S, self.lon_list_S, self.S_range_v)
            self.lat_list_B, self.lon_list_B = self.apply_drift_adjustment(self.lat_list_B, self.lon_list_B, self.B_range_v)
    
        # plot the range limits of the transit and survey mode scenarios
        bmap.plot(self.lon_list_T, self.lat_list_T, latlon=True, lw=self.major_line_width, color=self.T_range_color, linestyle='dashed')
        bmap.plot(self.lon_list_S, self.lat_list_S, latlon=True, lw=self.major_line_width, color=self.S_range_color, linestyle='dashed')

        # plot the range limit of the buoyancy mode as necessary
        if self.buoyancy_on:
            bmap.plot(self.lon_list_B, self.lat_list_B, latlon=True, lw=self.major_line_width, color=self.B_range_color, linestyle='dashed')
            plt.legend(['Transit Mode (low power) \n' + str(self.T_range_v) + ' m/s', 'Survey Mode (high power) \n' + str(self.S_range_v) + ' m/s', 'Buoyancy Transit (low power) \n' + str(self.B_range_v) + ' m/s'], loc=3)
        else:
            plt.legend(['Transit Mode (low power) \n' + str(self.T_range_v) + ' m/s', 'Survey Mode (high power) \n' + str(self.S_range_v) + ' m/s'], loc=3)

        # if the map is not too big, plot an inset map on top of the basemap
        if self.map_width <= self.inset_threshold:

            # create axes for inset map
            axin = inset_axes(bmap.ax, width=self.inset_size, height=self.inset_size, loc=4)

            # draw inset map  
            omap = Basemap(projection='ortho', lat_0=self.lat, lon_0=self.lon, ax=axin, anchor='NE')
            omap.drawcountries(color=self.inset_land)
            omap.fillcontinents(color=self.inset_water)               
            bx, by = omap(bmap.boundarylons, bmap.boundarylats)
            xy = list(zip(bx,by))
            mapboundary = Polygon(xy, edgecolor=self.inset_box, linewidth=self.major_line_width, fill=False, zorder=5)
            omap.ax.add_patch(mapboundary)

        plt.show()


if __name__ == '__main__':
    # initialize Glider Model object 
    model = GliderModel()

    # determine model and graphing parameters 
    model.plot_set = set(['speed-range', 'percent-range', 'current-power', 'current-range', 'current-increase', 'current-speed', '3d-transit-range', '3d-survey-range', 'map'])
    constant_transit_pwr = model.constant_transit_pwr
    constant_survey_pwr =  model.constant_survey_pwr
    model.capacity = model.capacity_li_sec
    model.lat = 25.10                       # lat of the Bahamas  
    model.lon = -77.25                      # lon of the Bahamas
    model.map_width = 8e6                   # desired width of the world map
    model.buoyancy_on = False               # determine whether or not to plot buoyancy transit mode range limits 
    model.current_speed = 1.78              # the average speed of the gulf stream [m/s]
    model.current_dir = -40                 # chosen direction for the gulf stream current [degrees]

    # extract speed and range data to plot
    model.get_range_data(constant_transit_pwr, constant_survey_pwr)

    # plot range data on world map as necessary
    if 'map' in model.plot_set:
        model.get_map_display_plot()
