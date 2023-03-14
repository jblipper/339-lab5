'''
<pid_controller.py> is a GUI for interacting with the PHYS 339 
Arduino PID setup. It wraps an API <pid_controller_api.py> which handles 
the serial communication with the Arduino. Remember the Cant.

For use in the McGill University physics course PHYS-339.
Written by Brandon Ruffolo in 2022-23.
Email: brandon.ruffolo@mcgill.ca
'''

import spinmob.egg as _egg
import traceback   as _traceback
import spinmob     as _s
import time        as _time
import ctypes

from PyQt5 import QtGui, QtWidgets, QtCore
from pid_controller_api import pid_api

try   : from serial.tools.list_ports import comports as _comports
except: _comports = None

_p = _traceback.print_last
_g = _egg.gui

# Dark theme
_s.settings['dark_theme_qt'] = True

try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID( u'PHYS 339 PID')
except Exception: 
        pass
    

class pid_controller():
    
    def __init__(self, name='PHYS 339 PID', api_class = pid_api, temperature_limit=80, show=True, block=False, window_size=[900,650]):
        
        w = self.window = _g.Window(name, size = window_size, autosettings_path=name+'_window.txt')
        w.set_size(window_size)
        self.window._window.setWindowIcon(QtGui.QIcon('Images/symbol'))

        self.name = name  # Remebmer the name.

        # Checks periodically for the last exception
        self.timer_exceptions = _g.TimerExceptions()
        self.timer_exceptions.signal_new_exception.connect(self._new_exception)

        # Where the actual api will live after we connect.
        self.api = None
        self._api_class = api_class
        
       # Get all the available ports
        self._ports = [] # Actual port names for connecting
        ports       = [] # Pretty port names for combo box
        
        default_port = None
        
        if _comports:
            for inx, p in enumerate(_comports()):
                self._ports.append(p.device)
                ports      .append(p.description)
                
                if 'Arduino' in p.description:
                    default_port = inx

        # Append simulation port
        ports      .append('Simulation')
        self._ports.append('Simulation')
        
        # Append refresh port
        ports      .append('Refresh - Update Ports List')
        self._ports.append('Refresh - Update Ports List')
        
        self.populate_window(ports, default_port, show, block, name)
        
        # Create Timer for collecting data 
        self.timer = _g.Timer(interval_ms=250, single_shot=False)
        self.timer.signal_tick.connect(self._timer_tick)
        
        self.t0 = None
        
        self.window.show(block)
        
        
    def populate_window(self, ports, default_port, show, block, name):
        # Populate the GUI window 
        w = self.window
        gt = self._grid_top    = w.add(_g.GridLayout(margins=False), column=1, row=1, alignment=0)
        gb = self._grid_bottom = w.add(_g.GridLayout(margins=False), column=1, row=2, alignment=0).disable()
        
        if default_port is None: default_port = 0
        self.combo_ports = gt.add(_g.ComboBox(ports, default_index = default_port))
        self.combo_ports.signal_changed.connect(self._ports_changed)
        
        # Add BAUD selector to GUI 
        gt.add(_g.Label('Baud:'))
        self.combo_baudrates = gt.add(_g.ComboBox(['1200','2400','4800', '9600', '19200', '38400', '57600', '115200'],
                                                             default_index=7,autosettings_path=self.name+'.combo_baudrates'))
        
        # Add Timeout selector to GUI 
        gt.add(_g.Label('Timeout:'),alignment=1)
        self.number_timeout = gt.add(_g.NumberBox(100, dec=True, bounds=(1, None), suffix=' ms',
                         tip='How long to wait for an answer before giving up (ms).', autosettings_path=self.name+'.number_timeout')).set_width(100)
        
        # Add Connect Button 
        self.button_connect = gt.add(_g.Button(
                    'Connect',
                    checkable=True,
                    signal_toggled = self._button_connect_toggled,
                    tip='Connect to chosen device.'))
        self.label_status   = gt.add(_g.Label(''))
        gt.set_column_stretch(5)

        # Add tabs for the different devices on the adalm2000
        self.tabs = gb.add(_g.TabArea(self.name+'.tabs'), alignment=0)
        
        t1 = self.tab_quadratures = self.tabs.add_tab('Data Monitor')
        
        self.tabs._widget.setTabIcon(0, QtGui.QIcon('Images/Discriminator.png'))
        
        
        self.grid_right  = t1.add(_g.GridLayout(margins=False),alignment=0)
        self.grid_left = t1.add(_g.GridLayout(margins=False), alignment=2)

        # # GRID LEFT
        self.grid_left_top  = self.grid_left.add(_g.GridLayout(margins=False), alignment=1)
        self.grid_left_top_extra  = self.grid_left.add(_g.GridLayout(margins=False), alignment=2)
        self.grid_left.new_autorow()
        self.settings = self.grid_left.add(_g.TreeDictionary(
            autosettings_path  = name+'.settings',
            name               = name+'.settings'),column_span=10).set_width(800)
    
        # Add the sweep controls

        self.button_loop_control = self.grid_left_top.add(_g.Button(
            text            = 'Open\nLoop',
            signal_clicked  = self.loop_control_changed,
            tip = 'Set outputs, collect data, and estimate quadratures at a variety of frequencies specified below.',
            signal_toggled  = None), 
            alignment = 2).set_style('font-size: 11pt;').set_width(100).set_colors(text = 'orange').disable()
        
        self.button_inject = self.grid_left_top_extra.add(_g.Button('',
            checkable       = True,
            signal_toggled  = None,
            tip='Inject a Heating/Cooling pulse into your block.\n'+
            'Can be used for generalized testing, for example:\n'+
            '•Testing the stability of your control loop when in closed loop operation.\n'+
            '•Testing the thermal response of your system when in open loop operation.'),
            alignment = 2).set_width(75).set_height(75).disable()
        
        self.button_inject._widget.setIcon(QtGui.QIcon('Images/inject_pulse.png'))
        self.button_inject._widget.setIconSize(QtCore.QSize(40,40))
        
        self.setup_ParameterTree()
        
        # GRID RIGHT

        self.grid_right_top  = self.grid_right.add(_g.GridLayout(margins=False),alignment=1)
        
        self.grid_right_top.add(_g.Label('Measured Temperature:'), 0,0, alignment=2).set_style('font-size: 12pt; color: white')
        self.number_temperature = self.grid_right_top.add(_g.NumberBox(
            25.4, dec=True,suffix = '°C', tip=''), 1, 0).set_width(125).set_style('font-size: 12pt; color: white').disable()
        
        self.grid_right_top.set_column_stretch(1)

        self.grid_right_top.add(_g.Label('Setpoint Temperature:'), 0,1, alignment=2).set_style('font-size: 12pt; color: cyan')
        self.number_setpoint = self.grid_right_top.add(_g.NumberBox(
            25.4, dec=True, bounds=(-50,80),suffix = '°C',
            tip='Iteration at this frequency.'),
            1,1).set_width(125).set_style('font-size: 12pt; color: cyan').disable()
        
        self.grid_right_top.add(_g.Label('DAC Output:'), 2,1, alignment=2).set_style('font-size: 12pt; color: pink')
        self.number_dac = self.grid_right_top.add(_g.NumberBox(
            0, int=True, bounds=(-4095,4095), 
            tip='Iteration at this frequency.'),3,1).set_width(125).set_style('font-size: 12pt; color: pink').disable()

        ## Tabs for data plotting ##
        self.grid_right.new_autorow()
        self.tabs_data = self.grid_right.add(_g.TabArea(autosettings_path=name+'.tabs'), alignment=0)

        self.tab_main   = self.tabs_data.add_tab('Main Data')
        self.tab_debug  = self.tabs_data.add_tab('DeBugging Data')

        self.plot_main = self.tab_main.add(_g.DataboxPlot(
            file_type         = '*.raw',
            autosettings_path = name+'.plot_raw',
            name              = name+'.plot_raw',
            delimiter=','), alignment=0)

        #self.button_folder = self.grid_top.place_object(_g.Button(' ', tip='Search folder', checkable = True)).set_width(64).set_height(64)
        #self.button_folder._widget.setIcon(QtGui.QIcon('Images/OpenFolder.png')) 

        self.plot_debug = self.tab_debug.add(_g.DataboxPlot(
            file_type         = '*.debug',
            autosettings_path = name+'.plot_quadratures',
            name              = name+'.plot_quadratures',
            autoscript        = 1), alignment=0, column_span=3)
        self.tab_debug.set_column_stretch(2)
     
    def setup_ParameterTree(self):
        s = self.settings

        s.add_parameter('Output/DAC', 0, int=True, bounds=(-4095,4095),
            tip = 'Output value of the 12-bit DAC (MCP4725). Range is [-4095,4095].')
        
        s.add_parameter('Loop Parameters/Band', 10.01, dec=True, decimals = 5, bounds = (0,None),
            suffix = '°C', siPrefix = True,
            tip = '').set_style('font-size: 10pt; font-weight: bold; color: white').set_width(300)

        s.add_parameter('Loop Parameters/Integral time', 0.12, dec=True, decimals = 5,  bounds = (0,None),
            suffix = 's', siPrefix = True,
            tip = '')
        
        s.add_parameter('Loop Parameters/Derivative time', 53.03, dec=True, decimals = 5,
            suffix='s', siPrefix=True, bounds=(0,None),
            tip = '')
        
        s.add_parameter('Loop Parameters/Control Period', 1.0, dec=True,
            suffix='ms', bounds=(20,10000), siPrefix=True,
            tip = '')

        # Force to 0
        s.block_key_signals('Output/DAC')
        s.set_value('Output/DAC', 0)
        s.unblock_key_signals('Output/DAC')
        
        s.add_parameter('Output/Temperature Setpoint', 24.5, bounds = (-20,72), decimals = 5,
                        suffix = '°C',
                        tip = 'Setpoint temperature of the control loop. Enter any temperature in the range [-20,72] °C.')
        
        s.connect_signal_changed('Loop Parameters/Band'           , self.loop_parameter_changed)
        s.connect_signal_changed('Loop Parameters/Integral time'  , self.loop_parameter_changed)
        s.connect_signal_changed('Loop Parameters/Derivative time', self.loop_parameter_changed)
        s.connect_signal_changed('Loop Parameters/Control Period' , self._number_period_changed)
        s.connect_signal_changed('Output/DAC'                     , self._number_dac_changed)
        s.connect_signal_changed('Output/Temperature Setpoint'    , self._number_setpoint_changed)
        
        s.add_parameter('DeBug/User Variables', True)
        
        s.add_parameter('Pulse/Type', ['Square','Gaussian','Triangular'],
            tip = 'Number of steps from start to stop.')        
        
        s.add_parameter('Pulse/Width', 1.25, dec=True,
            suffix = 's', siPrefix=True,
            tip = 'Sweep stop frequency.')

        s.add_parameter('Pulse/Height', 103, bounds = (0,4095),
            tip = 'Number of steps from start to stop.')

        s.add_parameter('Pulse/Polarity', ['Heat','Cool'],
            tip = 'Number of steps from start to stop.')
        
        s.add_parameter('Settings/MAX31865/Conversion Mode', ['One-Shot', 'Continuous'],
                        tip = 'Number of steps from start to stop.')
        
        s.add_parameter('Settings/MAX31865/Enable Bias', True,
                        tip = 'Applies to One-Shot conversions. RTD self-heating can be reduced with bias disabled.\n'+
                        'If disabled, the RTD RC network will need to charge everytime a conversion is initiated.\n'+
                        'Practically this will increase the conversion time by 10 milliseconds.')
        
        s.add_parameter('Settings/MAX31865/Configuration register', '0b00000000',
                        tip = 'Number of steps from start to stop.', readonly = True)
        
        s.add_parameter('Settings/MAX31865/Fault Check', True,
                        tip = 'Number of steps from start to stop.')
        
        s.add_parameter('Settings/Arduino/Temperature Calculation', ['Polynomial', 'Lookup table'],
                        tip = 'Number of steps from start to stop.')
        
        s.add_parameter('Settings/GUI/Startup/Loop Parameters', ['Grap Arduino Defaults', 'Use Current Values'],
                        tip = 'Number of steps from start to stop.')
        
        s.add_parameter('Settings/GUI/General/Max Setpoint', 80, suffix='°C',int=True, 
                        tip = 'Number of steps from start to stop.')
        
        s.add_parameter('Settings/GUI/General/Min Setpoint', -20, suffix='°C', int= True,
                        tip = 'Number of steps from start to stop.')

        a = self.settings.get_widget('Output')
        a.setIcon(0,QtGui.QIcon('Images/Dac.png'))
        
        a = self.settings.get_widget('DeBug')
        a.setIcon(0,QtGui.QIcon('Images/debug.png'))
        a.setExpanded(False)

        a = self.settings.get_widget('Pulse')
        a.setIcon(0,QtGui.QIcon('Images/Pulse.png'))
        a.setExpanded(False)
        
        a = self.settings.get_widget('Loop Parameters')
        a.setIcon(0,QtGui.QIcon('Images/Loop.png'))
        
        a = self.settings.get_widget('Settings')
        a.setIcon(0, QtGui.QIcon('Images/Settings.png'))
        a.setExpanded(False)
        
        self.settings.get_widget('Settings/MAX31865').setExpanded(False)
        self.settings.get_widget('Settings/Arduino') .setExpanded(False)
        self.settings.get_widget('Settings/GUI')     .setExpanded(False)
    
    def loop_control_changed(self):
        
        if(self.button_loop_control.get_text() == 'Open\nLoop'):
            self.button_loop_control.set_colors(text = 'mediumspringgreen')
            self.button_loop_control.set_text('Closed\nLoop')
            self.api.set_mode('CLOSED_LOOP')
            return
        
        if(self.button_loop_control.get_text() == 'Closed\nLoop'):
            self.button_loop_control.set_colors(text = 'orange')
            self.button_loop_control.set_text('Open\nLoop')
            self.api.set_mode('OPEN_LOOP')
            return
    
    def _button_connect_toggled(self, *a):
        """
        Called when the connect button is toggled in the GUI. 
        Creates the API and imports data from the arduino.
        """
        if self._api_class is None:
            raise Exception('You need to specify an api_class when creating a serial GUI object.')

        # If we checked it, open the connection and start the timer.
        if self.button_connect.is_checked():
            port = self.get_selected_port()
            self.api = self._api_class(
                    port=port,
                    baudrate=int(self.combo_baudrates.get_text()),
                    timeout=self.number_timeout.get_value())
            
            # If we're in simulation mode
            if self.api.simulation:
                self.label_status.set_text('*** Simulation ***')
                self.label_status.set_colors('pink' if _s.settings['dark_theme_qt'] else 'red')
                self.button_connect.set_colors(background='pink')
            else:
                
                # Get temperature and parameter data currently on the arduino
                T            = self.api.get_temperature()
                S            = self.api.get_temperature_setpoint()
                period       = self.api.get_period()
                P, I, D      = self.api.get_parameters()
                dac_output   = self.api.get_dac()
                
                # Update the temperature, setpoint, and parameter tabs
                self.number_temperature .set_value(T,          block_signals=True)
                self.number_setpoint    .set_value(S,          block_signals=True)
                self.number_dac         .set_value(dac_output, block_signals=True)
                
                # Update the loop parameters
                self.settings.set_value('Loop Parameters/Band'           , P)
                self.settings.set_value('Loop Parameters/Integral time'  , I)
                self.settings.set_value('Loop Parameters/Derivative time', D)
                self.settings.set_value('Loop Parameters/Control Period' , period)
                self.settings.set_value('Output/Temperature Setpoint'    , S)
                
                # Force to DAC 0
                self.settings.block_key_signals('Output/DAC')
                self.settings.set_value('Output/DAC', 0)
                self.settings.unblock_key_signals('Output/DAC')
                
                config = self.api.get_RTD_config()
                for i in range(8-len(config)): 
                    config = '0'+ config
                config = '0b'+config
                
                self.settings.set_value('Settings/MAX31865/Configuration register', config)

            # Record the time if it's not already there.
            if self.t0 is None: self.t0 = _time.time()

            # Disable serial controls
            self.combo_baudrates.disable()
            self.combo_ports    .disable()
            self.number_timeout .disable()
            
            # Enable PID controls
            self.button_loop_control.enable()
            self.button_inject      .enable()
            self._grid_bottom       .enable()
            
            # Change the button color to indicate we are connected
            self.button_connect.set_text('Disconnect').set_colors(background = 'blue')
            
            # Clear the plots of any previous data
            self.plot_main .clear()
            self.plot_debug.clear()
            
            # Print Arduino sketch version for reference 
            self.label_status.set_text(self.api.get_version())  
            
            # Start the timer
            self.timer.start()

        # Otherwise, shut it down
        else:
            
            # Disconnect the API
            self.api.disconnect()
            
            # Reset Loop control to open loop
            self.button_loop_control.block_signals()
            self.button_loop_control.set_colors(text = 'orange').set_text('Open\nLoop')
            self.button_loop_control.unblock_signals()
            
            #
            self.button_connect.set_text('Connect').set_colors()

            # Re-enable serial controls
            self.combo_baudrates.enable()
            self.combo_ports    .enable()
            self.number_timeout .enable()
            
            # Disable PID controls
            self.button_loop_control.disable()
            self.button_inject      .disable()
            self._grid_bottom       .disable()
            
            # Stop the timer
            self.timer.stop()
    
    def loop_parameter_changed(self):
        """
        Called when someone changes one of the control parameters in the GUI.
        Updates all the control parameters on the arduino.

        """
        
        band = self.settings['Loop Parameters/Band']
        t_i  = self.settings['Loop Parameters/Integral time']
        t_d  = self.settings['Loop Parameters/Derivative time']
        
        self.api.set_parameters(band, t_i, t_d)
         
    def _number_period_changed(self):
        """
        Called when someone changes the control period number in the GUI.
        Updates the control period on the arduino.

        """
        _period = self.settings['Loop Parameters/Control Period']
        
        self.api.set_period(_period)
        
    def _number_dac_changed(self):
        self.api.set_dac(self.settings['Output/DAC'])
        
    def _number_setpoint_changed(self):
        self.api.set_temperature_setpoint(self.settings['Output/Temperature Setpoint'])
        
    def _timer_tick(self, *a):
        """
        Called whenever the timer ticks. 
        Updates all parameters and the plot and saves the latest data.
        
        """
        
        t, T, S, dac_level, period, _u1, _u2, _u3 = self.api.get_all_variables()
    
        # Update the temperature, dac voltage, and setpoint
        self.number_temperature.set_value(T)
        self.number_dac        .set_value(dac_level, block_signals=True)
        self.number_setpoint   .set_value(S, block_signals=True)

        # Append this to the databox
        self.plot_main .append_row([t/1000, T, T-S, 100*dac_level/4095], ckeys=['Time (s)', 'Temperature (C)', 'Temperature Error (C)', 'DAC Voltage (%)'])
        self.plot_debug.append_row([t/1000, _u1, _u2, _u3], ckeys = ['Time(s)','u1','u2','u3'])
        
        # Update the plot
        self.plot_main .plot()
        self.plot_debug.plot()

        # Update GUI
        self.window.process_events()
    
    def get_selected_port(self):
        """
        Returns the actual port string from the combo box.
        """
        return self._ports[self.combo_ports.get_index()]
    
    def _ports_changed(self):
        """
        Refreshes the list of availible serial ports in the GUI.
        """
        if self.get_selected_port() == 'Refresh - Update Ports List':
            
            len_ports = len(self.combo_ports.get_all_items())
            
            # Clear existing ports
            if(len_ports > 1): # Stop recursion!
                for n in range(len_ports):
                    self.combo_ports.remove_item(0)
            else:
                return
                self.combo_ports.remove_item(0)
                 
            self._ports = [] # Actual port names for connecting
            ports       = [] # Pretty port names for combo box
                
            default_port = 0
             
            # Get all the available ports
            if _comports:
                for inx, p in enumerate(_comports()):
                    self._ports.append(p.device)
                    ports      .append(p.description)
                    
                    if 'Arduino' in p.description:
                        default_port = inx
                        
            # Append simulation port
            ports      .append('Simulation')
            self._ports.append('Simulation')
            
            # Append refresh port
            ports      .append('Refresh - Update Ports List')
            self._ports.append('Refresh - Update Ports List')
             
            # Add the new list of ports
            for item in ports:
                self.combo_ports.add_item(item)
             
            # Set the new default port
            self.combo_ports.set_index(default_port)
        
    def _new_exception(self, a):
        """
        Just updates the status with the exception.
        """
        
    

self = pid_controller()  