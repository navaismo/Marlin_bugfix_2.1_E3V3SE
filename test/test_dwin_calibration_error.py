#!/usr/bin/env python3
"""Execute the real calibration error renderer, knob handler and dispatch case."""
from pathlib import Path
import re
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]
STUBS = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
#include "Marlin/src/core/macros.h"
#define F(s) s
#define DWIN_WIDTH 240
enum {MainMenu,CalibrationError,POPUP_CONFIRM,Spanish,English};
enum {MF_INITIALIZING,MF_STOPPED,MF_KILLED,MF_RUNNING};
enum ENCODER_DiffState {ENCODER_DIFF_NO,ENCODER_DIFF_CW,ENCODER_DIFF_CCW,ENCODER_DIFF_ENTER};
enum {Z_AXIS,font8x16,Color_White,Color_Red,Color_Yellow,Color_Bg_Window,Color_Bg_Blue};
struct {
 bool reenter=false,fail_home=false,stop_on_fail=false;
 int homes=0,menus=0,old_confirms=0,alert_resets=0,updates=0;
 bool homing_screen=false;
} t;
int checkkey=MainMenu;
ENCODER_DiffState event=ENCODER_DIFF_NO;
ENCODER_DiffState get_encoder_state(){auto v=event;event=ENCODER_DIFF_NO;return v;}
struct {
 bool leveling_offset_flag=true,Pressure_Height_end=true,local_leveling_flag=true,G29_finish_flag=true;
 bool Level_check_start_flag=true,Need_g29_flag=true,Refresh_bottom_flag=false;
 bool Need_boot_flag=true;
 int boot_step=0,language=English;
} HMI_flag;
bool OctoRefresh=true;
struct {
 int state=MF_RUNNING;
 bool isStopped(){return state==MF_STOPPED;}
 bool isRunning(){return state>=MF_RUNNING;}
 void setState(int s){state=s;}
} marlin;
struct {
 bool trusted=true;
 void set_axis_untrusted(int a){assert(a==Z_AXIS);trusted=false;}
 bool all_axes_trusted(){return trusted;}
} motion;
struct {void reset_alert_level(){++t.alert_resets;}}ui;
struct {void synchronize(){}}planner;
struct {int now=9;void set(int n){now=n;}}select_page;
std::vector<std::string> text;
void Clear_Main_Window(){text.clear();}
void Draw_Title(const char *s){assert(std::strlen(s)*8<=DWIN_WIDTH);text.emplace_back(s);}
void Draw_Popup_Bkgd_60(){}
void DWIN_Draw_String(bool,bool,int,int,int,int x,int y,const char *s){
 assert(x>=0 && x+int(std::strlen(s))*8<=DWIN_WIDTH && y>=0 && y+16<=320);
 text.emplace_back(s);
}
void DWIN_Draw_Rectangle(int,int,int x1,int y1,int x2,int y2){
 assert(x1>=0 && x1<x2 && x2<DWIN_WIDTH && y1>=0 && y1<y2 && y2<320);
}
void DWIN_UpdateLCD(){++t.updates;}
void Popup_Window_Home(){t.homing_screen=true;}
void Goto_MainMenu(){++t.menus;checkkey=MainMenu;}
void HMI_Confirm(){++t.old_confirms;HMI_flag.boot_step=99;}
void dispatch();
struct {void home_all_axes(){
 assert(marlin.isRunning() && !motion.trusted);++t.homes;
 assert(checkkey==CalibrationError && t.homing_screen);
 if(t.reenter){event=ENCODER_DIFF_ENTER;dispatch();}
 motion.trusted=!t.fail_home;
 if(t.fail_home && t.stop_on_fail)marlin.setState(MF_STOPPED);
}}gcode;
'''

MAIN = r'''
bool contains(const char *s){for(const auto &line:text)if(line==s)return true;return false;}
void reset(){t={};HMI_flag={};marlin.state=MF_RUNNING;motion.trusted=true;
 checkkey=MainMenu;event=ENCODER_DIFF_NO;OctoRefresh=true;select_page.now=9;}
void show(int step,int language){
 reset();HMI_flag.boot_step=step;HMI_flag.language=language;
 DWIN_CalibrationFailed();
 assert(checkkey==CalibrationError && !motion.trusted && t.homes==0 && t.menus==0);
 assert(HMI_flag.boot_step==step && HMI_flag.Need_boot_flag);
 assert(!HMI_flag.Pressure_Height_end && !HMI_flag.G29_finish_flag && !HMI_flag.local_leveling_flag);
 assert(!HMI_flag.leveling_offset_flag && !HMI_flag.Level_check_start_flag && !HMI_flag.Need_g29_flag);
 assert(HMI_flag.Refresh_bottom_flag && t.updates==1);
 if(OCTOPRINT_PLUGIN)assert(!OctoRefresh);
 assert(contains(language==Spanish ? "Fallo al calcular" : "Could not calculate"));
 assert(contains(language==Spanish ? "Homing y menu" : "Home / Main menu"));
}
int main(){
 for(int step:{0,1,2,3})for(int language:{English,Spanish}){
  show(step,language);
  for(auto e:{ENCODER_DIFF_NO,ENCODER_DIFF_CW,ENCODER_DIFF_CCW}){
   event=e;dispatch();assert(t.homes==0 && t.menus==0 && t.old_confirms==0);
  }
  t.reenter=true;event=ENCODER_DIFF_ENTER;dispatch();
  assert(t.homes==1 && t.menus==1 && checkkey==MainMenu && select_page.now==0);
  assert(t.old_confirms==0 && HMI_flag.boot_step==step && HMI_flag.Need_boot_flag);
 }
 // Probe-stopped firmware is enabled only by the explicit recovery click.
 show(1,English);marlin.state=MF_STOPPED;assert(t.homes==0);
 event=ENCODER_DIFF_ENTER;dispatch();assert(t.homes==1 && t.menus==1 && t.alert_resets==1);
 // A failed home stays in the error modal and allows another explicit attempt.
 for(bool stopped:{false,true}){
  show(2,English);t.fail_home=true;t.stop_on_fail=stopped;t.reenter=true;
  event=ENCODER_DIFF_ENTER;dispatch();
  assert(t.homes==1 && t.menus==0 && checkkey==CalibrationError && !motion.trusted);
  assert(contains("Homing failed. Check.") && t.old_confirms==0 && HMI_flag.boot_step==2);
  t.fail_home=false;event=ENCODER_DIFF_ENTER;dispatch();
  assert(t.homes==2 && t.menus==1 && checkkey==MainMenu && t.old_confirms==0);
 }
 // A fatal/initializing state must never be silently restarted.
 for(int state:{MF_KILLED,MF_INITIALIZING}){
  show(1,English);marlin.state=state;event=ENCODER_DIFF_ENTER;dispatch();
  assert(t.homes==0 && t.menus==0 && marlin.state==state && checkkey==CalibrationError);
 }
}
'''

if __name__ == '__main__':
    source = (ROOT/'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
    header = (ROOT/'Marlin/src/lcd/dwin/creality/dwin.h').read_text()
    prototype = re.search(r'void DWIN_CalibrationFailed\([^;]+;', header)[0]
    functions = 'static bool calibration_recovery_busy=false;\n'+prototype+'\n'
    functions += function(source, 'void DWIN_CalibrationFailed(')
    functions += function(source, 'static void HMI_CalibrationError(')
    dispatch = function(source, 'void DWIN_HandleScreen(')
    cases = ''.join(re.search(r'case '+state+r':.*?\bbreak;', dispatch, re.S)[0]
                    for state in ('CalibrationError', 'POPUP_CONFIRM'))
    functions += '\nvoid dispatch(){switch(checkkey){'+cases+'}}\n'
    # Confirm that old process IDs are retained and all error entry points use
    # this modal instead of the wizard's generic confirmation handler.
    assert header.index('CalibrationError,') > header.index('ThumbPrint_window,')
    for path, prefix in (('Marlin/src/e3v3se/M8015.cpp','void GcodeSuite::M8015('),
                         ('Marlin/src/gcode/bedlevel/abl/G29.cpp','if (!isfinite(abl.measured_z)'),
                         ('Marlin/src/lcd/dwin/creality/dwin.cpp','void Show_G_Pic(')):
        body = function((ROOT/path).read_text(), prefix)
        assert 'DWIN_CalibrationFailed()' in body
        assert 'Popup_window_boot(High_faild_clear)' not in body
    with tempfile.TemporaryDirectory(prefix='dwin-calibration-error-') as folder:
        src, exe = Path(folder)/'error.cpp', Path(folder)/'error'
        src.write_text(STUBS+functions+MAIN)
        for host in (0, 1):
            subprocess.run(['g++','-std=c++17','-I',str(ROOT),f'-DOCTOPRINT_PLUGIN={host}',
                            str(src),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
    print('PASS calibration failure LCD, Spanish/English, all wizard states, explicit home, reentrant clicks, stopped firmware and failed homing; SD/host')
