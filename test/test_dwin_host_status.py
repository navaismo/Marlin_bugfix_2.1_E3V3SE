#!/usr/bin/env python3
"""Replay actual host pause/title/M117 UI code without a printer."""
from pathlib import Path
import os
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]
s = (ROOT / 'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
prefix = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include "Marlin/src/core/macros.h"
#define M9001_DRAW_PROTOCOL 1
#define DWIN_RENDER_THUMBNAIL 1
#define OCTOPRINT_PLUGIN 1
#define F(V) V
#define SERIAL_ECHOLN(...)
#define SERIAL_ECHOLNPGM(...)
#define ELAPSED(N,T) (int32_t((N)-(T))>=0)
using millis_t=uint32_t;
uint32_t now=100;
uint32_t millis(){return now;}
enum {MainMenu,ThumbPrint,ThumbTune,ThumbPrint_window,AdvancedPause,M117Info};
int checkkey=ThumbPrint;
bool OctoRefresh=true,hasThumbnail=true,isPaused=false,dwin_abort_flag=false;
struct {bool pause_flag=false,Refresh_bottom_flag=false,pause_action=false,
 Level_check_start_flag=false,done_confirm_flag=false,print_finish=false,select_flag=false;int language=0;} HMI_flag;
struct {bool running=true,paused=false;bool printJobOngoing(){return running;}
 bool printingIsPaused(){return paused;}void end_waiting(){}} marlin;
struct {int progress=6734,layer=17,total=40,remaining=600,resets=0;
 int aborts=0;void abort_print(){++aborts;marlin.running=marlin.paused=false;}
 void progress_reset(){++resets;progress=0;}int get_current_layer(){return layer;}} ui;
char title[50]="cube.gcode",shift_name[101]={},visibleText[31]={};
uint8_t scrollOffset=0;uint32_t lastScrollTime=0;const int scrollDelay2=250;
constexpr int MENU_CHAR_LIMIT=30,DWIN_FONT_HEAD=1,Color_Yellow=4,Color_Blue=3,Color_White=1,
 Color_Bg_Black=0,font8x16=1,LANGUAGE_Info=1,LANGUAGE_Back=2,TITLE_X=0,TITLE_Y=0,
 DWIN_WIDTH=240,MENU_CHR_W=8;
struct Text {int x,y;std::string value;int color;};std::vector<Text> text;
int title_clears=0,full_clears=0,pause_icons=0,continue_icons=0;
void DWIN_Draw_String(bool,bool,int,int color,int,int x,int y,const char *v){text.push_back({x,y,v,color});}
void Clear_Title_Bar(){++title_clears;}
void Clear_Main_Window(){++full_clears;}
void Draw_Mid_Status_Area(bool){}void DWIN_ICON_Show(int,int,int,int){}void Draw_Back_First(){}
void Clear_Below_Area(){}void Draw_Print_ProgressBar(){}
void ICON_Tune(){}void ICON_Stop(){}void ICON_Pause(){++pause_icons;}void ICON_Continue(){++continue_icons;}
void DWIN_UpdateLCD(){}
bool drawing=false;
namespace LcdDraw {bool active(){return drawing;}void cancel(){drawing=false;}}
namespace HostPrint {void draw_title();uint16_t title_color();void refresh(bool){}}
struct Selection {int now=0;void reset(){now=0;}void set(int v){now=v;}bool inc(int max){if(now>=max-1)return false;++now;return true;}
 bool dec(){if(!now)return false;--now;return true;}} select_print,select_tune,select_page;
void Goto_MainMenu(){Clear_Main_Window();checkkey=MainMenu;hasThumbnail=OctoRefresh=isPaused=HMI_flag.pause_flag=false;}
struct {int show_mode=0;} HMI_ValueStruct;
int index_tune=0,MROWS=5;
enum ENCODER_DiffState {ENCODER_DIFF_NO,ENCODER_DIFF_CW,ENCODER_DIFF_CCW,ENCODER_DIFF_ENTER};
ENCODER_DiffState event=ENCODER_DIFF_NO;
ENCODER_DiffState get_encoder_state(){return event;}
void Draw_ThumbTune_Menu(){}void ThumbPopup_PauseOrStop(){}
void unchanged(){assert(ui.progress==6734&&ui.layer==17&&ui.total==40&&ui.remaining==600&&ui.resets==0);}
void title_only(int from){for(unsigned i=from;i<text.size();++i)assert(text[i].y==4);}
'''
code = prefix
for name in ('octo_make_name_without_ext', 'Draw_OctoTitle', 'octoUpdateScroll'):
    code += '\n' + function(s, 'void ' + name + '(')
# Compile the real helper state/functions, not a rewritten model.
a = s.index('  namespace HostPrint {', s.index('void Goto_ThumbPrint('))
b = s.index('\n#endif', a)
code += '\n' + s[a:b]
for name in ('Goto_ThumbPrint', 'HMI_ThumbPrint', 'DWIN_Show_M117'):
    code += '\n' + function(s, 'void ' + name + '(')
code += r'''
int main(){
 char first[]="Heating nozzle. Please wait";
 int before=text.size();DWIN_Show_M117(first);
 assert(checkkey==ThumbPrint&&OctoRefresh&&full_clears==0&&text.back().value==first);
 assert(text.back().color==Color_Blue);
 assert(!strcmp(title,"cube.gcode"));unchanged();title_only(before);
 now+=14999;HostPrint::update_title();assert(text.back().value==first);
 ++now;HostPrint::update_title();assert(text.back().value=="cube"&&text.back().color==Color_Yellow);unchanged();
 // A second message gets a fresh 15 seconds, including while paused.
 isPaused=true;marlin.running=false;marlin.paused=true;OctoRefresh=false;
 char second[]="Paused. Inspect first layer";
 DWIN_Show_M117(first);now+=10000;DWIN_Show_M117(second);
 now+=14999;HostPrint::update_title();assert(text.back().value==second);
 ++now;HostPrint::update_title();assert(text.back().value=="cube"&&isPaused);unchanged();
 // Clear the LCD's pause state from a host event even if its core timer lags.
 before=text.size();HostPrint::set_paused(false);
 assert(!isPaused&&!HMI_flag.pause_flag&&pause_icons==1&&OctoRefresh);
 assert(text.back().value=="cube");title_only(before);unchanged();
 int old_pause=pause_icons;select_print.now=0;event=ENCODER_DIFF_CW;HMI_ThumbPrint();
 assert(pause_icons==old_pause+1); // Encoder uses the host UI state, not the stale timer.
 marlin.paused=false;HostPrint::set_paused(true);int old_continue=continue_icons;
 select_print.now=0;HMI_ThumbPrint();assert(continue_icons==old_continue+1);
 // Do not replace Tune or safety prompts when a state notification/message arrives.
 checkkey=ThumbTune;before=text.size();DWIN_Show_M117(second);HostPrint::set_paused(false);
 assert(checkkey==ThumbTune&&text.size()==before);unchanged();
 Goto_ThumbPrint(false);assert(text[text.size()-1].value==second);unchanged();
 checkkey=AdvancedPause;before=text.size();DWIN_Show_M117(first);
 HostPrint::set_paused(true);now+=15000;HostPrint::update_title();
 assert(checkkey==AdvancedPause&&text.size()==before);
 Goto_ThumbPrint(false);assert(text.back().value=="cube");unchanged();
 // Long text is bounded, scrolls, and never overwrites the original filename.
 char long_message[220];memset(long_message,'x',219);long_message[219]=0;
 before=text.size();DWIN_Show_M117(long_message);assert(strlen(shift_name)==100&&text.back().value.size()==30);
 now+=300;octoUpdateScroll();assert(text.back().value.size()==30&&text.back().color==Color_Blue);title_only(before);
 now+=14700;HostPrint::update_title();assert(text.back().value=="cube");unchanged();
 // A stale rendering session defers drawing; title timeout is still cooperative.
 drawing=true;before=text.size();DWIN_Show_M117(first);assert(text.size()==before);
 drawing=false;now+=15000;HostPrint::update_title();assert(text.back().value=="cube");
 // Unsigned millisecond wrap must not expire early or lose expiry at zero.
 now=uint32_t(0)-15000;DWIN_Show_M117(first);now=uint32_t(0)-1;
 HostPrint::update_title();assert(text.back().value==first);
 now=0;HostPrint::update_title();assert(text.back().value=="cube");unchanged();
 // New jobs/MAIN can cancel an old notification without a delayed redraw.
 DWIN_Show_M117(first);HostPrint::clear_status();checkkey=MainMenu;hasThumbnail=false;
 now+=20000;before=text.size();HostPrint::update_title();assert(text.size()==before);
 // Idle M117 retains the existing full-screen info/Back interaction.
 OctoRefresh=false;isPaused=false;marlin.running=marlin.paused=false;
 DWIN_Show_M117(second);assert(checkkey==M117Info&&full_clears==1&&!OctoRefresh);unchanged();
 // Only complete cancellation notices trigger control actions.
 for(const char *notice:{"Print cancelled","print canceled!","Printing cancelled.",
     "PRINTING CANCELED","Impresion cancelada","Impresión cancelada","IMPRESIÓN CANCELADA"})
   assert(HostPrint::is_cancel_message(notice));
 for(const char *notice:{"Press Cancel","Print not cancelled","Cancel printing?", "Print cancelled?", "Print cancelled test"})
   assert(!HostPrint::is_cancel_message(notice));
 checkkey=ThumbTune;hasThumbnail=isPaused=marlin.paused=drawing=true;
 HMI_flag.pause_flag=HMI_flag.pause_action=true;select_page.now=2;
 char cancelled[]="  Print cancelled!  ";before=full_clears;
 DWIN_Show_M117(cancelled);
 assert(ui.aborts==1&&full_clears==before+1&&checkkey==MainMenu&&select_page.now==0);
 assert(!drawing&&!isPaused&&!OctoRefresh&&!HMI_flag.pause_flag&&!HMI_flag.pause_action);
 now+=20000;before=text.size();HostPrint::update_title();assert(text.size()==before);
 DWIN_Show_M117(cancelled);assert(ui.aborts==1&&checkkey==MainMenu); // Idle duplicate does not send another cancel.
}
'''
with tempfile.TemporaryDirectory(prefix='dwin-host-status-') as folder:
    path = Path(folder) / 'status.cpp'; path.write_text(code)
    binary = path.with_suffix('')
    subprocess.run(['clang++', '-std=c++17', '-O1', '-g', '-fsanitize=address,undefined', '-I', str(ROOT), str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0"), check=True)
print('PASS host resume/icon synchronization, print/paused M117 title only, 15 s expiry/replacement/wrap, menu/prompt preservation and idle info window')
