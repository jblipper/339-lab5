/**
 * Based on "Serial Input Basics" by user Robin2 on Arduino forums.
 * See https://forum.arduino.cc/t/serial-input-basics-updated/382007
 */

const char startMarker = '>';
const char delimiter   = ',';
const char endMarker   = '\n'; 

void receive_data() {
  static boolean recv_in_progress = false;
  static byte index = 0;
  char rc;
  
  while (Serial.available() > 0 && newData == false) {
    rc = Serial.read();
   
    if (recv_in_progress == true) {
      
      if (rc != endMarker) {
        received_data[index] = rc;
        index++;
        
        if (index >= data_size) {
          index = data_size - 1;
          // Send warning to user that data buffer is full.
        }
      }
      else {
        received_data[index] = '\0'; // terminate the string
        recv_in_progress = false;
        index = 0;
        newData = true;
        //Serial.println(received_data);
      }
    }

    else if (rc == startMarker) {
        recv_in_progress = true;
    }
  }
}

void parseData() {      
   strtok_index = strtok(temp_data,",");   // Get the first part - the string
   strcpy(functionCall, strtok_index);     // Copy it to function_call
   strtok_index = strtok(NULL, ",");

  if(strcmp(functionCall,"get_all")      == 0){
      write(time_control, delimiter);
      write(temperature,  delimiter);
      write(setpoint   ,  delimiter);
      write(dac_output ,  delimiter);
      write(get_period(), delimiter);
      write(u1,           delimiter);
      write(u2,           delimiter);
      write(u3,           endMarker);
  }

  else if(strcmp(functionCall,"set_dac")           == 0){ 
    int voltage_12bit = atoi(strtok_index);

    if(mode == OPEN_LOOP){
      set_dac(voltage_12bit);
      return;
    }
    Serial.println(F("Arduino must be in OPEN_LOOP mode in order to directly manipulate the dac output."));
  }

  else if(strcmp(functionCall,"get_pid")    == 0){
    write(band, delimiter);
    write(t_integral, delimiter);
    write(t_derivative, endMarker);   
  }
  
  else if(strcmp(functionCall,"set_pid")    == 0){
    float _band       = atof(strtok_index);     

    strtok_index      = strtok(NULL, ",");
    float _t_i        = atof(strtok_index);
    
    strtok_index      = strtok(NULL, ",");
    float _t_d        = atof(strtok_index);

    set_parameters(_band, _t_i, _t_d);
  }
  
  else if(strcmp(functionCall,"set_mode")          == 0){

    if(strcmp(strtok_index,"OPEN_LOOP")        == 0) set_mode(OPEN_LOOP);
    else if(strcmp(strtok_index,"CLOSED_LOOP") == 0) set_mode(CLOSED_LOOP);
    else                                             Serial.println("Invaild Mode.");
    return;
  }
  
  else if(strcmp(functionCall,"set_period")     == 0) set_period(atoi(strtok_index));
  
  else if(strcmp(functionCall,"set_setpoint")   == 0) set_setpoint(atof(strtok_index));    

  else if(strcmp(functionCall,"set_polyfit")    == 0) polyfit = atoi(strtok_index);
  
  else if(strcmp(functionCall,"get_polyfit")    == 0) Serial.println(polyfit);
  
  else if(strcmp(functionCall,"get_dac")        == 0) Serial.println(dac_output);

  else if(strcmp(functionCall,"get_mode")       == 0) Serial.println(MODE_NAMES[get_mode()]);
  
  else if(strcmp(functionCall,"get_temp")       == 0) Serial.println(temperature,2);

  else if(strcmp(functionCall,"get_setpoint")   == 0) Serial.println(setpoint,4);    

  else if(strcmp(functionCall,"get_period")     == 0) Serial.println(period);

  else if(strcmp(functionCall,"get_version")    == 0){
    Serial.print("Sketch version: ");
    Serial.print(SKETCH_VERSION);
    Serial.print(" (Compiled on ");
    Serial.print(__DATE__);
    Serial.println(")");
  }
  else if(strcmp(functionCall,"set_bias")              == 0) rtd.enableBias(atoi(strtok_index));
  else if(strcmp(functionCall,"get_MAX31865_config")   == 0) Serial.println(rtd.readRegister8(MAX31865_CONFIG_REG), BIN);
}

void write(float _data, char _termination){
  Serial.print(_data,3);
  Serial.print(_termination);
}
