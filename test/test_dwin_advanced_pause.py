#!/usr/bin/env python3
"""Run upstream load/purge, DWIN confirmation and host responses together."""
from pathlib import Path
import re
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]

STUBS = r'''
#include <cassert>
#include <cstdint>
#include <vector>
#include <deque>
#include <string>
#include <functional>
#include "Marlin/src/core/macros.h"
#define ADVANCED_PAUSE_FEATURE 1
#define DWIN_CREALITY_LCD 1
#define M600_PURGE_MORE_RESUMABLE 1
#define DWIN_RENDER_THUMBNAIL 1
#define HAS_FILAMENT_SENSOR 1
#define HAS_RESUME_CONTINUE 1
#define HAS_MEDIA 1
#define ADVANCED_PAUSE_PURGE_FEEDRATE 3
#define FILAMENT_CHANGE_SLOW_LOAD_FEEDRATE 2
#define FILAMENT_CHANGE_FAST_LOAD_FEEDRATE 6
#define DEBUG_SECTION(...)
#define DEBUG_ECHOLNPGM(...)
#define SERIAL_ECHO_MSG(...)
#define KEEPALIVE_STATE(...)
#define _PMSG(V) "insert"
#define GET_TEXT_F(V) "message"
#define F(V) V
#define FPSTR(V) V
#define DXC_ARGS
using FSTR_P=const char*;
using feedRate_t=float;
enum { MainMenu, PrintProcess, ThumbPrint, Tune, AdvancedPause };
enum ENCODER_DiffState { ENCODER_DIFF_NO,ENCODER_DIFF_CW,ENCODER_DIFF_CCW,ENCODER_DIFF_ENTER };
int checkkey=ThumbPrint,progress=67,print_visits=0,thumb_visits=0,main_visits=0,draws=0;
bool hasThumbnail=true, filament_out=false;
struct {bool enabled=true;} EncoderRate;
struct {bool Refresh_bottom_flag=false;} HMI_flag;
constexpr int Color_Bg_Black=0,Color_White=1,Color_Yellow=2,font6x12=6,font8x16=8,DWIN_WIDTH=240,STATUS_Y=250;
std::vector<std::string> labels;
void DWIN_Draw_Rectangle(int,int,int,int,int,int) { ++draws; }
void DWIN_Draw_String(bool,bool,int,int,int,int,int,const char *s) { labels.push_back(s); }
void DWIN_UpdateLCD() {}
void Draw_Mid_Status_Area(bool) {}
void Clear_Title_Bar() {}
void Clear_Main_Window() {}
void Draw_Title(const char *) {}
void Show_JPN_print_title() {}
void Goto_ThumbPrint(bool reset) { ++thumb_visits;checkkey=ThumbPrint;if(reset) progress=0; }
void Goto_PrintProcess() { ++print_visits;checkkey=PrintProcess; }
void Goto_MainMenu() { ++main_visits;checkkey=MainMenu; }
struct { bool enabled=true,filament_ran_out=false;int resets=0;
 void reset() {++resets;filament_ran_out=false;}
} runout;
std::deque<ENCODER_DiffState> events;
struct Marlin {
 bool wait_for_user=false,printing=true;
 std::function<void()> idle_action;
 int idles=0;
 void wait_start() { wait_for_user=true; }
 void user_resume() { wait_for_user=false; }
 bool printJobOngoing() { return printing; }
 bool printingIsPaused() { return printing; }
 void idle_no_sleep() { assert(++idles<100);idle_action(); }
} marlin;
ENCODER_DiffState get_encoder_state() {
 if(events.empty()) return ENCODER_DIFF_NO;
 auto e=events.front();events.pop_front();
 if(e==ENCODER_DIFF_ENTER) {
   bool waiting=marlin.wait_for_user; marlin.user_resume();
   if(waiting) return ENCODER_DIFF_NO;
 }
 return e;
}
struct Motion {
 int extruder=0; std::vector<float> moves;
 void unscaled_e_move(float length,float) { moves.push_back(length); }
} motion;
bool ensure_safe_temperature(bool,PauseMode);
void first_impatient_beep(int) {}
void impatient_beep(int) {}
enum PromptReason { PROMPT_NOT_DEFINED, PROMPT_FILAMENT_RUNOUT, PROMPT_USER_CONTINUE, PROMPT_PAUSE_RESUME, PROMPT_INFO };
PromptReason host_prompt_reason=PROMPT_NOT_DEFINED;
const char *CONTINUE_STR="Continue";
const char M24_STR[]="M24";
struct {void inject_P(const char*){}} queue;
struct HostUI {
 int prompts=0,ends=0;
 template<class...T> void prompt_do(T...) {}
 void prompt_end() { ++ends; }
 void filament_load_prompt() { ++prompts;host_prompt_reason=PROMPT_FILAMENT_RUNOUT; }
 void handle_response(uint8_t);
} hostui;
struct MarlinUI {
 static void pause_show_message(PauseMessage,PauseMode=PAUSE_MODE_SAME,uint8_t=0);
 static void refresh() {}
} ui;
PauseMenuResponse pause_menu_response=PAUSE_RESPONSE_WAIT_FOR;
PauseMode pause_mode=PAUSE_MODE_PAUSE_PRINT;
bool ensure_safe_temperature(bool,PauseMode) { return true; }
bool active_filament_is_out() { return filament_out; }
'''

MAIN = r'''
void reset() {
 motion.moves.clear();events.clear();marlin.idles=0;marlin.printing=true;
 marlin.wait_for_user=false;runout.enabled=true;runout.filament_ran_out=false;filament_out=false;
 hostui.prompts=hostui.ends=0;pause_ui_active=false;hasThumbnail=true;
 checkkey=ThumbPrint;progress=67;
 marlin.idle_action=[] { HMI_AdvancedPause(); };
}
void load(float purge) { assert(load_filament(0,0,purge,0,true,false,PAUSE_MODE_PAUSE_PRINT)); }
int main() {
 reset();events={ENCODER_DIFF_ENTER};load(7);
 assert(motion.moves==std::vector<float>{7});
 assert(pause_menu_response==PAUSE_RESPONSE_RESUME_PRINT);
 ui.pause_show_message(PAUSE_MESSAGE_STATUS);
 assert(checkkey==ThumbPrint && progress==67 && thumb_visits==1);
 reset();events={ENCODER_DIFF_CW,ENCODER_DIFF_ENTER,ENCODER_DIFF_ENTER};load(50);
 assert((motion.moves==std::vector<float>{50,50}));
 // Purge/insert stages yield and clicks clear the core wait, without becoming menu clicks.
 reset();ui.pause_show_message(PAUSE_MESSAGE_INSERT);marlin.wait_start();
 events={ENCODER_DIFF_ENTER};HMI_AdvancedPause();
 assert(!marlin.wait_for_user && checkkey==AdvancedPause);
 marlin.printing=false;ui.pause_show_message(PAUSE_MESSAGE_STATUS);assert(checkkey==MainMenu);
 // Explicitly labeled sensor disable matches the upstream host response.
 reset();runout.filament_ran_out=true;filament_out=true;events={ENCODER_DIFF_ENTER};load(2.5f);
 assert(!runout.enabled && !runout.filament_ran_out && runout.resets==1);
 assert(pause_menu_response==PAUSE_RESPONSE_RESUME_PRINT);
 #if !FILAMENT_MOTION_SENSOR
 // Reinserted switch filament clears the event without disabling detection.
 reset();runout.filament_ran_out=true;events={ENCODER_DIFF_ENTER};load(50);
 assert(runout.enabled && !runout.filament_ran_out);
 assert(motion.moves==std::vector<float>{50});
 // Reinsertion while the option screen is open also rearms the switch.
 reset();runout.filament_ran_out=true;filament_out=true;
 pause_menu_response=PAUSE_RESPONSE_WAIT_FOR;ui.pause_show_message(PAUSE_MESSAGE_OPTION);
 assert(runout.filament_ran_out);
 filament_out=false;HMI_AdvancedPause();
 assert(runout.enabled && !runout.filament_ran_out && labels.back()=="Resume");
 #else
 reset();runout.filament_ran_out=true;
 assert(pause_sensor_out() && runout.enabled); // No switch-based reset for a motion sensor.
 #endif
 // M412 S0 remains disabled even when the switch becomes present.
 reset();runout.enabled=false;runout.filament_ran_out=true;
 assert(pause_sensor_out() && !runout.enabled);
 reset();ui.pause_show_message(PAUSE_MESSAGE_WAITING);
 assert(labels[labels.size()-2]=="Press knob to resume");
 #if HOST_PROMPT_SUPPORT
   reset();int responses=0;
   marlin.idle_action=[&] { hostui.handle_response(responses++ ? 1 : 0); };
   load(3);assert((motion.moves==std::vector<float>{3,3}));
   assert(hostui.prompts==2 && hostui.ends==1);
   reset();ui.pause_show_message(PAUSE_MESSAGE_INSERT);marlin.wait_start();
   host_prompt_reason=PROMPT_USER_CONTINUE;hostui.handle_response(0);
   assert(!marlin.wait_for_user);
 #endif
 // Option rendering is event driven: idle ticks must not flood the LCD.
 reset();pause_menu_response=PAUSE_RESPONSE_WAIT_FOR;ui.pause_show_message(PAUSE_MESSAGE_OPTION);
 HMI_AdvancedPause();int before=draws;
 for(int n=0;n<100;++n) HMI_AdvancedPause();
 assert(draws==before);
}
'''


def main():
    header=(ROOT/'Marlin/src/feature/pause.h').read_text()
    enums='\n'.join(re.search(r'enum '+name+r' : char \{.*?\};',header,re.S)[0]
                    for name in ('PauseMode','PauseMessage','PauseMenuResponse'))
    # Modes precede stub declarations that use them; the preprocessor macros follow.
    dwin=(ROOT/'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
    begin=dwin.index('  static bool pause_ui_active')
    end=dwin.index('\nvoid dwinInitScreen()',begin)
    bridge=dwin[begin:end]
    bridge=bridge[:bridge.rfind('#endif')]
    load=function((ROOT/'Marlin/src/feature/pause.cpp').read_text(),'bool load_filament(')
    host=function((ROOT/'Marlin/src/feature/host_actions.cpp').read_text(),'void HostUI::handle_response(')
    with tempfile.TemporaryDirectory() as tmp:
        source,exe=Path(tmp)/'pause.cpp',Path(tmp)/'pause'
        for prompts in (0,1):
            for motion in (0,1):
                source.write_text(enums+'\n'+STUBS+bridge+'\n'+host+'\n'+load+'\n'+MAIN)
                subprocess.run(['g++','-std=c++17','-I',str(ROOT),f'-DHOST_PROMPT_SUPPORT={prompts}',
                                f'-DFILAMENT_MOTION_SENSOR={motion}',str(source),'-o',str(exe)],check=True)
                subprocess.run([str(exe)],check=True)
    print('PASS purge lengths/repeat, LCD/host confirmation, switch reinsertion, explicit disable, progress and idle rendering')


if __name__=='__main__':
    main()
