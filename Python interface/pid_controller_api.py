'''
<pid_controller_api.py> is an API implementing
serial communication to an Arduino microcontroller running <PID.ino>.

For use in the McGill University physics course PHYS-339.
Written by Brandon Ruffolo in 2022-23.
Email: brandon.ruffolo@mcgill.ca
'''

import mcphysics as _mp
import time as _time


_serial_left_marker  = '>'
_serial_right_marker = '\n'  

_debug_enabled       = True 


class pid_api():
    """
    Commands-only object for interacting with an Arduino
    temperature controller.
    
    Parameters
    ----------
    port='COM3' : str
        Name of the port to connect to.
        
    baudrate=115200 : int
        Baud rate of the connection. Must match the instrument setting.
        
    timeout=3000 : number
        How long to wait for responses before giving up (ms). 
        
    temperature_limit=85 : float
        Upper limit on the temperature setpoint (C).
        
    """
    def __init__(self, port='COM3', baudrate=115200, timeout=500, temperature_limit=80):

        self._temperature_limit = temperature_limit        

        # Check for installed libraries
        if not _mp._serial:
            print('You need to install pyserial to use the Arduino based PID temperature controller.')
            self.simulation = True
            _debug('Simulation enabled.')

        # Assume everything will work for now
        else: self.simulation = False

        # If the port is "Simulation"
        if port=='Simulation': 
            self.simulation      = True
            self.simulation_mode = "OPEN_LOOP" 
            _debug('Simulation enabled.')

        # If we have all the libraries, try connecting.
        if not self.simulation:
            _debug("Attempting serial communication with following parameters:\nPort    : "+port+"\nBaudrate: "+str(baudrate)+" BPS\nTimeout : "+str(timeout)+" ms\n")
            
            try:
                # Create the instrument and ensure the settings are correct.
                self.serial = _mp._serial.Serial(port=port, baudrate=baudrate, timeout=timeout/1000)
                
                _debug("Serial communication to port %s enabled.\n"%port)
                

            # Something went wrong. Go into simulation mode.
            except Exception as e:
                print('Could not open connection to '+port+' at baudrate '+str(baudrate)+' BPS. Entering simulation mode.')
                print(e)
                self.serial = None
                self.simulation = True
        
        # Give the arduino time to run setup loop!
        _time.sleep(2)
                                
    def disconnect(self):
        """
        Disconnects.
        """
        if not self.simulation: 
            self.serial.close()
            _debug('Serial port closed.')

    def get_dac(self):
        """
        Gets the current output level of the dac.
        """
        if self.simulation: return _n.random.randint(0,4095)
        else:                    
            self.write('get_dac')
            return int(self.read())
        
    def get_temperature(self):
        """
        Gets the current temperature in Celcius.
        """
        if self.simulation: return _n.round(_n.random.rand()+24, 1)
        else:
             self.write('get_temp')
             return float(self.read())

    def get_temperature_setpoint(self):
        """
        Gets the current temperature setpoint in Celcius.
        """
        if self.simulation: return 25.4
        else:                    
             self.write('get_setpoint')
             
             # Convert to floating point number and return
             return float(self.read())
    
    def get_parameters(self):
        """
        Get the PID control parameters on the arduino.
        Returns
        -------
        Band: float
            The proportional band.
            
        t_i:  float
            The integral time.
            
        t_d: float
            The derivative time.
        """
        self.write('get_pid')  
        raw_params = self.read().split(',')
        
        # Convert to floating point numbers
        band = float(raw_params[0])
        ti   = float(raw_params[1])
        td   = float(raw_params[2]) 
        
        return band, ti, td
        
    def get_mode(self):
        """
        Get the current operating mode of the of the arduino temperature controller.
        Returns
        -------
        str
            The current operating mode.
        """
        if self.simulation:
            return self.simulation_mode
        
        self.write("get_mode")
        return self.read()
    
    def set_dac(self,level):
        """
        Sets the DAC output.
        
        Parameters
        ----------
        level : int
            The desired dac level. This number can range from 0 to 
            2**dac_bit_depth - 1. The output voltage will depend on 
            the dac supply voltage. 
            
        """
        
        if self.simulation: return
        
        # Get the control mode
        mode = self.get_mode()
         
        # Check that we are in OPEN_LOOP operation before attempting to set dac voltage
        if(mode == "OPEN_LOOP"):
            self.write("set_dac, "+str(level))
        else:
            print("Doing nothing. DAC output can only be directly controlled in OPEN_LOOP mode!")        
    
    def set_temperature_setpoint(self, T=20.0, temperature_limit=None):
        """
        Sets the temperature setpoint to the supplied value in Celcius.
        
        Parameters
        ----------
        T=20.0 : float
            Temperature setpoint (C).
            
        temperature_limit=None : None or float
            If None, uses self._temperature_limit. Otherwise uses the specified
            value to place an upper bound on the setpoint (C).
        """
        if temperature_limit is None: temperature_limit = self._temperature_limit
        
        if T > temperature_limit:
            print('Setpoint above the limit! Doing nothing.')
            return
        
        if not self.simulation:
            self.write('set_setpoint,'+str(T))
    
    def set_parameters(self,band, t_i, t_d):
        """
        Set the PID control parameters on the arduino.
        Parameters
        ----------
        band : float
            The proportional band.
        t_i : float
            The integral time.
        t_d : float
            The derivative time.
        Returns
        -------
        None.
        """
        if self.simulation: return 
        
        self.write('set_pid,%.4f,%.4f,%.4f'%(band,t_i,t_d)) 
        
    def set_mode(self,mode):
        """
        Set the current operating mode of the of the arduino temperature controller.
        Parameters
        ----------
        mode : str
            The desired operating mode.

        """
        
        if( mode != "OPEN_LOOP" and mode != "CLOSED_LOOP"):
            print("Controller mode has not been changed. %s is not a vaild mode."%mode)
            return 
        
        if self.simulation: 
            self.simulation_mode = mode
            return
        
        self.write("set_mode,%s"%mode)
        
    def set_period(self,period):
        """
        Set the control loop period.

        Parameters
        ----------
        period : int
            Control loop period [milliseconds].

        """
        if self.simulation:
            return
        
        self.write('set_period,%d'%(period))
    
    def get_period(self):
        """
        Get the control loop period.

        Returns
        -------
        int
            Control loop period [milliseconds].

        """
        
        self.write("get_period")
        
        return int(self.read())
        
    def write(self,raw_data):
        """
        Writes data to the serial line, formatted appropriately to be read by the arduino temperature controller.        
        
        Parameters
        ----------
        raw_data : str
            Raw data string to be sent to the arduino.
        
        Returns
        -------
        None.
        
        """
        encoded_data = (_serial_left_marker + raw_data + _serial_right_marker).encode()
        self.serial.write(encoded_data) 
    
    def read(self):
        """
        Reads data from the serial line.
        
        Returns
        -------
        str
            Raw data string read from the serial line.
        """
        return self.serial.read_until(expected = '\r\n'.encode()).decode().strip('\r\n')
    
    def get_RTD_config(self):
        self.write('get_MAX31865_config')
        
        return self.read()
    
    def get_all_variables(self):
        """
        Get all arduino parameters in one shot.

        """
        self.write('get_all')
        raw_params = self.read().split(',')
        
        _time      = float(raw_params[0])
        _temp      = float(raw_params[1])
        _setpoint  = float(raw_params[2])
        _dac       = float(raw_params[3]) 
        _period    = float(raw_params[4])
        _u1        = float(raw_params[5])
        _u2        = float(raw_params[6])
        _u3        = float(raw_params[7])
        
        
        return _time, _temp, _setpoint, _dac, _period, _u1, _u2, _u3

    def get_version(self):
        """
        Get the version of sketch currently on the arduino board.
        Returns
        -------
        str
            A string describing the arduino sketch version and compilation date.
        """
        self.write('get_version')
        
        return self.read()
        
def _debug(*a):
    if _debug_enabled:
        s = []
        for x in a: s.append(str(x))
        print(', '.join(s))