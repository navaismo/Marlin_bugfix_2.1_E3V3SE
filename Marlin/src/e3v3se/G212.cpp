#include "../gcode/gcode.h"
#include "../module/planner.h"
#include "../module/stepper.h"
#include "../module/probe.h"
// #include "../../../Configuration_adv.h"
#include "../feature/bedlevel/bedlevel.h"
#include "../feature/bedlevel/abl/bbl.h"
#include "AutoOffset.h"
// #include "../lcd/dwin/e3v2/dwin.h"


/*
*Function Name: gcodeG212()
*Purpose: Used for the host computer to send test instructions, such as G212 C128 B P T, C128 = measure 128 times; B = perform head wipe operation; P = perform pressure sensor measurement operation; T = perform CR-TOUCH measurement operation
*Params: None
*Return: None
*/
void GcodeSuite::G212()
{
  int count = 1;
  if(GET_PARSER_SEEN('C')) count = GET_PARSER_INT_VAL();

  if(GET_PARSER_SEEN('H'))
  {
    HX711 hx711;
    hx711.init(HX711_SCK_PIN, HX711_SDO_PIN);
    FOR_LOOP_TIMES(i, 0, count, hx711.getVal(1)); 
    return;
  }

  if(GET_PARSER_SEEN('K'))
  {
    ProbeAcq pa;
    xyz_pos_t cp = PRESS_XYZ_POS;
    pa.hx711.init(HX711_SCK_PIN, HX711_SDO_PIN);
    pa.minZ_mm = -10;    //Drop up to 10mm
    pa.basePos_mm.x = cp.x;
    pa.basePos_mm.y = cp.y;
    pa.basePos_mm.z = 3;
    pa.baseSpdXY_mm_s = 100;        
    pa.baseSpdZ_mm_s = 5;
    pa.step_mm = 0.02;  //Rock             
    pa.minHold = MIN_HOLD;
    pa.maxHold = MAX_HOLD;
    pa.probePointByStep();
    return;
  }

  bool isRunClearNozzle = GET_PARSER_SEEN('B'); //Do you need to wipe the nozzle?
  bool isRunTestByPress = GET_PARSER_SEEN('P'); //Is it necessary to use a pressure sensor to measure the height of the nozzle?
  bool isRunTestByTouch = GET_PARSER_SEEN('T'); //Do I need to use CT touch to measure?
  float zOffset = 0;
  CHECK_AND_RUN((isRunClearNozzle || isRunTestByPress || isRunTestByTouch), FOR_LOOP_TIMES(i, 0, count, getZOffset(isRunClearNozzle, isRunTestByPress, isRunTestByTouch, &zOffset)));

}