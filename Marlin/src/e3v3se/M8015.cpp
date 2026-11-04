/**
 * @file M8015.cpp
 * @author creality
 *
 * @version 0.1
 * @date 2021-12-15
 *
 * @copyright Copyright (c) 2021
 *
 */
#include "../gcode/gcode.h"
#include "../module/planner.h"
#include "../module/stepper.h"
#include "../module/probe.h"
// #include "../../../Configuration_adv.h"
#include "../feature/bedlevel/bedlevel.h"
#include "../feature/bedlevel/abl/bbl.h"
#include "AutoOffset.h"
#include "../lcd/dwin/creality/dwin.h"


/**
 *One key to obtain z-axis offset value
 */
void GcodeSuite::M8015()
{
  const bool wLevel = parser.seen('S') ? parser.value_bool() : true; // S0: Get Z offset without leveling; S1: Get Z offset with leveling
  // SERIAL_ECHOLNPGM("M8015: Trying to get Z offset value...");
  float zOffset = 0;
  if (motion.axis_is_trusted(Z_AXIS))
  {
    DISABLE_AXIS_Z();   // Release the z-axis motor. If not released, the second adjustment data will be abnormal and cannot be cleared.
  }
  // gcode.process_subcommands_now_P(PSTR("G28"));
  // probe.auto_get_offset(); //One-click high logic
  HMI_flag.leveling_offset_flag = true;
  HMI_flag.Pressure_Height_end = false;
  checkkey = ONE_HIGH;
  if (getZOffset(1, 1, 1, &zOffset))
  {
    for (int x = 0; x < GRID_MAX_POINTS_X; x++)
      for (int y = 0; y < GRID_MAX_POINTS_Y; y++)
        bedlevel.z_values[x][y] = 0;
    bedlevel.refresh_bed_level();
    settings.save(); // Commit the validated offset and the cleared mesh together.
    if (HMI_flag.Need_boot_flag) // Booting
    {
      HMI_flag.boot_step = Set_levelling; // Set the current step to the boot completion flag and save it
      // Save_Boot_Step_Value();//Save the boot boot steps
    }
    // else
    // {
    probe.offset.z = zOffset;
    // probe.offset.z -= NOZ_AUTO_OFT_MM; // Press down the final Z-axis compensation value by 0.02mm. Rock_20230516
    // TERN_(EEPROM_SETTINGS, settings.save());
    // TERN_(USE_AUTOZ_TOOL_2, DWIN_CompletedHeight());
    SERIAL_ECHOLNPGM("M8015 succeeded in getting Z offset.");
    SERIAL_ECHOLN("Z Offset: ", probe.offset.z);
    if (wLevel){

      HMI_flag.leveling_offset_flag = false;
      HMI_flag.Pressure_Height_end = true;

    }else{
    Goto_MainMenu();
    }
  }
  else // Failed against high
  {
    HMI_flag.leveling_offset_flag=false; //test failed
    DWIN_CalibrationFailed();
    SERIAL_ECHOLNPGM("M8015 failed to get Z offset.");
  }
}
