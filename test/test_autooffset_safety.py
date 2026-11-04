#!/usr/bin/env python3
"""Run production auto-offset / M8015 / G212 with injected sensor and homing faults."""
from pathlib import Path
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]

STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include "Marlin/src/core/macros.h"
using std::max;
using std::isfinite;
using std::isnan;
using std::isinf;
enum {Z_AXIS, Nozz_Hot, Nozz_Clear, Nozz_Hight, ONE_HIGH, Set_levelling,
      POPUP_CONFIRM, High_faild_clear};
struct xyz_float_t { float x=0,y=0,z=0; float &operator[](int){return z;} };
struct xy_pos_t {float x=0,y=0;void set(float a,float b){x=a;y=b;}};
struct xy_int8_t {int x,y;};
struct Control {
 bool running=true, trusted=true, pressure_ok=true, stow_error=false, ftm=true;
 bool stop_on_touch=false, lose_trust_on_touch=false, fail_g29=false, with_level=true;
 int post_g29_moves=0,recoveries=0,g29_failures=0;
 int touches=0, homes=0, moves=0, shakes=0, pressure_steps=0, pressure_checks=0, saves=0, wipes=0, g29s=0;
 int fail_touch=-1, fail_home=-1, fail_pressure=-1, stow_at=-1;
 float touch_result=NAN, pressure_result=-1, saved_offset=0;
 std::vector<float> home_offsets;
} t;
struct { bool isRunning(){ return t.running; } void idle(){} } marlin;
struct {
 xyz_float_t position;
 struct {bool _enabled=true;}soft_endstop;
 bool all_axes_trusted(){ return t.trusted; }
 bool axis_is_trusted(int){ return t.trusted; }
 void set_axis_untrusted(int){ t.trusted=false; }
} motion;
std::string serial_log;
void serial(const char *s){ serial_log+=s; }
#define SERIAL_PRINT_MSG(s) serial(s)
#define SERIAL_ERROR_MSG(s) serial(s)
#define SERIAL_ECHOLNPGM_P(s) serial(s)
#define SERIAL_ECHOLNPGM(...) serial("result")
#define SERIAL_ECHOLN(...) serial("result")
struct {
 struct {float z=-2.25f;} offset; bool stow(){return t.stow_error;}
 float min_x(){return 28;} float max_x(){return 180;}
 float min_y(){return 28;} float max_y(){return 180;}
 void use_probing_tool(bool){}
} probe;
struct { void synchronize(){} } planner;
struct { void save(){ ++t.saves;t.saved_offset=probe.offset.z; } } settings;
int hotend=145, bed=50;
void move_z(float z){ assert(t.running && t.trusted && std::isfinite(z));++t.moves;
 if(z<motion.position.z)++t.pressure_steps;motion.position.z=z; }
void move_xy(float x,float y){assert(t.running && t.trusted && std::isfinite(x) && std::isfinite(y));
 ++t.moves;motion.position.x=x;motion.position.y=y;}
void move_xyz(float x,float y,float z){move_xy(x,y);move_z(z);++t.wipes;}
float touch(float,float){
 assert(t.running && t.trusted);++t.touches;
 if(t.touches==t.fail_pressure)t.pressure_ok=false;
 if(t.touches==t.stow_at)t.stow_error=true;
 if(t.stop_on_touch)t.running=false;
 if(t.lose_trust_on_touch)t.trusted=false;
 return t.touches==t.fail_touch ? t.touch_result : 0.f;
}
#define CRTOUCH_OFT_POS {-24.25,-15,0}
#define DO_BLOCKING_MOVE_TO_Z(z,speed) move_z(z)
#define DO_BLOCKING_MOVE_TO_XY(x,y,speed) move_xy(x,y)
#define DO_BLOCKING_MOVE_TO_XYZ(x,y,z,speed) move_xyz(x,y,z)
#define PROBE_PPINT_BY_TOUCH(x,y) touch(x,y)
#define GET_NOZZLE_TAR_TEMP(i) hotend
#define GET_BED_TAR_TEMP() bed
#define SET_HOTEND_TEMP(v,i) hotend=(v)
#define SET_BED_TEMP(v) bed=(v)
#define SET_BED_LEVE_ENABLE(v)
void set_bed_leveling_enabled(bool){}
#define MARLIN_CORE_IDLE() marlin.idle()
#define HAS_SOFTWARE_ENDSTOPS 1
bool &soft_endstops_enabled=motion.soft_endstop._enabled;
#define MIN_HOLD 2000
#define MAX_HOLD 10000
#define NOZ_TEMP_OFT_MM 0.05f
#define CLEAR_NOZZL_START_X 0
#define CLEAR_NOZZL_START_Y 15
#define CLEAR_NOZZL_END_X 0
#define CLEAR_NOZZL_END_Y 60
#define LEVEL_DISTANCE 15
#define FEEDING_DEF_SPEED 2
#define WAIT_HOTEND_TEMP(...)
#define WAIT_BED_TEMP(...)
#define SHOW_MSG 0
#define ZOFFSET_VALUE_MIN -5
#define ZOFFSET_VALUE_MAX 0
#define ZOFFSET_COMPARE 0.05f
void Popup_Window_Height(int){}
void In_out_feedtock_level(float,float,bool){}
struct HX711 {
 void init(int,int){} int getVal(bool){ return 123; }
};
#define HX711_SCK_PIN 4
#define HX711_SDO_PIN 6
#define PI_COUNT 32
struct ProbeAcq {
 float baseSpdXY_mm_s=100,baseSpdZ_mm_s=2,minZ_mm=-3,step_mm=.02f,outVal_mm=0;
 int minHold=MIN_HOLD,maxHold=MAX_HOLD,outIndex=0;
 xyz_float_t basePos_mm;
 double valP[PI_COUNT*2],posZ[PI_COUNT*2];
 HX711 hx711;
 void shakeZAxis(int){++t.shakes;}
 bool checkTrigger(){++t.pressure_checks;return t.pressure_ok;}
 void calMinZ(){outVal_mm=t.pressure_result;}
 ProbeAcq *probePointByStep();
 static float probeTimes(int,xyz_float_t,float,float,float,int,int);
};
struct {
 bool seen(char c){return c=='S';} bool value_bool(){return t.with_level;}
 bool seen_test(char){return false;}
 float linearval(char,float v){return v;}
} parser;
struct {
 bool leveling_offset_flag=false,Pressure_Height_end=false,Need_boot_flag=false;
 bool Need_g29_flag=false,Level_check_flag=false,Level_check_start_flag=false;
 bool G29_level_not_normal=false,G29_finish_flag=false,local_leveling_flag=false;
 int boot_step=0;
} HMI_flag;
int checkkey=0, failure_popups=0, main_menus=0;
void Popup_window_boot(int v){assert(v==High_faild_clear);++failure_popups;}
void DWIN_CalibrationFailed(bool=false){++failure_popups;}
void Goto_MainMenu(){++main_menus;}
#define GRID_MAX_POINTS_X 2
#define GRID_MAX_POINTS_Y 2
struct {
 float z_values[2][2];int refreshes=0;
 void refresh_bed_level(){++refreshes;}
} bedlevel;
#define DISABLE_AXIS_Z() t.trusted=false
bool gp=true,gt=true,gb=false,gk=false,gh=false;
int gc=4;
#define GET_PARSER_SEEN(c) ((c)=='C'||((c)=='P'&&gp)||((c)=='T'&&gt)||((c)=='B'&&gb)||((c)=='K'&&gk)||((c)=='H'&&gh))
#define GET_PARSER_INT_VAL() gc
using xyz_pos_t=xyz_float_t;
#define PRESS_XYZ_POS {28,28,0}
void finish_g29(float);
int G29_level_num=0;
#define G29_RETURN(retry,did) return retry
#define DWIN_CREALITY_LCD 1
#define HOST_PROMPT_SUPPORT 0
#define G29_MAX_RETRIES 3
enum {Level_faild_QR};
void delay(int){}
struct GcodeSuite {
 void process_subcommands_now(const char *cmd){
  if(!std::strcmp(cmd,"G29")){G29_with_retry();return;}
  assert(!std::strncmp(cmd,"G28",3));++t.homes;t.home_offsets.push_back(probe.offset.z);
  t.trusted=t.homes!=t.fail_home;motion.position.z=10;
 }
 static void M8015();static void G212();
 static bool G29(){++t.g29s;finish_g29(t.fail_g29 ? NAN : 0);return t.fail_g29;}
 static void G29_with_retry();
 static void event_probe_recover(){++t.recoveries;}
 static void event_probe_failure(){++t.g29_failures;}
} gcode;
#define PSTR(s) s
#define F(s) s
#define G28_STR "G28"
#define CHECK_POINT_NUM 4
#define CHECK_ERROR_MIN_VALUE .05f
#define CHECK_ERROR_MAX_VALUE .1f
#define CHECK_ERROR_NUM 2
struct {bool isPrinting(){return false;}}card;
int sd_starts=0;
struct FtmScope { bool saved=t.ftm; FtmScope(){t.ftm=false;}~FtmScope(){t.ftm=saved;} };
#define FTM_DISABLE_IN_SCOPE() FtmScope ftm_scope
float estimate_result=-.95f;
static float robust_offset_from_points(const float *v,const xyz_float_t *,uint8_t n){
 assert(n>0);return std::isfinite(estimate_result) ? v[0] : estimate_result;
}
'''

MAIN = r'''
void reset(){
 t=Control{};probe.offset.z=-2.25f;estimate_result=-.95f;
 HMI_flag={};failure_popups=main_menus=0;bedlevel.refreshes=0;
 for(auto &row:bedlevel.z_values)for(float &v:row)v=.4f;
 gp=gt=true;gb=gk=gh=false;gc=4;hotend=145;bed=50;
 soft_endstops_enabled=true;serial_log.clear();
 sd_starts=0;
}
void failed(bool clean=false){
 float z=99;
 assert(!getZOffset(clean,true,true,&z));
 assert(std::isnan(z) && probe.offset.z==-2.25f && t.saves==0);
 assert(!t.trusted && t.ftm && soft_endstops_enabled);
}
int main(){
 // Every point, both non-finite readings, and a stow failure must stop the run.
 const int points=X_ROUTINE_AUTO_OFFSET ? 5 : 4;
 const int touches=points*ZOFFSET_REPEAT_NIN;
 for(int at=1;at<=points;++at)for(float bad:{NAN,INFINITY}){
  reset();t.fail_touch=at;t.touch_result=bad;failed();
  assert(t.touches==at && t.homes==1 && !t.wipes);
 }
 reset();t.stow_at=1;failed();assert(t.touches==1 && t.pressure_checks==0);
 reset();t.stop_on_touch=true;failed();assert(t.touches==1 && t.pressure_checks==0);
 reset();t.lose_trust_on_touch=true;failed();assert(t.touches==1 && t.pressure_checks==0);
 // A missing pressure contact stops retries and restores software endstops.
 reset();t.fail_pressure=1;failed();assert(t.touches==1 && t.homes==1);
 reset();t.pressure_ok=false;failed(true);assert(t.touches==0 && t.wipes==0 && t.homes==1);
 reset();t.pressure_result=INFINITY;failed();assert(t.touches==1);
 reset();t.fail_home=1;failed();assert(t.touches==0 && t.shakes==0 && t.moves==0);
 reset();t.fail_home=2;failed();assert(t.touches==touches);
 // Invalid estimates and incomplete sensor selections are never persisted.
 for(float bad:{NAN,INFINITY}){reset();estimate_result=bad;failed();assert(t.homes==1);}
 for(bool pressure:{false,true})for(bool touch:{false,true})if(!pressure||!touch){
  reset();float z=0;assert(!getZOffset(true,pressure,touch,&z));
  assert(std::isnan(z) && t.homes==0 && t.moves==0 && t.saves==0 && probe.offset.z==-2.25f);
 }
 // Healthy calibration remains available, including cleaning and final homing.
 for(bool clean:{false,true}){
  reset();float z=0;assert(getZOffset(clean,true,true,&z));
  assert(std::fabs(z+.95f)<.0001f && probe.offset.z==z);
  assert(t.saves==0 && t.trusted && t.ftm && t.touches==touches);
  assert(t.homes==(clean?3:2) && t.home_offsets.front()==0 && t.home_offsets.back()==z);
 }
 // M8015 failure must not erase the previous mesh or schedule G29.
 reset();HMI_flag.Pressure_Height_end=true;t.fail_touch=2;
 GcodeSuite::M8015();assert(failure_popups==1 && t.saves==0);
 assert(!HMI_flag.Pressure_Height_end && !HMI_flag.leveling_offset_flag);
 assert(probe.offset.z==-2.25f && !bedlevel.refreshes);
 for(auto &row:bedlevel.z_values)for(float v:row)assert(v==.4f);
 reset();GcodeSuite::M8015();assert(t.saves==1 && HMI_flag.Pressure_Height_end);
 assert(!failure_popups && bedlevel.refreshes==1);
 reset();t.with_level=false;GcodeSuite::M8015();assert(t.saves==1 && !HMI_flag.Pressure_Height_end && main_menus==1);
 reset();HMI_flag.Need_boot_flag=true;t.fail_touch=1;GcodeSuite::M8015();assert(HMI_flag.boot_step!=Set_levelling);
 // G212 C must not retry a failed calibration.
 reset();t.fail_touch=1;GcodeSuite::G212();assert(t.touches==1 && t.homes==1 && t.saves==0);
 reset();gc=1;GcodeSuite::G212();assert(t.saves==1 && t.trusted && t.saved_offset==probe.offset.z);
 // The real LCD preflight must run before queuing the SD file and cannot
 // convert a failed probe into a new automatic G29 / print attempt.
 reset();HMI_flag.Level_check_flag=true;t.fail_touch=1;
 start_sd_print();assert(sd_starts==0 && t.g29s==0 && failure_popups==1 && t.touches==1);
 reset();HMI_flag.Level_check_flag=true;t.fail_home=1;
 start_sd_print();assert(sd_starts==0 && t.g29s==0 && t.touches==0 && t.moves==0);
 reset();HMI_flag.Level_check_flag=true;t.fail_g29=true;
 start_sd_print();assert(sd_starts==0 && t.g29s==1 && t.post_g29_moves==0 && t.saves==0);
 assert(t.recoveries==0 && t.g29_failures==0);
 reset();HMI_flag.Level_check_flag=true;
 start_sd_print();assert(sd_starts==1 && t.touches==CHECK_ERROR_NUM && t.g29s==1);
 reset();HMI_flag.Level_check_flag=true;
 for(auto &row:bedlevel.z_values)for(float &v:row)v=0;
 start_sd_print();assert(sd_starts==1 && t.touches==4);
 reset();HMI_flag.Level_check_flag=true;t.fail_home=2;
 for(auto &row:bedlevel.z_values)for(float &v:row)v=0;
 start_sd_print();assert(sd_starts==0 && t.g29s==0);
 for(float bad:{NAN,INFINITY}){
  reset();HMI_flag.G29_finish_flag=HMI_flag.local_leveling_flag=HMI_flag.Pressure_Height_end=true;
  finish_g29(bad);assert(!t.trusted && !t.saves && !t.post_g29_moves);
  assert(HMI_flag.G29_level_not_normal && !HMI_flag.G29_finish_flag && !HMI_flag.Pressure_Height_end);
 }
 // Scalar logging cannot access arrays, and uses the actual bounded formatter.
 reset();for(int i=0;i<130;++i)printTestResult(0,-1);
 PRINTF("%s",std::string(500,'a').c_str());assert(serial_log.size()>=127);
 // Raw pressure diagnostics cannot bypass homing or accept invalid positions.
 reset();ProbeAcq pa;t.trusted=false;assert(std::isnan(pa.probePointByStep()->outVal_mm));assert(t.moves==0);
 reset();pa.basePos_mm.z=NAN;assert(std::isnan(pa.probePointByStep()->outVal_mm));assert(t.moves==0);
}
'''

if __name__ == '__main__':
    source = (ROOT/'Marlin/src/e3v3se/AutoOffset.cpp').read_text()
    header = (ROOT/'Marlin/src/e3v3se/AutoOffset.h').read_text()
    names = ('FOR_LOOP_TIMES', 'CHECK_AND_RETURN', 'CHECK_AND_RUN', 'ARY_SORT',
             'PRINTF', 'RUN_AND_WAIT_GCODE_CMD')
    macros = '\n'.join(line for line in header.splitlines()
                       if any(line.startswith('#define '+name+'(') for name in names))
    utility = (ROOT/'Marlin/src/core/utility.h').read_text()
    restorer = utility[utility.index('template<typename T>\nclass restorer'):utility.index('// Converts from an uint8_t')]
    functions = '\n'.join(function(source, prefix) for prefix in (
        'char *getStr(', 'static inline bool is_valid_offset(',
        'float ProbeAcq::probeTimes(', 'ProbeAcq* ProbeAcq::probePointByStep(',
        'bool clearByBed(', 'bool probeByPress(', 'bool probeByTouch(',
        'static void printTestResult(', 'float Hight_One(',
        'static float Multiple_Hight_At(', 'static bool measure_z_offset(', 'bool getZOffset('))
    functions += function((ROOT/'Marlin/src/e3v3se/M8015.cpp').read_text(), 'void GcodeSuite::M8015(')
    functions += function((ROOT/'Marlin/src/e3v3se/G212.cpp').read_text(), 'void GcodeSuite::G212(')
    functions += function((ROOT/'Marlin/src/gcode/gcode.cpp').read_text(), 'void GcodeSuite::G29_with_retry(')
    lcd = (ROOT/'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
    functions += function(lcd, 'static bool G29_small(')
    g29 = (ROOT/'Marlin/src/gcode/bedlevel/abl/G29.cpp').read_text()
    guard = function(g29, 'if (!isfinite(abl.measured_z)')
    assert g29.index('if (!isfinite(abl.measured_z)') < g29.index('probe.move_z_after_probing();') < g29.index('settings.save();')
    functions += '\nvoid finish_g29(float z){struct {float measured_z;}abl{z};'+guard.replace('G29_RETURN(true, false);','return;')+'++t.post_g29_moves;settings.save();}\n'
    preview = function(lcd, 'void Show_G_Pic(')
    assert preview.index('if (HMI_flag.Level_check_flag') < preview.index('card.openAndPrintFile(')
    functions += '\nvoid start_sd_print(){'+function(preview, 'if (HMI_flag.Level_check_flag')+'++sd_starts;}\n'
    with tempfile.TemporaryDirectory(prefix='autooffset-safety-') as folder:
        src, exe = Path(folder)/'safety.cpp', Path(folder)/'safety'
        src.write_text(STUBS+'\n'+macros+'\n'+restorer+'\n'+functions+MAIN)
        for x_routine in (0, 1):
            for ftm in (0, 1):
                for repeats in (1, 2, 3):
                    subprocess.run(['g++','-std=c++17','-O1','-D_FORTIFY_SOURCE=3',
                                    '-fstack-protector-strong','-I',str(ROOT),
                                    f'-DX_ROUTINE_AUTO_OFFSET={x_routine}',f'-DFT_MOTION={ftm}',
                                    f'-DZOFFSET_REPEAT_NIN={repeats}','-DZOFFSET_REPEAT_NAX=3',
                                    str(src),'-o',str(exe)],check=True)
                    subprocess.run([str(exe)],check=True)
    print('PASS auto-offset failures, pressure timeout, homing, rollback, EEPROM, M8015/G212, bounded logging; D/X, FT on/off, 1/2/3 samples')
