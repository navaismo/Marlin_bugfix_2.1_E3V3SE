/**
 *Marlin 3D Printer Firmware
 *Copyright (c) 2020 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 *
 *Based on Sprinter and grbl.
 *Copyright (c) 2011 Camiel Gubbels /Erik van der Zalm
 *
 *This program is free software: you can redistribute it and/or modify
 *it under the terms of the GNU General Public License as published by
 *the Free Software Foundation, either version 3 of the License, or
 *(at your option) any later version.
 *
 *This program is distributed in the hope that it will be useful,
 *but WITHOUT ANY WARRANTY; without even the implied warranty of
 *MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *GNU General Public License for more details.
 *
 *You should have received a copy of the GNU General Public License
 *along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 */
#pragma once

/**
 *DWIN by Creality3D
 */

#include "./dwin_lcd.h"
#include "../common/encoder.h"
#include "../../../libs/BL24CXX.h"

#include "../../../inc/MarlinConfigPre.h"

#include "../../../libs/duration_t.h"

#if ANY(HAS_HOTEND, HAS_HEATED_BED, HAS_FAN) && PREHEAT_COUNT
  #define HAS_PREHEAT 1
  #if PREHEAT_COUNT < 2
    #error "Creality DWIN requires two material preheat presets."
  #endif
#endif

//Pause the feeding action before resuming.
//Pause the feeding action before resuming.
#define FEEDING_DEF_DISTANCE                10                // in material: default distance of feeding material
#define FEEDING_DEF_SPEED                   4                 // in material: default speed of feeding

#define LEVEL_DISTANCE   50  //One click to increase the retraction distance.
#define FEEDING_DEF_DISTANCE_1              15                /* in material: default distance of feeding materialdefault feeding distance */ 
#define IN_DEF_DISTANCE                 90               //Default feeding and discharging distance
// #define FEEDING_DEF_SPEED 5 //in material: default speed of feeding _MMS

#define FEED_TEMPERATURE 240  //Feed temperatureFeed temperature
#define EXIT_TEMPERATURE 240 //Discharge temperature
#define STOP_TEMPERATURE 140 //stop temperature

#if ENABLED(SHOW_GRID_VALUES)  //If the leveling value is displayed
  #define Flat_Color        0x7FE0  //Lawn green --> flat color
  #define Relatively_Flat   0x1C9F  //Dodge blue --> flatter color
  // #define Slope_Small 0xF81F //Magenta -->Small slope
  #define Slope_Small       0xFFE0  //Yellow --> small tilt 
  #define Slope_Big         0xF800  //Deep red --> large tilt
  
  #define  Select_Block_Color 0xFFE0 //Yellow color selected block color

  #define Slope_Big_Max        2.0  //Large slope upper boundary value
  #define Slope_Big_Min       -2.0  //Large slope lower boundary value
  #define Slope_Small_Max      1.0  //Small slope upper boundary value
  #define Slope_Small_Min     -1.0  //Small slope lower boundary value
  #define Relatively_Flat_Max  0.5  //flatter upper bound
  #define Relatively_Flat_Min -0.5  //flatter lower boundary value

                                    // Data between 0.5 and -0.5 represents flatness.


#endif
enum Auto_Hight_Stage:uint8_t{Nozz_Start,Nozz_Hot,Nozz_Clear,Nozz_Hight,Nozz_Finish};  //The four stages of one-click high-definition
enum processID : uint8_t {
  // Process ID
  MainMenu,
  SelectFile,
  Prepare,
  Control,
  Leveling,
  Level,
  PrintProcess,
  AxisMove,
  TemperatureID,
  Motion,
  Info,
  Pstats,
  Tune,
  #if HAS_PREHEAT
    PLAPreheat,
    TPUPreheat,
    PETGPreheat,
    ABSPreheat,
  #endif
  MaxSpeed,
  MaxSpeed_value,
  MaxAcceleration,
  MaxAcceleration_value,
  MaxJerk,
  MaxJerk_value,
  Step,
  Step_value,
#if ENABLED(DWIN_INPUT_SHAPING_MENU)  
  InputShaping,
  InputShaping_XFreq,
  InputShaping_XZeta,
  InputShaping_YFreq,
  InputShaping_YZeta,
#endif  
#if ENABLED(DWIN_SKEW_MENU)  
  SkewCorrection,
  skewxy_dac,
  skewxy_dbd,
  skewxy_sad,
#endif
#if ENABLED(DWIN_CUSTOM_EXTRUDE)
  CExtrude_Menu,
  custom_extrude_temp,
  custom_extrude_length,
#endif  
  Display_Menu,
  
#if ENABLED(DWIN_DIMM_MENU)  
  Max_LCD_Bright,
  Dimm_Bright,
  DimmTime,
#endif  
  ZHeight,
  HomeOff,
  HomeOffX,
  HomeOffY,
  HomeOffZ,

  // Last Process ID
  Last_Prepare,

  // Advance Settings  //20210724 _rock
  AdvSet,
  ProbeOff,
  ProbeOffX,
  ProbeOffY,

  // Back Process ID
  Back_Main,
  Back_Print,

  // Date variable ID
  Move_X,
  Move_Y,
  Move_Z,
  #if HAS_HOTEND
    Extruder,
    ETemp,
    EFlow,
  #endif
  Homeoffset,
  #if HAS_HEATED_BED
    BedTemp,
  #endif
  #if HAS_FAN
    FanSpeed,
  #endif
  PrintSpeed,

  // Window ID
  Print_window,
  Filament_window,
  Popup_Window,
  // remove card screen
  Remove_card_window,
  Show_gcode_pic,
  Selectlanguage,
  Poweron_select_language,
  HM_SET_PID,            // Set pid manually
  AUTO_SET_PID,          // Automatically set pid
  AUTO_SET_NOZZLE_PID,   // Automatically set nozzle pid
  AUTO_SET_BED_PID,      // Automatically set the hotbed pid
  HM_PID_Value,          // Manual pid value
  AUTO_PID_Value,        // automatic pid value
  PID_Temp_Err_Popup,    // Pid temperature abnormal pop-up window
  AUTO_IN_FEEDSTOCK, //Automatic feeding
  AUTO_OUT_FEEDSTOCK, //Automatic return
  Level_Value_Edit,  //Edit leveling data
  Change_Level_Value, //Change leveling value
  ONE_HIGH, //Highlight the page with one click
  POPUP_CONFIRM,//Pop-up window confirmation interface
  Max_GUI, 
  M117Info,
#if ENABLED(DWIN_RENDER_THUMBNAIL)
  ThumbPrint,
  ThumbTune,
  ThumbPrintSpeed,
  ThumbETemp,
  ThumbEFlow,
  ThumbBedTemp,
  ThumbFanSpeed,
  ThumbHomeoffset,
  ThumbPrint_window,
#endif
};

enum DC_language{
  Chinese   = 2, /*Chinese*/
  English   = 4, /*English*/
  German    = 6, /*German*/
  Russian   = 9, /*Russian*/
  French    = 12, /*French*/
  Turkish   = 15, /*turkish*/
  Spanish   = 17, /*spanish*/
  Italian   = 19, /*Italian*/
  Portuguese= 21, /*Portuguese*/
  Japanese = 23,  /*Japanese*/
  Korean   = 25,  /*Korean*/
  Language_Max    /*language boundary value*/
};
//Boot steps
#define LANGUAGE_TOTAL 11  //total number of languages
enum DC_Boot_Step{
  Set_language,    //Set language
  Set_high,        //Set the height
  Set_levelling,   //Set up the leveling interface
  Boot_Step_Max    /*Boot boot boundary value*/
};
//Boot boot pop-up interface
enum DWIN_Poupe{
  Clear_nozz_bed,//Tips for cleaning nozzles and heat bed
  High_faild_clear,//For high failure, please clean the nozzle and heat bed
  Level_faild_QR, //If leveling fails, please scan the QR code to get the solution.
  Boot_undone,  //Boot is not completed
  CRTouch_err,  //Cr touch is abnormal,
  UnknownError, // Used for future MarlinUI integration
};
extern enum DC_language current_language;
// Picture ID
#define Background_ICON     27//12 //Background image ID 27-31 =256*5KB
#define Start_Process       0   // splash screen image
#define Auto_Set_Nozzle_PID 1   // Automatically set nozzle pid
#define Auto_Set_Bed_PID    2   // Automatically set the hotbed pid

#define Background_min  4 //03
#define Background_max  42//53//53 + 50
#define Background_reset 43 //Factory reset
#define BG_PRINTING_CIRCLE_MIN 145 //Printing progress bar 0%
#define BG_PRINTING_CIRCLE_MAX 245 //Printing progress bar 100%

#define BG_NOZZLE_MIN  104
#define BG_NOZZLE_MAX  118//123
#define BG_BED_MIN     125 
#define BG_BED_MAX     139//144
// ICON ID
#define ICON                       0 //2//13
#define ICON_LOGO                  0
#define ICON_Print_0               1
#define ICON_Print_1               2
#define ICON_Prepare_0             3
#define ICON_Prepare_1             4
#define ICON_Control_0             5
#define ICON_Control_1             6
#define ICON_Leveling_0            7
#define ICON_Leveling_1            8
#define ICON_HotendTemp            9
#define ICON_BedTemp              10
#define ICON_Speed                11
#define ICON_Zoffset              12
#define ICON_Back                 13
#define ICON_File                 14
#define ICON_PrintTime            15
#define ICON_RemainTime           16
#define ICON_Setup_0              17
#define ICON_Setup_1              18
#define ICON_Pause_0              19
#define ICON_Pause_1              20
#define ICON_Continue_0           21
#define ICON_Continue_1           22
#define ICON_Stop_0               23
#define ICON_Stop_1               24
//#define ICON_Bar                  25
#define ICON_More                 26

#define ICON_Axis                 27
#define ICON_CloseMotor           28
#define ICON_Homing               29
#define ICON_SetHome              30
#define ICON_PLAPreheat           31
#define ICON_ABSPreheat           32
#define ICON_Cool                 33
#define ICON_Language             34

#define ICON_MoveX                35
#define ICON_MoveY                36
#define ICON_MoveZ                37
#define ICON_Extruder             38
#define ICON_Alignheight          39

#define ICON_Temperature          40
#define ICON_Motion               41
#define ICON_WriteEEPROM          42
#define ICON_ReadEEPROM           43
#define ICON_ResumeEEPROM         44
#define ICON_Info                 45

#define ICON_SetEndTemp           46
#define ICON_SetBedTemp           47
#define ICON_FanSpeed             48
#define ICON_SetPLAPreheat        49
#define ICON_SetABSPreheat        50

#define ICON_MaxSpeed             51
#define ICON_MaxAccelerated       52
#define ICON_MaxJerk              53
#define ICON_Step                 54
#define ICON_PrintSize            55
#define ICON_Version              56
#define ICON_Contact              57
#define ICON_StockConfiguraton    58
#define ICON_MaxSpeedX            59
#define ICON_MaxSpeedY            60
#define ICON_MaxSpeedZ            61
#define ICON_MaxSpeedE            62
#define ICON_MaxAccX              63
#define ICON_MaxAccY              64
#define ICON_MaxAccZ              65
#define ICON_MaxAccE              66
#define ICON_MaxSpeedJerkX        67
#define ICON_MaxSpeedJerkY        68
#define ICON_MaxSpeedJerkZ        69
#define ICON_MaxSpeedJerkE        70
#define ICON_StepX                71
#define ICON_StepY                72
#define ICON_StepZ                73
#define ICON_StepE                74
#define ICON_Setspeed             75
#define ICON_SetZOffset           76
//#define ICON_Rectangle 77 //Manually drawn rectangle replacement
#define ICON_BLTouch              78
#define ICON_TempTooLow           79  //The nozzle or heating bed temperature is too low
//#define ICON_AutoLeveling 80
#define ICON_TempTooHigh          81  //The nozzle or heating bed temperature is too high
#define ICON_Hardware_version     82   // Hardware version small icon
#define ICON_LEVELING_ERR         83   // Leveling failed
#define ICON_HIGH_ERR             84    //Failed against high


//#define ICON_Continue_E 85 //OK English button

//#define ICON_Cancel_C 86 //Cancel Chinese button
//#define ICON_Cancel_E 87 //Cancel English button
//#define ICON_Confirm_C 88 //Confirm Chinese button
//#define ICON_Confirm_E 89 //Confirm English button
//#define ICON_Info_0 90
//#define ICON_Info_1 91
//#define ICON_Power_On_Home_C 92 //ICON_Degree 92

//#define ICON_Card_Remove_C 93 //Chinese prompt for card removal
//#define ICON_Card_Remove_E 94 //English prompt for card removal

#define ICON_HM_PID               95
#define ICON_Auto_PID             96
#define ICON_Feedback             97
#define ICON_Level_ERR_QR_CH     98   //
#define ICON_Level_ERR_QR_EN     99
#define ICON_HM_PID_NOZZ_P       100
#define ICON_HM_PID_NOZZ_I       101
#define ICON_HM_PID_NOZZ_D       102
#define ICON_HM_PID_Bed_P        103
#define ICON_HM_PID_Bed_I        104
#define ICON_HM_PID_Bed_D        105
// The numbers here correspond to the pictures
#define ICON_Auto_PID_Nozzle     106 // Automatically set the nozzle pid curve
#define ICON_Auto_PID_Bed        107 // Automatically set the heating bed pid curve
#define ICON_Edit_Level_Data      108 //Edit leveling data

#define ICON_Defaut_Image        143

#define ICON_Word_CN 150
#define ICON_Word_EN 151
#define ICON_Word_FR 152
#define ICON_Word_PT 153
#define ICON_Word_TR 154
#define ICON_Word_DE 155
#define ICON_Word_ES 156
#define ICON_Word_IT 157
#define ICON_Word_PYC 158
#define ICON_Word_JP 159

#define ICON_Word_KOR 160  //Korean

#define ICON_OUT_STORK 166  //Feed small icon
#define ICON_IN_STORK 167 //Return small icon
#define ICON_STORKING_TIP 168 //Feeding prompt
#define ICON_STORKED_TIP  169 //Feed completion prompt
#define ICON_OUT_STORKING_TIP 170 //Tips for returning materials
#define ICON_OUT_STORKED_TIP 171  //Return completion prompt
//166-172 One click to match small icons with high logic
#define ICON_NOZZLE_HIGH 172   //finish high
#define ICON_NOZZLE_HIGH_HOT 173 //Not high
#define ICON_NOZZLE_HEAT 174   //Heating completed
#define ICON_NOZZLE_HEAT_HOT 175 //unheated
#define ICON_NOZZLE_CLEAR 176    //Nozzle cleaning does not start
#define ICON_NOZZLE_CLEAR_HOT 177 //Nozzle cleaning completed
#define ICON_NOZZLE_LINE 178  //One-click high connection line
#define ICON_LEVEL_CALIBRATION_OFF 179//Leveling calibration off
#define ICON_LEVEL_CALIBRATION_ON  180 //Leveling and calibration on


#define ICON_FLAG_MAX 181

/* LANGUAGE ID Chinese*/
  #define LANGUAGE_ID              4//14
  // Main
  #define LANGUAGE_Main             1
  #define LANGUAGE_Print_0          2
  #define LANGUAGE_Prepare_0        3
  #define LANGUAGE_Control_0        4
  #define LANGUAGE_Info_0           5
  #define LANGUAGE_Stop_0           6
  #define LANGUAGE_Pause_0          7
  #define LANGUAGE_Print_1          8
  #define LANGUAGE_Prepare_1        9
  #define LANGUAGE_Control_1        10
  #define LANGUAGE_Info_1           11
  #define LANGUAGE_Stop_1           12
  #define LANGUAGE_Pause_1          13
  #define LANGUAGE_Level_0          14
  #define LANGUAGE_Level_1          15
 // Printing
  #define LANGUAGE_Zoffset          16
  #define LANGUAGE_Setup            17
  #define LANGUAGE_PrintTime        18
  #define LANGUAGE_PrintSpeed       19
  #define LANGUAGE_Printing         20
  #define LANGUAGE_Back             21
  #define LANGUAGE_Fan              22
  #define LANGUAGE_Hotend           23
  #define LANGUAGE_Bedend           24
  #define LANGUAGE_RemainTime       25
  #define LANGUAGE_SelectFile       26
  #define LANGUAGE_Pausing          27
  // Control
  #define LANGUAGE_Store            28
  #define LANGUAGE_Read             29
  #define LANGUAGE_Reset            30
  #define LANGUAGE_Temp             31
  #define LANGUAGE_Motion           32
  #define LANGUAGE_Motion_Title     33
  // Prepare
  #define LANGUAGE_ABS              34
  #define LANGUAGE_PLA              35
  #define LANGUAGE_Home             36
  // #define LANGUAGE_SetHome       37
  #define LANGUAGE_info_new         37
  #define LANGUAGE_CloseMotion      38
  #define LANGUAGE_Move_Title       39
  #define LANGUAGE_Prepare          40
  #define LANGUAGE_Cool             41
  // Move
  #define LANGUAGE_MoveX            42
  #define LANGUAGE_MoveY            43
  #define LANGUAGE_MoveZ            44
  #define LANGUAGE_MoveE            45
  #define LANGUAGE_Move             46
  // Temperpare
  #define LANGUAGE_PLASetup         47
  #define LANGUAGE_ABSSetup         48
  #define LANGUAGE_Temp_Title       49
  // Motion
  #define LANGUAGE_X                50
  #define LANGUAGE_Y                51
  #define LANGUAGE_Z                52
  #define LANGUAGE_E                53
  #define LANGUAGE_Step             54
  #define LANGUAGE_Acc              55
  #define LANGUAGE_Corner           56
  #define LANGUAGE_MaxSpeed         57
  // Info
  #define LANGUAGE_Version          58
  #define LANGUAGE_Size             59
  #define LANGUAGE_Contact          60
  #define LANGUAGE_Info             61
  // Preheat Configuration
  #define LANGUAGE_PLASetup_Title   62
  #define LANGUAGE_PLASetupSave     63
  #define LANGUAGE_ABSSetup_Title   64
  #define LANGUAGE_ABSSetupSave     65
  // Language
  #define LANGUAGE_language         66
  // Popup Window
  #define LANGUAGE_FilamentLoad     67
  #define LANGUAGE_FilamentUseup    68
  #define LANGUAGE_TempLow          69   // Nozzle temperature is too low
  #define LANGUAGE_PowerLoss        70
  #define LANGUAGE_TempHigh         71
  #define LANGUAGE_Cancel           72   // Cancel button
  #define LANGUAGE_Confirm          73   // OK button
  #define LANGUAGE_Homing           74
  #define LANGUAGE_waiting          75
  #define LANGUAGE_PausePrint       76
  #define LANGUAGE_StopPrint        77
  // Add
  #define LANGUAGE_Setup_0          78
  #define LANGUAGE_Setup_1          79
  #define LANGUAGE_Control          80
  #define LANGUAGE_Finish           81
  #define LANGUAGE_PrintFinish      82   // OK button
  #define LANGUAGE_Card_Remove_JPN  83
  #define LANGUAGE_Homeing          84
  #define LANGUAGE_leveing          85

#define LANGUAGE_mjerk_title        86
#define LANGUAGE_ratio_title        87
#define LANGUAGE_mspeed_title       88
#define LANGUAGE_maccel_title       89
// new_add rock_202220302
#define LANGUAGE_recard_OK          90   // Remove card OK button
#define LANGUAGE_align_height       91   // One click to match height
#define LANGUAGE_filament_cancel    92   // Material break recovery stop button
#define LANGUAGE_keep_print_0       93
#define LANGUAGE_keep_print_1       94
#define LANGUAGE_print_stop         95   // stop button
#define LANGUAGE_Powerloss_go       96   // Continue printing button after power failure
// 20220819 rock_add
//#define LANGUAGE_Laser_switch 97 //Switch laser engraving
#define LANGUAGE_PID_Manually       98   // Set pid manually
#define LANGUAGE_Auto_PID           99   // Automatically set PID
// PLA settings
#define LANGUAGE_PLA_FAN              100
#define LANGUAGE_PLA_NOZZLE           101
#define LANGUAGE_PLA_BED              102
// Abs settings
#define LANGUAGE_ABS_NOZZLE           103
#define LANGUAGE_ABS_BED              104
#define LANGUAGE_ABS_FAN              105

// maximum speed
#define LANGUAGE_MAX_SPEEDX          107
#define LANGUAGE_MAX_SPEEDY          108
#define LANGUAGE_MAX_SPEEDZ          109
#define LANGUAGE_MAX_SPEEDE          110
// maximum acceleration
#define LANGUAGE_MAX_ACCX          112
#define LANGUAGE_MAX_ACCY          113
#define LANGUAGE_MAX_ACCZ          114
#define LANGUAGE_MAX_ACCE          115
// maximum corner speed
#define LANGUAGE_MAX_CORNERX          117
#define LANGUAGE_MAX_CORNERY          118
#define LANGUAGE_MAX_CORNERZ          119
#define LANGUAGE_MAX_CORNERE          120

#define LANGUAGE_Auto_Set_Bed_PID     116  // Automatically set the hotbed pid
#define LANGUAGE_Auto_Set_Nozzle_PID  121  // Automatically set nozzle pid

#define LANGUAGE_Step_Per_X       122  // Transmission ratiox
#define LANGUAGE_Step_Per_Y       123  // Transmission ratio y
#define LANGUAGE_Step_Per_Z       124  // Transmission ratio z
#define LANGUAGE_Step_Per_E       125  // Transmission ratio e

#define LANGUAGE_Title_Feedback   111 // Feedback
#define LANGUAGE_Feedback         126 // Feedback
// Image preview text -needs to be added
#define LANGUAGE_Estimated_Time      127  // Estimated time
#define LANGUAGE_Filament_Used       128  // Material length
#define LANGUAGE_Layer_Height        129  // Floor height
#define LANGUAGE_Volume              130  // volume

// Pid settings
#define LANGUAGE_Set_PID_Manually   131  // Set pid manually
#define LANGUAGE_Nozz_P             132  // Nozzle p value
#define LANGUAGE_Nozz_I             133  // Nozzle i value
#define LANGUAGE_Nozz_D             134  // Nozzle d value
#define LANGUAGE_Bed_P              135  // Hotbed p-value
#define LANGUAGE_Bed_I              136  // Heating bed i value
#define LANGUAGE_Bed_D              137  // Heating bed d value
#define LANGUAGE_Set_Auto_PID       138  // automatic pid

#define LANGUAGE_Title_Language     106  // language title
//#define LANGUAGE_Fun_LANGUAGE 139 //Language title
#define LANGUAGE_Bed_LOW            140  // Heating bed temperature is too low
#define LANGUAGE_Bed_HIGH           141  // Heating bed temperature is too high

#define LANGUAGE_Auto_PID_ING       142  // Automatic pid detection is in progress
#define LANGUAGE_Auto_PID_END       143  // Automatic pid detection completed
#define LANGUAGE_Auto_NOZZ_EX       144  // Automatic pid detection completed
#define LANGUAGE_Auto_BED_EX        145  // Automatic pid detection completed

#define LANGUAGE_Auto_Set_Nozzle_PID_Title  146  // Automatically set nozzle pid
#define LANGUAGE_Auto_Set_Bed_PID_Title     147  // Automatically set the hotbed pid
#define LANGUAGE_IN_STORK  148  //Feed entry
#define LANGUAGE_OUT_STORK 149  //Return entry
#define LANGUAGE_STORKING_TIP1  150 //Tip 1 while feeding
#define LANGUAGE_OUT_STORKING_TIP2 151 //Tip 1 when returning materials
#define LANGUAGE_STORKING_TIP2 152 //Prompt for feeding during feeding
#define LANGUAGE_OUT_STORKED_TIP2 153 //Return completion prompt
#define LANGUAGE_IN_TITLE   154 //Feed title
#define LANGUAGE_OUT_TITLE 155 //Return title
#define LANGUAGE_Hardware_Version 156 //Hardware version entry
#define LANGUAGE_Level_Calibration 157 //Print calibration entry
#define LANGUAGE_HIGH_ERR_CLEAR    158  //Please clean on high failure
#define LANGUAGE_CLEAR_HINT       159 //Tips for cleaning nozzles and platforms
#define LANGUAGE_SCAN_QR          160 //Scan the QR code to get the solution
#define LANGUAGE_BOOT_undone      161 // Boot is not completed
#define LANGUAGE_CRTouch_error      162 // Cr touch is abnormal, please contact customer service

#define LANGUAGE_LEVELING_EDIT     189  //Leveling data edit button
#define LANGUAGE_LEVELING_CONFIRM  190  //Leveling OK button
#define LANGUAGE_EDIT_LEVEL_DATA   191 //Edit leveling data
#define LANGUAGE_EDIT_DATA_TITLE   192 //Edit leveling data title
#define LANGUAGE_LEVEL_FINISH      193 //Leveling completion entry
#define LANGUAGE_LEVEL_ERROR       194 //Leveling failed entry
#define LANGUAGE_LEVEL_EDIT_DATA   195 //Edit leveling data title
#define LANGUAGE_AUTO_HIGHT_TITLE  196 //to high school
#define LANGUAGE_NOZZLE_HOT        197  //Nozzle heating
#define LANGUAGE_NOZZLE_CLRAR  198  //Nozzle cleaning
#define LANGUAGE_NOZZLE_HIGHT  199  //Nozzle height

#define ICON_AdvSet               ICON_Language
#define ICON_HomeOff              ICON_AdvSet
#define ICON_HomeOffX             ICON_StepX
#define ICON_HomeOffY             ICON_StepY
#define ICON_HomeOffZ             ICON_StepZ
#define ICON_ProbeOff             ICON_AdvSet
#define ICON_ProbeOffX            ICON_StepX
#define ICON_ProbeOffY            ICON_StepY
#define ICON_PIDNozzle            ICON_SetEndTemp
#define ICON_PIDbed               ICON_SetBedTemp

/**
 *3-.0：The font size, 0x00-0x09, corresponds to the font size below:
 *0x00=6*12   0x01=8*16   0x02=10*20  0x03=12*24  0x04=14*28
 *0x05=16*32  0x06=20*40  0x07=24*48  0x08=28*56  0x09=32*64
 */
#define font6x12  0x00
#define font8x16  0x01
#define font10x20 0x02
#define font12x24 0x03
#define font14x28 0x04
#define font16x32 0x05
#define font20x40 0x06
#define font24x48 0x07
#define font28x56 0x08
#define font32x64 0x09

// Color  FE29
#define Color_White       0xFFFF
#define Color_Yellow      0xFE29
#define Color_Blue        0x19FF
#define Color_Red         0xF44F
#define Color_Bg_Window   0x31E8  // Popup background color
#define Color_Bg_Blue     0x1145  // Dark blue background color
#define Color_Bg_Black    0x0841  // Black background color
#define Color_Bg_Red      0xF00F  // Red background color
#define Popup_Text_Color  0xD6BA  // Popup font background color
#define Line_Color        0x3A6A  // Split line color
#define Rectangle_Color   0xFE29//0xEE2F  //Blue square cursor color
#define Percent_Color     0xFE29  // Percentage color
#define BarFill_Color     0x10E4  // Fill color of progress bar
#define Select_Color      0x33BB  // Selected color
#define Button_Select_Color 0xFFFF  // Selected color
#define All_Black         0x0000  // Selected color

extern bool Show_Default_IMG;
extern volatile uint8_t checkkey;
extern float zprobe_zoffset;
extern char print_filename[16];
extern int16_t temphot;
extern uint8_t afterprobe_fan0_speed;
extern bool home_flag;
extern bool G29_flag;

extern millis_t dwin_heat_time;
extern float dwin_zoffset;
extern float last_zoffset;


typedef struct 
{
  #if ENABLED(HAS_HOTEND)
    celsius_t E_Temp = 0;
    int16_t E_Flow = 0;
    int16_t Extrusion_Length = 0;
    int16_t LCD_MaxBright  = MAX_SCREEN_BRIGHTNESS;
    int16_t LCD_DimmBright = DIMM_SCREEN_BRIGHTNESS;
    uint8_t Dimm_Time = TURN_OFF_TIME;
    #if ENABLED(DWIN_ZHOME_MENU)
      uint8_t Z_height = CZ_AFTER_HOMING;
    #else
      uint8_t Z_height = 10;
    #endif

  #endif
  #if ENABLED(HAS_HEATED_BED)
    celsius_t Bed_Temp = 0;
  #endif
  #if ENABLED(HAS_FAN)
    int16_t Fan_speed = 0;
  #endif
  int16_t print_speed     = 100;
  float Max_Feedspeed     = 0;
  float Max_Acceleration  = 0;
  float Max_Jerk_scaled   = 0;
  float Max_Step_scaled   = 0;
  float Move_X_scaled     = 0;
  float Move_Y_scaled     = 0;
  float Move_Z_scaled     = 0;
  float InputShaping_scaled = 0;
  uint8_t Curve_index = 0;
  uint16_t Auto_PID_Temp  = 0;
  uint16_t Auto_PID_Value[3] = {0, 100, 260}; // 1: Hot bed temperature; 2 Nozzle temperature
  float HM_PID_Temp_Value  = 0;
  float Temp_Leveling_Value=0;
  float HM_PID_Value[7]  = {0,DEFAULT_KP,DEFAULT_KI,DEFAULT_KD,DEFAULT_BED_KP,DEFAULT_BED_KI,DEFAULT_BED_KD};
  #if HAS_HOTEND
    float Move_E_scaled   = 0;
  #endif
  float offset_value      = 0;
  int8_t show_mode        = 0; // -1: Temperature control    0: Printing temperature
  float Home_OffX_scaled  = 0;
  float Home_OffY_scaled  = 0;
  float Home_OffZ_scaled  = 0;
  float Probe_OffX_scaled = 0;
  float Probe_OffY_scaled = 0;
} HMI_value_t;

#define DWIN_CHINESE 123
#define DACAI_JAPANESE 124
#define DWIN_ENGLISH 0

typedef struct {
  uint8_t boot_step;  //Boot steps
  uint8_t language;   //language
  uint8_t g_code_pic_sel;
  bool pause_flag:1;
  bool pause_action:1;
  bool print_finish:1;
  bool done_confirm_flag:1;
  bool select_flag:1;
  bool home_flag:1;
  bool heat_flag:1;               // 0: heating done  1: during heating
  bool cutting_line_flag:1;       // Material break detection flag
  bool filement_resume_flag:1;    // Whether the local material outage state has been restored, 0: has been restored, and can receive cloud instructions; 1: is still in the material shortage state, and cannot receive cloud control instructions.
  bool remove_card_flag:1;        // Card removal detection flag
  bool flash_remain_time_flag:1;  // Refresh the remaining time flag
  bool online_pause_flag:1;       // The online printing pause command flag bit solves the problem of pause in the middle of double-material printing and requires manual resumption of printing.
  bool disallow_recovery_flag:1;  // Data recovery not allowed flag
  bool cloud_printing_flag:1;     // Cloud printing logo
  bool power_back_to_zero_flag:1; // Power-on zero return flag
  bool disable_queued_cmd :1;     // Cloud printing is prohibited from responding to gcode commands after the material is interrupted.
  bool filament_recover_flag :1;  // Material break detection recovery flag bit
  bool PID_autotune_start :1;     // Automatic pid start
  bool PID_autotune_end :1;       // Automatic pid end
  bool Refresh_bottom_flag:1;    //Refresh the bottom parameter flag 1 does not refresh, 0 needs to be refreshed
  bool Auto_inout_end_flag:1;  //Automatic feeding and unloading completion mark
  bool Level_check_flag:1; //Leveling calibration mark
  bool Level_check_start_flag:1; //Leveling calibration mark
  bool Need_g29_flag:1; //Requires g29 flag
  bool Need_boot_flag:1; //Need to set the high flag
  bool abort_end_flag:1; //Customize stop printing flag
  #if ENABLED(PREVENT_COLD_EXTRUSION)
    bool ETempTooLow_flag:1;
  #endif
  #if HAS_LEVELING
    bool leveling_offset_flag:1;   //Leveling the high mark
    bool Pressure_Height_end :1;   //One click to start with high flag 1 
    bool G29_finish_flag     :1;
    bool G29_level_not_normal    :1; //This leveling is normal
    bool Edit_Only_flag      :1; 
    bool local_leveling_flag :1;   //local leveling flag
    bool leveling_edit_home_flag :1; //Whether the leveling editing page has been returned to zero is completed
    bool cr_touch_error_flag :1; //Cr touch error flag
  #endif
  AxisEnum feedspeed_axis, acc_axis, jerk_axis, step_axis;
  uint8_t HM_PID_ROW,Auto_PID_ROW;
  uint8_t PID_ERROR_FLAG;
  uint8_t High_Status;
} HMI_Flag_t;

extern HMI_value_t HMI_ValueStruct;
extern HMI_Flag_t HMI_flag;
extern bool end_flag; //Prevent repeated refresh of curve completion instructions
// Show ICO
void ICON_Print(bool show);
void ICON_Prepare(bool show);
void ICON_Control(bool show);
void ICON_Leveling(bool show);
void ICON_StartInfo(bool show);

void ICON_Setting(bool show);
// void ICON_Pause(bool show);
// void ICON_Continue(bool show);
void ICON_Pause();
void ICON_Continue();
void ICON_Stop(bool show);

#if HAS_HOTEND || HAS_HEATED_BED
  // Popup message window
  void DWIN_Popup_Temperature(const bool toohigh);
  void DWIN_Popup_Temperature(const bool toohigh,int8_t Error_id);
#endif

#if HAS_HOTEND
  void Popup_Window_ETempTooLow();
#endif

void Popup_Window_Resume();
void Popup_Window_Home(const bool parking=false);
void Popup_Window_Leveling();

void Goto_PrintProcess();
void Goto_MainMenu();
void Goto_ThumbPrint();

#if ENABLED(OCTOPRINT_PLUGIN)
  void Goto_ThumbFinish();
  void DWIN_OctoUpdate();
  void Clear_Thumb_UpperArea();
  //octo imagemap
  #define OctoIMAGE_WIDTH 96
  // Buffer to hold one line of the image
  extern uint16_t OctoImageLine[OctoIMAGE_WIDTH];
  extern char title[50];
  void Draw_OctoTitle(const char *const title);
  void DWIN_RenderOctoTitle();
  void initializeImageMap();
  void DWIN_RenderOctoLine(uint16_t y);
#endif
// Variable control
void HMI_Move_X();
void HMI_Move_Y();
void HMI_Move_Z();
void HMI_Move_E();

void HMI_Zoffset();

#if ENABLED(HAS_HOTEND)
  void HMI_ETemp();
#endif
#if ENABLED(HAS_HEATED_BED)
  void HMI_BedTemp();
#endif
#if ENABLED(HAS_FAN)
  void HMI_FanSpeed();
#endif

void HMI_PrintSpeed();

void HMI_MaxFeedspeedXYZE();
void HMI_MaxAccelerationXYZE();
void HMI_MaxJerkXYZE();
void HMI_StepXYZE();


void DWIN_Draw_Signed_Float(uint8_t size, uint16_t bColor, uint8_t iNum, uint8_t fNum, uint16_t x, uint16_t y, long value);

// SD Card
void HMI_SDCardInit();
void HMI_SDCardUpdate();

// Main Process
void Icon_print(bool value);
void Icon_control(bool value);
void Icon_temperature(bool value);
void Icon_leveling(bool value);

// Other
void Draw_Status_Area(const bool with_update); // Status Area
void HMI_StartFrame(const bool with_update);   // Prepare the menu view
void HMI_MainMenu();    // Main process screen
void HMI_SelectFile();  // File page
void HMI_Printing();    // Print page
void HMI_Prepare();     // Prepare page
void HMI_Control();     // Control page
void HMI_Leveling();    // Level the page
void HMI_AxisMove();    // Axis movement menu
void HMI_Temperature(); // Temperature menu
void HMI_Motion();      // Sports menu
void HMI_Info();        // Information menu
void HMI_Tune();        // Adjust the menu
void HMI_Confirm();  //You need to click OK interface
#if HAS_PREHEAT
  void HMI_PLAPreheatSetting(); // PLA warm-up setting
  void HMI_TPUPreheatSetting(); // TPU warm-up setting
  void HMI_PETGPreheatSetting(); // PETG warm-up setting
  void HMI_ABSPreheatSetting(); // ABS warm-up setting
#endif

void HMI_MaxSpeed();        // Maximum speed submenu
void HMI_MaxAcceleration(); // Maximum acceleration submenu
void HMI_MaxJerk();         // Maximum jerk speed submenu
void HMI_Step();            // Transmission ratio
void HMI_Boot_Set(); //Boot settings

void HMI_Init();
void DWIN_Update();
void EachMomentUpdate();
void Check_Filament_Update(void);
void DWIN_HandleScreen();
// void DWIN_StatusChanged(const char *text);
void DWIN_Draw_Checkbox(uint16_t color, uint16_t bcolor, uint16_t x, uint16_t y, bool mode /* = false*/);

inline void DWIN_StartHoming() { HMI_flag.home_flag = true; }

void DWIN_Show_M117(char* str);

void DWIN_CompletedHoming();
void DWIN_CompletedHeight();
void DWIN_CompletedLeveling();
void HMI_SetLanguage();

void Popup_window_Filament(void);
void Popup_window_Remove_card(void);
void Remove_card_window_check(void);
void ICON_Continue();
void Save_Boot_Step_Value();//Save boot steps
// Added new PID related interfaces
 void HMI_Hm_Set_PID(void);       // Set pid manually
 void HMI_Auto_set_PID(void);     // Automatically set pid
 void HMI_Auto_Nozzle_PID(void);  // Automatically set nozzle pid
 void HMI_Auto_Bed_PID(void);     // Automatically set the hotbed pid
void make_name_without_ext(char *dst, char *src, size_t maxlen);
// Cloud printing macro
#define TEXTBYTELEN     20   // File name length
#define MaxFileNumber   20   // Maximum number of files

#define AUTO_BED_LEVEL_PREHEAT  120

#define FileNum             MaxFileNumber
#define FileNameLen         TEXTBYTELEN
#define RTS_UPDATE_INTERVAL 2000
#define RTS_UPDATE_VALUE    RTS_UPDATE_INTERVAL

#define SizeofDatabuf       26

typedef struct CardRecord
{
  int recordcount;
  int Filesum;
  unsigned long addr[FileNum];
  char Cardshowfilename[FileNum][FileNameLen];
  char Cardfilename[FileNum][FileNameLen];
}CRec;

extern bool DWIN_lcd_sd_status;
extern bool pause_action_flag ;





extern uint8_t Cloud_Progress_Bar; // Progress bar data transmitted by cloud printing

extern void Draw_Print_ProgressRemain();
void Draw_Select_language();
void Draw_Poweron_Select_language();
void HMI_Poweron_Select_language();
void Draw_Print_File_Menu();
void Clear_Title_Bar();
void Draw_HM_PID_Set();
void Draw_Auto_PID_Set();
void Draw_auto_nozzle_PID();
void Draw_auto_bed_PID();
void HMI_HM_PID_Value_Set();   // Manually set pid value
void HMI_AUTO_PID_Value_Set(); // Automatically set pid value
void HMI_PID_Temp_Error();     // Pid temperature error interface
void Draw_PID_Error();         // Draw pid exception interface
void Popup_Window_Feedstork_Finish(bool parking/*=false*/);
void Popup_Window_Feedstork_Tip(bool parking/*=false*/);
void HMI_Plan_Move(const feedRate_t fr_mm_s);
void HMI_Auto_In_Feedstock();
void HMI_Auto_IN_Out_Feedstock();
void Draw_More_Icon(uint8_t line);
void Draw_Menu_Icon(uint8_t line,  uint8_t icon);
void Draw_Leveling_Highlight(const bool sel);
void Popup_Window_Height(uint8_t state);
void Leveling_Error();  //Leveling failure pop-up window
void Draw_Status_Area(bool with_update);
void Draw_Mid_Status_Area(bool with_update);
void update_variable();
void update_middle_variable();
duration_t estimate_remaining_time(const duration_t elapsed);
void Draw_laguage_Cursor(uint8_t line);
void In_out_feedtock(uint16_t _distance,uint16_t _feedRate,bool dir);
void In_out_feedtock_level(uint16_t _distance,uint16_t _feedRate,bool dir);
void Popup_window_boot(uint8_t type_popup); //Pop-up window type interface
void CR_Touch_error_func();//CR_TOUCH错误
// void Draw_Dots_On_Screen(xy_int8_t *mesh_Count,uint8_t Set_En,uint16_t Set_BG_Color);
#if ENABLED(SHOW_GRID_VALUES)  //If the leveling value is displayed
  void Draw_Dots_On_Screen(xy_int8_t *mesh_Count,uint8_t Set_En,uint16_t Set_BG_Color);
  void DWIN_Draw_Z_Offset_Float(uint8_t size, uint16_t color,uint16_t bcolor, uint8_t iNum, uint8_t fNum, uint16_t x, uint16_t y, long value);
  void Refresh_Leveling_Value();//Refresh leveling values
#endif
#if ENABLED(USER_LEVEL_CHECK)  //Using the leveling calibration function
    #define CHECK_POINT_NUM        4
    #define CHECK_ERROR_NUM        2
    #define CHECK_ERROR_MIN_VALUE  0.05
    #define CHECK_ERROR_MAX_VALUE  0.1
#endif

#if ENABLED(ONE_CLICK_PRINT)
  void one_click_print();
#endif

extern uint8_t G29_level_num;//Record how many points G29 has been leveled to determine whether G29 is leveled normally.
///////////////////////////
