/*
*Assignment: used to adapt to CR-TOUCH automatic Z-OFFSET acquisition module
*Author: Wang Yulong107051
*Date: 2022-12-01
*Version: V2.0
*Description: Use a combination of RC low-pass filtering + feature method trigger detection + rotation method result calculation to automatically obtain Z-OFFSET.
*Content includes nozzle wipe type, CR-TOUCH measurement, and pressure sensor measurement.
*Attention: During the migration process, users must ensure that all macro definitions are correct and running normally (the current macro definitions are based on Marlin 2.0.8.3).
*/


#ifndef __AUTO_OFFSET_H__
#define __AUTO_OFFSET_H__

#include "../inc/MarlinConfig.h"
#include "../MarlinCore.h"
#include "../module/probe.h"
#include "../module/motion.h"
#include "../module/planner.h"
#include "../module/stepper.h"
#include "../module/settings.h"
#include "../gcode/parser.h"
#include "../module/temperature.h"
#include "../HAL/shared/Delay.h"
// #include "../lcd/dwin/e3v2/dwin.h"
#include "../../src/feature/bedlevel/bedlevel.h"
#include "../../src/feature/babystep.h"
#include "../module/probe.h"

#include "stdio.h"
#include "string.h"
#include "../gcode/gcode.h"


#if ENABLED(USE_AUTOZ_TOOL_2)

#define FOR_LOOP_TIMES(lp, sVal, eVal, fun) for(int lp = sVal; lp < eVal; lp++) fun
#define CHECK_RANGE(val, min, max) ((val > min) && (val < max))
#define CHECK_AND_BREAK(bVal) if(bVal) break
#define CHECK_AND_RUN(bVal, fun) if(bVal) fun
#define CHECK_AND_RETURN(bVal, rVal) if(bVal) return rVal
#define CHECK_AND_RUN_AND_RETURN(bVal, fun, rVal) if(bVal) {fun;return rVal;}
#define CHECK_AND_RUN_AND_ELSE(bVal, fun1, fun2); if(bVal) {fun1;} else {fun2;}

#define ARY_MIN(min, ary, count) for(int i = 0; i < count; i++) {CHECK_AND_RUN(min > ary[i], min = ary[i];)}
#define ARY_MAX(max, ary, count) for(int i = 0; i < count; i++) {CHECK_AND_RUN(max < ary[i], max = ary[i];)}
#define ARY_AVG(avg, ary, count) for(int i = 0; i < count; i++) {avg += ary[i];}; avg /= count
#define ARY_MIN_INDEX(min, index, ary, count) for(int i = 0; i < count; i++) {CHECK_AND_RUN(min >= ary[i], {min = ary[i]; index = i;})}
#define ARY_SORT(ary, count) FOR_LOOP_TIMES(i, 0, count, FOR_LOOP_TIMES(j, i, count, { if(ary[i] > ary[j]){float t = ary[i]; ary[i] = ary[j]; ary[j] = t;}}));

#define PRINTF(str, ...)  {char strMsg[128] = {0}; snprintf(strMsg, sizeof(strMsg), str, __VA_ARGS__); SERIAL_PRINT_MSG(strMsg);}
#define RUN_AND_WAIT_GCODE_STR(gCode, isWait, ...)   {char cmd[128] = {0}; sprintf(cmd, gCode, __VA_ARGS__);PRINTF("\n***RUM GCODE CMD: %s***\n", cmd); RUN_AND_WAIT_GCODE_CMD(cmd, isWait);}
#define WAIT_BED_TEMP(maxTickMs, maxErr)    { unsigned int tickMs = GET_TICK_MS(); while (((GET_TICK_MS() - tickMs) < maxTickMs) && (abs(GET_BED_TAR_TEMP() - GET_BED_TEMP()) > maxErr)) MARLIN_CORE_IDLE();}
#define WAIT_HOTEND_TEMP(maxTickMs, maxErr) { unsigned int tickMs = GET_TICK_MS(); while (((GET_TICK_MS() - tickMs) < maxTickMs) && (abs(GET_HOTEND_TAR_TEMP(0) - GET_HOTEND_TEMP(0)) > maxErr)) MARLIN_CORE_IDLE();}


#define MIN_HOLD    2000    //Minimum threshold for trigger detection to prevent false triggering
#define MAX_HOLD    10000   //Maximum threshold for trigger detection to prevent over-triggering
#define RC_CUTE_FRQ 1     //The cutoff frequency of the RC filter is 0.1~10. The smaller the value = the more sensitive the trigger; the larger the value = the slower the trigger.
//The slower the speed, the smaller the cutoff frequency


/***The following macro definitions need to be implemented according to different versions of marlin***/
#define HX711_SCK_PIN                   PA4
#define HX711_SDO_PIN                   PC6
//Is there any printing information?
#define SHOW_MSG    0
//Pressure sensor installation position (corresponding to the position of the screw hole)
#define PRESS_XYZ_POS                   {AUTOZ_TOOL_X, AUTOZ_TOOL_Y, 0}
//The temperature expansion compensation of the nozzle, that is, the length of the nozzle extension when the temperature is 26 to 200 degrees
#define NOZ_TEMP_OFT_MM                 0.05
#define NOZ_AUTO_OFT_MM                 0.02 //0.04
//low pass filter coefficient
#define LFILTER_K1_NEW                  0.9f
//Taking the nozzle as the reference point 0, the installation position of cr touch
#define CRTOUCH_OFT_POS                 NOZZLE_TO_PROBE_OFFSET
//The x-direction size of the hot bed, in mm
#define BED_SIZE_X_MM                   X_BED_SIZE  //220
//Y-direction size of the hot bed, unit mm
#define BED_SIZE_Y_MM                   Y_BED_SIZE  //220
//The height of Z-axis lifting during the alignment process, unit: mm
#define HIGHT_UPRAISE_Z  4//8
//Wipe the coordinates of the nozzle
#define CLEAR_NOZZL_START_X  0
#define CLEAR_NOZZL_START_Y  15
#define CLEAR_NOZZL_END_X  0
#define CLEAR_NOZZL_END_Y  60
//Automatically set high number of repeats
#define ZOFFSET_REPEAT_NIN  1
#define ZOFFSET_REPEAT_NAX  2
#define ZOFFSET_COMPARE     0.05
#define ZOFFSET_VALUE_MIN   -5
#define ZOFFSET_VALUE_MAX   0
//Get the xyz coordinates of the current nozzle
#define GET_CURRENT_POS()               motion.position
//Detect whether the gcode instruction contains the given parameters
#define GET_PARSER_SEEN(c)              parser.seen(c)
//Get the value int type of the given parameter in the gcode instruction
#define GET_PARSER_INT_VAL()            parser.value_int()
//Get the value float of the given parameter in the gcode instruction
#define GET_PARSER_FLOAT_VAL()          parser.value_float()
//Print debugging information through the serial port
#define SERIAL_PRINT_MSG(msg)           {char* str = msg; while (*str != '\0') MYSERIAL1.write(*str++);} 
//Get system timestamp
#define GET_TICK_MS()                   millis()
//Delay us (microseconds)
#define TIME_DELAY_US(dUs)              DELAY_US(dUs)
//Marlin's idle() main loop
#define MARLIN_CORE_IDLE()              marlin.idle()
//Update watchdog
#define REFRESH_WATCHDOG()              {HAL_watchdog_refresh();}
//Block the execution of a gcode instruction
#define RUN_AND_WAIT_GCODE_CMD(cmd, isWait) do { planner.synchronize(); gcode.process_subcommands_now(F(cmd)); if (isWait) planner.synchronize(); } while (0)

//Set gpio working mode
#define GPIO_SET_MODE(pin, isOut)       {if((isOut)>0) SET_OUTPUT((pin)); else SET_INPUT_PULLUP((pin));}
//Set gpio output value
#define GPIO_SET_VAL(pin, val)          WRITE((pin), (val))
//Get gpio input value
#define GPIO_GET_VAL(pin)               READ((pin))

//Set nozzle temperature
#define SET_HOTEND_TEMP(temp, index)    thermalManager.setTargetHotend((temp), (index))
//Get the current temperature of the nozzle
#define GET_HOTEND_TEMP(index)          thermalManager.temp_hotend[(index)].celsius
//Get the nozzle target temperature
#define GET_HOTEND_TAR_TEMP(index)      thermalManager.temp_hotend[(index)].target
//Set heating bed temperature
#define SET_BED_TEMP(temp)              thermalManager.setTargetBed(temp)
//Get the current temperature of the heated bed
#define GET_BED_TEMP()                  thermalManager.temp_bed.celsius
//Get the heated bed target temperature
#define GET_BED_TAR_TEMP()              thermalManager.temp_bed.target
//Get the nozzle target temperature
#define GET_NOZZLE_TAR_TEMP(index)      thermalManager.temp_hotend[(index)].target
//Block and wait for the nozzle temperature to reach the target value
#define WAIT_NOZZLE_TEMP(index)         thermalManager.wait_for_hotend((index))
//Set the heating bed leveling enable state
#define SET_BED_LEVE_ENABLE(sta)        set_bed_leveling_enabled(sta)


//Get model cooling fan status
#define GET_FAN_SPD()                   fans[0].speed
//Set model cooling fan status 0~255
#define SET_FAN_SPD(sta)                thermalManager.set_fan_speed(0, (sta))

//Disable global interrupts, required when h x711 reads data
#define DISABLE_ALL_ISR()               hal.isr_off()
//Restore company-wide outage
#define ENABLE_ALL_ISR()                hal.isr_on()

//Xyze motor, requires a given number of steps per millimeter
#define STEPS_PRE_UNIT                  DEFAULT_AXIS_STEPS_PER_UNIT     //#define DEFAULT_AXIS_STEPS_PER_UNIT { 80, 80, 400, 424.9 }
//Z-axis motor moves forward one step
#define AXIS_Z_STEP_PLUS(dUs)           {Z_STEP_WRITE(!STEP_STATE_Z);TIME_DELAY_US((dUs));Z_STEP_WRITE(STEP_STATE_Z);TIME_DELAY_US((dUs));}
//The direction in which the Z-axis height increases
#define Z_DIR_ADD                       0
//The direction in which the Z-axis height decreases
#define Z_DIR_DIV                       (!Z_DIR_ADD)
//Z-axis motor direction setting, 1 is forward, 0 is backward
#define AXIS_Z_DIR_SET(sta)             Z_DIR_WRITE(sta)
//Z-axis motor direction reading
#define AXIS_Z_DIR_GET()                Z_DIR_READ()
//Z-axis motor enable
#define AXIS_Z_ENABLE()                 ENABLE_AXIS_Z()

//Detect whether the motor is running, return true to indicate that it is running, and return false to indicate that the operation is completed.
#define AXIS_XYZE_STATUS()              (planner.has_blocks_queued() || planner.cleaning_buffer_counter)    
//Set the current z-axis coordinate to the home point (0 point)
#define SET_NOW_POS_Z_IS_HOME()         {motion.set_axis_is_at_home(Z_AXIS);motion.sync_plan_position();}

//Use cr touch to measure the z value of a given point
#define PROBE_PPINT_BY_TOUCH(x, y)      probe.probe_at_point(x, y, PROBE_PT_RAISE, 0, false, true)
//Set z offset and save eeprom
// #define SET_Z_OFFSET(zOffset, isSave)   {dwin_zoffset = last_zoffset = probe.offset.z = zOffset; HMI_ValueStruct.offset_value = zOffset * 100;DWIN_UpdateLCD(); babystep.add_mm(Z_AXIS, zOffset);}
#define SET_Z_OFFSET(zOffset, isSave){ \
  probe.offset.z = zOffset; \
  babystep.add_mm(Z_AXIS, zOffset); \
  if(isSave) settings.save(); \
}

//Block and perform xy axis movement to the given position
#define DO_BLOCKING_MOVE_TO_XY(x_mm, y_mm, spd_mm_s)    motion.blocking_move_xy((x_mm), (y_mm), (spd_mm_s))
//Jam and perform z-axis motion to the given position
#define DO_BLOCKING_MOVE_TO_Z(z_mm, spd_mm_s)           motion.blocking_move_z((z_mm), (spd_mm_s))

#define DO_BLOCKING_MOVE_TO_XYZ(x_mm, y_mm, z_mm,spd_mm_s)   do{ \
    motion.position.set(x_mm, y_mm, z_mm); \
    motion.goto_current_position(spd_mm_s); \
    planner.synchronize(); \
  }while(0)
/***End***/

//RC high-pass filter is used to filter out low-frequency interference such as temperature changes, wire pulling, etc.
//Glitch filter to remove glitches in continuous data
//Low-pass filter to remove ultra-high frequency noise from connected data
class Filters
{
  public:
    static void hFilter(double *vals, int count, double cutFrqHz, double acqFrqHz);
    static void tFilter(double *vals, int count);
    static void lFilter(double *vals, int count, double k1New);
};

//H x711 chip driver for reading pressure sensor data
class HX711
{
public:
  void init(int clkPin, int sdoPin);
  int getVal(bool isShowMsg = 0);
  static bool ckGpioIsInited(int pin);
private:
  int clkPin;
  int sdoPin;
};

#define PI_COUNT 32

class ProbeAcq
{
  public:
    float baseSpdXY_mm_s;       //The preparation speed of the nozzle moving in the x and y planes
    float baseSpdZ_mm_s;        //The preparation speed of the nozzle moving in the z plane
    float minZ_mm;              //The stop position when moving towards the z-axis, that is, when no pressure change is detected when reaching this position, it will be forced to stop.

    float step_mm;              //Every time this distance is moved, the pressure sensor is read
    int   minHold;              //Minimum threshold, the last point of the trigger condition needs to be greater than this value
    int   maxHold;              //Maximum threshold. If the last point of the trigger condition is greater than this value, the trigger is forced.

    float outVal_mm;            //Output, the corresponding axis coordinate when triggered
    int   outIndex;             //Output, the corresponding sequence index when triggered. If the value is not in the (PI_COUNT*2/3, PI_COUNT-1) interval, the measurement is wrong and needs to be measured again.

    xyz_float_t basePos_mm;     //That is, the coordinates of the preparation position that the nozzle needs to reach before starting to measure this point.
    
    HX711 hx711;                //Point to acquisition function for CS123X or HX711
    ProbeAcq* probePointByStep();   //Test this against the parameter configuration of this class
    xyz_long_t readBase();      //Get clean data   
    bool checHx711();           //Check whether the pressure sensor is working properly
    void shakeZAxis(int times); //Vibrate the z-axis to eliminate gap stress
    static float probeTimes(int max_times, xyz_float_t rdy_pos, float step_mm, float min_dis_mm, float max_z_err, int min_hold, int max_hold);
  private:
    double valP[PI_COUNT * 2];  //The pressure value of the pressure saving sequence
    double posZ[PI_COUNT * 2];  //The corresponding coordinate values ​​of the pressure saving sequence
    
    void calMinZ();             //Calculate measurement results based on pressure saving sequence
    bool checkTrigger();        //Check whether the data in the pressure saving sequence meets the trigger conditions
};
char *getStr(float f);
void gcodeG212();
bool clearByBed(xyz_float_t rdyPos_mm, float norm, float minTemp, float maxTemp);
bool probeByPress(xyz_float_t rdyPos_mm, float* outZ);
bool probeByTouch(xyz_float_t rdyPos_mm, float* outZ);
bool getZOffset(bool nozzleClr, bool runProByPress, bool runProByTouch, float* outOffset);
#endif
#endif
