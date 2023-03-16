#define sgn(x) ((x) < 0 ? -1 : ((x) > 0 ? 1 : 0)) // Gets the sign (positive or negative) of the argument

#define RTD_A 3.9083e-3
#define RTD_B -5.775e-7

const float Z1 = -RTD_A;
const float Z2 = RTD_A * RTD_A - (4 * RTD_B);
const float Z3 = (4 * RTD_B) / RNOMINAL;
const float Z4 = 2 * RTD_B;

void set_period(unsigned int _period){     
/*
 * Sets the time between calls to control().
 * 
 * period: period to be set in milliseconds.
 */    
  unsigned int num_clk_ticks = floor(16e6*_period/1024000) - 1; // Calculate the number of clock ticks in the specified period
  
  // Manipulating registers in the AVR chip (here the ATmega328 for the arduino uno), see the datasheet for details.
  cli();                    // Disable interrupts

  TCCR1A = 0;               // Blank out Timer control register A 
  TCCR1B = 0;               // Blank out Timer control register B 
  TCNT1  = 0;               // Initialize Timer1's counter value to be 0
  OCR1A  = num_clk_ticks;   /* Set the output compare register 1 to the number of ticks calculated earlier */    
                            /* Note that OCR1a is a 16-bit register, so _number <= 65,535             */ 

  TCCR1B |= (1 << WGM12);                 // Enable clear timer on compare match (CTC) mode
  TCCR1B |= (1 << CS12) | (1 << CS10);    // Set a prescaler of 1024 on Timer1 
  TIMSK1 |= (1 << OCIE1A);                // Enable Timer1 output compare match interrupt
  sei();                                  // Re-enable interrupts

  period = _period;
}

void set_parameters(float _band, float _t_integral, float _t_derivative){
    
    band         = _band;
    t_integral   = _t_integral;
    t_derivative = _t_derivative;   
  }

void set_dac(int voltage_12bit){

  // Limit magnitude of voltage_12bit  
  if(abs(voltage_12bit) > 4095){
      voltage_12bit = sgn(voltage_12bit)*4095;
    }
    
  if(ENABLE_OUTPUT){
    
    // Check if a polarity change is needed
    if (sgn(dac_output) != sgn(voltage_12bit)){

      // Bring the dac output to zero temporarily for safe polarity change
      dac.setVoltage(0,false);

      // No need to change sign if we are turning the output off
      if(voltage_12bit == 0){ 
         dac_output = voltage_12bit;
         return;
      }

      // Flip the polarity pin accordingly
      if(voltage_12bit < 0) digitalWrite(POLARITY_PIN,HIGH);
      else                  digitalWrite(POLARITY_PIN,LOW);
    }

    // Set the dac to desired output
    dac.setVoltage(abs(voltage_12bit),false);
  }
  
  // Save the full signed output 
  dac_output = voltage_12bit;
}

void set_mode(MODES _mode){
    mode = _mode;
}

void set_setpoint(float _setpoint){
  /*
   * Set Temperature setpoint.
   */
  setpoint = _setpoint;
}

int get_dac(){
  return dac_output;
}

MODES get_mode(){
  return mode;
}

float get_temperature(){
  /* 
   *  Get the most recently measured temperature.
   */
  return temperature;
}

float get_setpoint(){
  /*
   * Get the current temperature setpoint.
   */
  return setpoint;
}

int get_period(){
  return period;
}

/*
 * Get a value from the pt1000 lookup table stored in 
 * program memory.
 * @param
 */
uint16_t get_pt1000(uint16_t i){
  return pgm_read_word_near( pt1000_table + i );
}

/*
 * Binary search to iteratively search for the closest resistance 
 * value in the lookup table that smaller than or equal to the 
 * supplied value. Converges in Log2(PT1000_TBL_SIZE) iterations.
*/
uint8_t find_resistance(uint16_t _r){
  
    uint8_t  lo = 0;
    uint8_t  hi = PT1000_TBL_SIZE - 1;
    uint8_t  mid;
    uint16_t table_val;

    // Main loop.
    do{
        mid = (hi + lo) >> 1;
        table_val = get_pt1000(mid);
        
        if (table_val > _r) hi = mid-1;
        
        else if(lo == mid){
               
          table_val = get_pt1000(hi);     
          if(table_val > _r) hi = lo;
          else               lo = hi;
        }
        else lo = mid;
    }while(hi-lo);
    
    return lo;
}

/*
 * Fast conversion of ADC measurement of RTD resistance to temperature (in °C)
 * via integer math and lookup table search. 
 */
float lookup_temperature(uint16_t _adc){
  
  uint32_t r_measured;
  uint16_t lookup, r_lookup, r_next;
  float    temp;

  // Multiply ADC reading into RREF, multiply by 10 since we want 10X pt1000 resistance.
  // NOTE: multiplication of two 16-bit vals, cast properly into 32-bit.
  r_measured = (uint32_t)(_adc) * 10 * (uint32_t)RREF; 

  // Divide (in integer fashion) by 2^15 (bit-depth of the MAX31865 ADC).
  r_measured = r_measured >> 15;

  // Find the index of the closest resistance to our measured val in the lookup table.
  lookup = find_resistance((uint16_t)r_measured);

  // Get the closest resistance and the next highest one (to be used for linear interpolation).
  r_lookup = get_pt1000(lookup);
  r_next   = get_pt1000(lookup+1);

  // Compute the floating point temperature, in all its glory.
  temp = TEMPERATURE_MIN + (float)lookup + (float)(r_measured -  r_lookup)/(r_next - r_lookup);

  return temp;
}

/*
 * Conversion of ADC measurement of RTD resistance to temperature (in °C)
 * via direct mathematical method.
 */
float calculate_temperature(uint16_t _adc){
  float Rt, temp;

  Rt = _adc;   // Convert 16-bit int to float
  Rt /= 32768; // Divide by ADC bitness (15-bit = 2**15 = 32768) 
  Rt *= RREF;  // Multiply by reference resistance to get the complete RTD resistance conversion   

  // Immediately check if RTD is below 0°C (resistance is below 1000 Ω)
  if(Rt < 1000){
    // 5th order polynomial fit for T < 0°C
    float rpoly = Rt;
    
    temp = -242.02;
    temp += 2.2228e-1 * rpoly;
    rpoly *= Rt; // square
    temp += 2.5859e-5 * rpoly;
    rpoly *= Rt; // ^3
    temp -= 4.8260e-9 * rpoly;
    rpoly *= Rt; // ^4
    temp -= 2.8183e-12 * rpoly;
    rpoly *= Rt; // ^5
    temp += 1.5243e-15 * rpoly;    

    return temp;
  }

  // Otherwise, proceed with quadratic solution for T > 0°C 
  temp = Z2 + (Z3 * Rt);
  temp = (sqrt(temp) + Z1) / Z4;
  
  return temp;
}
