/*
 * <PID.ino> is the main PID temperature controller software. 
 * To be used with accompanying scripts <control.ino>, <get_and_set.ino>, 
 * and <serial_data.ino>. These are appended at compile time.
 * 
 * To be run alongside python GUI <pid_controller.py>, 
 * or API <pid_controller_api.py>. 
 * 
 * For use in the McGill University physics course PHYS-339.
 * Written by Brandon Ruffolo in 2021-23.
 * Email: brandon.ruffolo@mcgill.ca
*/

#define SKETCH_VERSION "1.0.0"


/* Imports */
#include <Adafruit_MCP4725.h>
#include <MAX31865.h>          // Modified Adafruit MAX31865 Library

/* Communication macros */
#define BAUD         115200 // Serial baudrate
#define POLARITY_PIN 6      // ARDUINO pin connected to the polarity control on the external electronics
#define DAC_ADDRESS  0x62   // I2C address of the MCP4725 DAC chip

/* RTD parameters */
#define RREF      4300       // The value of the Rref resistor in the MAX31865 package.
#define RNOMINAL  1000       // The 'nominal' 0°C resistance of the RTD
#define TEMPERATURE_MIN -50. // Miniumum  RTD temperature
#define TEMPERATURE_MAX 150. // Maximumum RTD temperature
#define PT1000_TBL_SIZE 202  // Size of the pt1000 RTD lookup table

/* Output control */
#define ENABLE_OUTPUT true 

/* Pt1000 RTD Lookup table.
 * Resistance values from -50C to +150C, in 1°C increments, conforming to IEC 751 Platinum RTD standard.
 * Values multipled by factor 10 for a 16-bit unsigned integer representation.
 * Stored in program memory to conserve RAM. Cannot be accessed directly.
 */
const uint16_t PROGMEM pt1000_table[PT1000_TBL_SIZE] = {
  8031,
  8070, 8110, 8150, 8189, 8229, 8269, 8308, 8348, 8388, 8427,
  8467, 8506, 8546, 8585, 8625, 8664, 8704, 8743, 8783, 8822,
  8862, 8901, 8940, 8980, 9019, 9059, 9098, 9137, 9177, 9216,
  9255, 9295, 9334, 9373, 9412, 9452, 9491, 9530, 9569, 9609,
  9648, 9687, 9726, 9765, 9804, 9844, 9883, 9922, 9961, 10000,
  10039,10078,10117,10156,10195,10234,10273,10312,10351,10390,
  10429,10468,10507,10546,10585,10624,10663,10702,10740,10779,
  10818,10857,10896,10935,10973,11012,11051,11090,11128,11167,
  11206,11245,11283,11322,11361,11399,11438,11477,11515,11554,
  11593,11631,11670,11708,11747,11785,11824,11862,11901,11940,
  11978,12016,12055,12093,12132,12170,12209,12247,12286,12324,
  12362,12401,12439,12477,12517,12555,12593,12632,12670,12708,
  12746,12785,12823,12861,12899,12938,12976,13014,13052,13090,
  13128,13167,13205,13243,13281,13319,13357,13395,13433,13471,
  13509,13547,13585,13623,13661,13699,13737,13775,13813,13851,
  13889,13927,13965,14003,14039,14077,14115,14153,14191,14229,
  14266,14304,14342,14380,14418,14456,14494,14532,14569,14607,
  14645,14682,14720,14758,14795,14833,14871,14908,14946,14983,
  15021,15058,15096,15134,15171,15209,15246,15284,15321,15358,
  15395,15432,15471,15508,15546,15583,15621,15658,15696,15733
};

/** Basic parameters **/ 
float temperature; // Will hold the most currently recorded temperature from the RTD
float setpoint;    // Temperature setpoint 

/** PID control parameters **/
float band        ;   // Proportional band
float t_integral  ;   // Integral time
float t_derivative;   // Derivative time

/** Timing parameters **/
uint16_t period;       // Control period (in milliseconds)
uint16_t dt;           // Time step between temperature measurements used in the control loop
uint32_t time_control; // Time of the temperature measurement last used to update the control function   
uint32_t time_recent ; // Time of the most recently taken temperature measurement

volatile boolean control_flag = false;

/** Serial data handling **/
const byte data_size = 64;        // Size of the data buffer receiving from the serial line 
char received_data[data_size];    // Array for storing received data
char temp_data    [data_size];    // Temporary array for use when parsing
char functionCall[20]  = {0};     //
boolean newData = false;          // Flag used to indicate if new data has been found on the serial line
char * strtok_index;              // Used by strtok() as an index

/** Control Modes **/
enum MODES{OPEN_LOOP,CLOSED_LOOP};
enum MODES mode = OPEN_LOOP;
const char *MODE_NAMES[] = {"OPEN_LOOP","CLOSED_LOOP"};

/** Setup the external DAC **/
Adafruit_MCP4725 dac;    // New DAC object
int16_t dac_output = 0;  // 

/** Setup MAX 31865 resistance-to-digital converter **/
Adafruit_MAX31865 rtd = Adafruit_MAX31865(13, 12, 11, 10); // Use software SPI: CS, DI, DO, CLK

/*  */
boolean polyfit       = true;

void _init(){
  /*
   * Initialalize control parameters 
   */
  set_setpoint(24.50);                   // Set temperature setpoint @ 24.5 C
  set_parameters(4.8, 15.16, 23.42);     // Set control paramters (as marked in the SWAN hatch)
  set_period(200);                       // Set control period @ 200 ms
  set_dac(0);                            // Dac output @ 0

  /* Do a preliminary temperature reading */
  uint16_t _adc = rtd.readRTD();            // One shot ADC measurement of the rtd
  temperature   = lookup_temperature(_adc); // Convert ADC measurement to temperature                                      
  time_control  = millis(); 
  time_recent   = millis();
}

void setup() {
  Serial.begin(BAUD);                 // Enable Serial COM. Make sure your computer is using the same baudrate! 
               
  if(ENABLE_OUTPUT)
  {
    pinMode(POLARITY_PIN, OUTPUT);    // Enable Polarity pin
    digitalWrite(POLARITY_PIN, LOW);  // Set Polarity pin LOW
    
    dac.begin(DAC_ADDRESS);           // Start communication with the external DAC
    dac.setVoltage(0, false);         // Set DAC output to ZERO
  }
  
  rtd.begin(MAX31865_3WIRE);          // Begin SPI communcation with the MAX 31865 chip
  _init();                            // Initialize relevant variables 
}

void loop() {
  receive_data();                       /* Look for and grab data on the serial line. */
                                        /* If new data is found, the newData flag will be set */ 
  if (newData == true) {
      strcpy(temp_data, received_data); /* this temporary copy is necessary to protect the original data    */
                                        /* because strtok() used in parseData() replaces the commas with \0 */
      parseData();                      // Parse the data for commands
      newData = false;                  // Reset newData flag
  }

  if(control_flag){
    read_temperature();                                    // Read the RTD temperature
    
    dt           = (uint16_t)(time_recent - time_control); // Update the time differential
    time_control = time_recent;                            // Update the time of the temperature measurement used in the control function

    if(mode == CLOSED_LOOP) control();                     // Call the control function
    
    control_flag = false;                                  // Reset control flag
  }
}

void read_temperature(){
  /**
   * Measure the RTD temperature, and  update measurement time.
   */
  uint16_t _adc = rtd.readRTD(); // One shot temperature measurement of the rtd
  time_recent   = millis();      // Update the time that this measurement was taken
  
  if(polyfit) temperature = calculate_temperature(_adc); // Convert ADC measurment via direct mathematical method
  else        temperature = lookup_temperature(_adc);    // Convert ADC measurement to temperature via lookup table
  
}

ISR(TIMER1_COMPA_vect){ 
/* 
 *  Timer1 compare interrupt 
 *  
 *  This interrupt is called at a regular intervals, that can be set with the set_period() function.  
 *  The main function of this interrupt is set the control flag, which is used in the main loop to 
 *  call the control() function at fixed time intervals.
 *  
 *  NOTE: This interupt will not be active until set_period() is called!
 */
  control_flag = true;
}
