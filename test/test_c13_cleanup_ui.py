"""Replay production native navigation/field updates and verify preserved controls."""
from pathlib import Path
import subprocess
import re
import tempfile
from test_dwin_input_shaping import function

ROOT=Path(__file__).resolve().parents[1]
DWIN=ROOT/'Marlin/src/lcd/dwin/creality/dwin.cpp'
s=DWIN.read_text()
base=subprocess.check_output(['git','show','244be9d8012cca3c4eb1efbfa084f1f9df0fa1d4:Marlin/src/lcd/dwin/creality/dwin.cpp'],cwd=ROOT,text=True)
# These native implementations must stay byte-for-byte intact.
for name in ('Draw_ThumbTune_Menu','HMI_ThumbTune','ThumbPopup_PauseOrStop',
             'HMI_MainMenu'):
    signature='void '+name+'('
    assert function(s,signature)==function(base,signature), name+' unexpectedly changed'

# Preserve the user's local removal of the four white selection outlines.
# MAIN's local connection banner is exercised below instead of pinned to old text.
for name in ('ICON_Tune','ICON_Pause','ICON_Continue','ICON_Stop'):
    def without_outline(text):
        return re.sub(r'(?m)^    (?://)?DWIN_Draw_Rectangle\(0, Color_White,.*;\n', '    \n', text)
    signature='void '+name+'('
    assert without_outline(function(s,signature))==without_outline(function(base,signature)), name

def host_preprocessed(text,signature='void HMI_PauseOrStop('):
    prefix='#include "Marlin/src/core/macros.h"\n#define OCTOPRINT_PLUGIN 1\n#define SDSUPPORT 0\n'
    return subprocess.check_output(['g++','-E','-P','-x','c++','-I',str(ROOT),'-'],
                                   input=prefix+function(text,signature),text=True)
assert host_preprocessed(s)==host_preprocessed(base), 'Host pause/stop actions changed'

assert re.sub(r'\s+','',host_preprocessed(s,'void HMI_ThumbPrint(')) == re.sub(r'\s+','',host_preprocessed(base,'void HMI_ThumbPrint(')), 'Legacy thumbnail controls changed'

prefix=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <string>
#include <vector>
#include "Marlin/src/core/macros.h"
#define M9001_DRAW_PROTOCOL 1
#define DWIN_CREALITY_320_LCD 1
#define OCTOPRINT_PLUGIN 1
#define DWIN_RENDER_THUMBNAIL 1
#define HAS_ONESTEP_LEVELING 1
#define F(V) V
#define ENCODER_WAIT_MS 20
#define PENDING(N,T) (int32_t((N)-(T))<0)
#define ELAPSED(N,T) (!PENDING(N,T))
using millis_t=uint32_t;
uint32_t clock_ms=0;
uint32_t millis() { return clock_ms; }
bool drawing=false; int cancellations=0;
namespace LcdDraw { bool active(){return drawing;} void cancel(){drawing=false;++cancellations;} }
namespace HostPrint {extern uint32_t total_minutes;void progress_caption();void clear_status();void draw_title();void set_paused(bool);}
enum ENCODER_DiffState {ENCODER_DIFF_NO,ENCODER_DIFF_CW,ENCODER_DIFF_CCW,ENCODER_DIFF_ENTER};
ENCODER_DiffState event=ENCODER_DIFF_NO;
ENCODER_DiffState Encoder_ReceiveAnalyze(){auto e=event;event=ENCODER_DIFF_NO;return e;}
enum {MainMenu,SelectFile,Prepare,Control,Level,Info,ThumbPrint,ThumbTune,ThumbPrint_window,M117Info};
int checkkey=MainMenu;
struct Selection {int now=0;void reset(){now=0;}void set(int n){now=n;}bool inc(int max){if(now>=max-1)return false;++now;return true;}bool dec(){if(!now)return false;--now;return true;}};
Selection select_page,select_prepare,select_control,select_cextr,select_print;
int index_prepare,index_control,MROWS=5;
struct {bool abort_end_flag=false,Refresh_bottom_flag=false;bool select_flag=true,pause_flag=false;int language=0;} HMI_flag;
constexpr int Language_Max=1,LANGUAGE_Main=0,TITLE_X=0,TITLE_Y=0,MAX_SCREEN_BRIGHTNESS=255,
 Color_Yellow=4,Color_White=1,Color_Bg_Black=0,Color_Bg_Blue=2,Color_Blue=3,font8x16=1,font6x12=0,DWIN_FONT_HEAD=1;
bool hasThumbnail=false,OctoRefresh=false,serial_connection_active=true,isPaused=false;
char title[]="Test.gcode";
struct {uint16_t current=1,total=100;uint32_t remaining=600;
 void set_current_layer(int v){current=v;}void set_total_layers(int v){total=v;}
 void progress_reset(){current=0;remaining=0;}void set_progress(int){}void set_remaining_time(int v){remaining=v;}void set_print_time(int){}
 uint16_t get_current_layer(){return current;}uint16_t get_total_layer_count(){return total;}
 uint32_t get_remaining_time(){return remaining;}int get_progress_percent(){return 10;}
} ui;
struct {uint32_t elapsed=300;uint32_t duration(){return elapsed;}} print_job_timer;
struct Text {int color,x,y;std::string text;};
std::vector<Text> text_calls;
std::vector<std::string> labels; int fills=0,icons=0,clears=0;
void DWIN_Draw_String(bool,bool,int,int color,int,int x,int y,const char *s){
 if((color==Color_White||color==Color_Yellow)&&y>=127&&y<=175&&(y-127)%16==0){
  assert(x>=124&&x+strlen(s)*8<=234); // Conservative on-panel glyph width.
  if(y!=127)assert(x*2+strlen(s)*8==358); // Layer row has two colors.
 }
 labels.push_back(s);text_calls.push_back({color,x,y,s});
}
void DWIN_Draw_Rectangle(int,int,int x,int y,int xx,int yy){
 if(y<25&&yy<25)return; // Existing MAIN connection marker stays in the title.
 if(y<123) assert(false && "Native row update overwrote thumbnail/progress");
 if(y!=123){assert(x==120&&xx==233&&y>=127&&yy==y+15&&yy<=190);++fills;}
}
void DWIN_Backlight_SetLuminance(int){}
void DWIN_ICON_Show(int,int,int,int){}
void Clear_Main_Window(){++clears;LcdDraw::cancel();}
void Draw_Back_First(){labels.push_back("Back");}
void ICON_Print(){++icons;}void ICON_Prepare(){++icons;}void ICON_Control(){++icons;}
void ICON_Leveling(int){++icons;}
void Draw_Prepare_Menu(){}void Draw_Control_Menu(){}void Draw_Level_Menu(){}
void DWIN_UpdateLCD(){}
void Goto_MainMenu();void Draw_Print_File_Menu();void Goto_ThumbPrint(bool reset_progress=true);
void Clear_Title_Bar(){}void Draw_OctoTitle(const char*){}void Draw_Mid_Status_Area(bool){}
namespace HostPrint {void clear_status(){}void draw_title(){Draw_OctoTitle(title);}void set_paused(bool v){isPaused=v;HMI_flag.pause_flag=v;}}
int progress_draws=0,cancel_actions=0,last_progress_text=0;
void ICON_Continue(){}void ICON_Pause(){}void ICON_Stop(){}void ICON_Tune(){}
struct {void cancel(){++cancel_actions;}} hostui;
#define SERIAL_ECHOLNPGM(...)
#define SERIAL_ECHOLN(...)
void Draw_Select_Highlight(bool v){HMI_flag.select_flag=v;}
struct {int Auto_PID_Value[3];} HMI_ValueStruct;
struct {void reset(){}void save(){}} settings;
struct {void reboot(){}} hal;
constexpr int Background_ICON=27,Background_reset=2,BG_PRINTING_CIRCLE_MIN=145,ICON_PERCENT_X=12,ICON_PERCENT_Y=75;
void DWIN_ICON_Not_Filter_Show(int,int picture,int x,int y){
 if(picture>=145&&picture<=245){++progress_draws;last_progress_text=text_calls.size();}
}
void delay(int){}
void HMI_ResetLanguage(){}void Save_Auto_PID_Value(){}

'''
code=prefix+'\n'+function(s,'inline ENCODER_DiffState get_encoder_state(')
# Pick the no-media implementations; the first occurrence belongs to SD builds.
for name in ('Draw_Print_File_Menu','HMI_SelectFile'):
    pos=s.rindex('void '+name+'(')
    code+='\n'+function(s[pos:],'void '+name+'(')
for name in ('Goto_MainMenu','HMI_MainMenu'):
    code+='\n'+function(s,'void '+name+'(')
host=(ROOT/'Marlin/src/e3v3se/OctoHost.cpp').read_text()
a=host.index('namespace HostPrint {');b=host.index('\n#endif',a)
code+='\n'+host[a:b]
for name in ('Clear_Below_Area','Draw_Print_ProgressBar','Goto_ThumbPrint','HMI_PauseOrStop'):
    code+='\n'+function(s,'void '+name+'(')
io=(ROOT/'Marlin/src/e3v3se/LcdDrawIO.cpp').read_text()
code+='\nstruct {bool paused=false,wait_for_user=false;bool printJobOngoing(){return true;}bool printingIsPaused(){return paused;}} marlin;'
code+='\nstruct {bool queued=false;bool has_blocks_queued(){return queued;}} planner;'
code+='\nnamespace LcdDrawIO {'+function(io,'bool allowed()')+'}'
code+=r'''
#define PROGRESS_SCALE 1
struct {char key=0;uint32_t value=0;const char *string_arg=nullptr;
 bool seen(char c){return c==key;}bool seenval(char c){return seen(c);}
 bool boolval(char c){return seen(c)&&value;}bool value_bool(){return value;}
 uint32_t value_ulong(){return value;}uint16_t value_ushort(){return value;}
 int value_int(){return value;}uint8_t value_byte(){return value;}float value_float(){return value;}
} parser;
struct GcodeSuite {static void M9000();};
void Clear_Thumb_UpperArea(){}void Goto_ThumbFinish(){}
'''
code+='\n'+function(host,'static void copy_title(')+'\n'+function(host,'void GcodeSuite::M9000(')
code+=r'''
int main(){
 auto at=[](int color,int y)->Text{
  for(auto i=text_calls.rbegin();i!=text_calls.rend();++i)if(i->color==color&&i->y==y)return *i;
  assert(false);return {};
 };
 Goto_MainMenu();assert(checkkey==MainMenu&&icons==4&&HostPrint::total_minutes==0);
 clock_ms=100;event=ENCODER_DIFF_ENTER;HMI_MainMenu();
 assert(checkkey==SelectFile&&labels[labels.size()-2]=="Upload to Host"&&labels.back()=="and start from there");
 clock_ms+=30;event=ENCODER_DIFF_ENTER;HMI_SelectFile();assert(checkkey==MainMenu);
 checkkey=ThumbPrint;assert(marlin.printJobOngoing()&&LcdDrawIO::allowed());
 marlin.paused=true;assert(!LcdDrawIO::allowed());marlin.paused=false;
 marlin.wait_for_user=true;assert(!LcdDrawIO::allowed());marlin.wait_for_user=false;
 planner.queued=true;assert(!LcdDrawIO::allowed());planner.queued=false;
 // Host state events reach the UI without opening S1 or changing metadata.
 parser.key='R';parser.value=1;GcodeSuite::M9000();assert(isPaused&&HMI_flag.pause_flag);
 parser.value=0;GcodeSuite::M9000();assert(!isPaused&&!HMI_flag.pause_flag);
 // Use the production M9000 entry point for the fixed total, independent of live remaining time.
 parser.key='E';parser.value=180;GcodeSuite::M9000();assert(HostPrint::total_minutes==180);
 parser.key='T';parser.value=7;GcodeSuite::M9000();assert(HostPrint::total_minutes==180);
 ui.current=12;ui.total=100;ui.remaining=600;HostPrint::layer_height_um=240;
 HostPrint::refresh(true);
 assert(at(Color_White,127).text=="12 /"&&at(Color_Yellow,127).text=="100");
 assert(at(Color_White,143).text=="0.240 mm");
 assert(at(Color_Yellow,159).text=="03:00"&&at(Color_White,175).text=="00:05");
 for(int i=0;i<4;++i){auto label=at(0x07FF,127+16*i);assert(label.x==12);}
 assert(at(0x07FF,127).text=="Layers:"&&at(0x07FF,143).text=="Layer Height:");
 auto prefix=at(Color_White,127),total=at(Color_Yellow,127);
 assert(total.x==prefix.x+(prefix.text.size()+1)*8);
 assert(prefix.x*2+(prefix.text.size()+1+total.text.size())*8==358);
 // Production Tune return restores both colors, unchanged ETA and the caption after the resource.
 checkkey=ThumbTune;HostPrint::refresh(true);int old_text=text_calls.size();
 Goto_ThumbPrint(false);assert(checkkey==ThumbPrint&&OctoRefresh&&hasThumbnail&&progress_draws==1);
 assert(text_calls.size()==old_text+9);
 // Progress caption remains disabled while investigating communication overhead.
 for(const auto &text:text_calls)assert(text.text!="Progress");
 Draw_Print_ProgressBar();
 int old=fills;for(int i=0;i<8;++i){clock_ms+=1250;HostPrint::refresh(false);}assert(fills==old);
 ui.current=13;for(int i=0;i<4;++i){clock_ms+=1250;HostPrint::refresh(false);}assert(fills==old+1);
 old=fills;ui.remaining=60;print_job_timer.elapsed=360;
 for(int i=0;i<4;++i){clock_ms+=1250;HostPrint::refresh(false);}
 assert(fills==old+1&&at(Color_Yellow,159).text=="03:00"&&at(Color_White,175).text=="00:06");
 assert(at(Color_Yellow,127).text=="100");
 old=fills;checkkey=M117Info;HostPrint::refresh(true);assert(fills==old);
 checkkey=ThumbPrint;drawing=true;HostPrint::refresh(true);assert(fills==old);
 clock_ms+=30;event=ENCODER_DIFF_CW;get_encoder_state();assert(!drawing&&cancellations>=1);
 // Maximum values retain every digit and the two layer colors without overlap.
 ui.current=65535;ui.total=65535;HostPrint::layer_height_um=65535;
 parser.key='E';parser.value=0xFFFFFFFFUL;GcodeSuite::M9000();
 print_job_timer.elapsed=0xFFFFFFFFUL;HostPrint::refresh(true);
 prefix=at(Color_White,127);total=at(Color_Yellow,127);
 assert(prefix.text=="65535 /"&&total.text=="65535"&&prefix.x==127&&total.x==191);
 assert(at(Color_White,143).text=="65.535 mm");
 assert(at(Color_Yellow,159).text=="71582788:15"&&at(Color_White,175).text=="1193046:28");
 // Unknown estimates clear a previous job's total; finishing does not turn it into time-left.
 parser.key='E';parser.value=0;GcodeSuite::M9000();HostPrint::refresh(true);
 assert(at(Color_Yellow,159).text=="--");
 parser.value=180;GcodeSuite::M9000();ui.remaining=0;HostPrint::finish_fields();
 assert(at(Color_Yellow,159).text=="03:00");
 // Shorter values repaint the complete 16-pixel cell without stale digits.
 ui.current=1;ui.total=2;HostPrint::layer_height_um=200;print_job_timer.elapsed=0;
 HostPrint::refresh(true);assert(at(Color_White,127).text=="1 /"&&at(Color_Yellow,127).text=="2");
 assert(at(Color_White,143).text=="0.200 mm");
 // Confirmed idle Stop returns to MAIN and clears the old job's estimate.
 checkkey=ThumbPrint_window;select_print.set(2);HMI_flag.select_flag=true;
 clock_ms+=30;event=ENCODER_DIFF_ENTER;int previous_clears=clears;
 HMI_PauseOrStop();assert(checkkey==MainMenu&&!OctoRefresh&&!hasThumbnail&&HostPrint::total_minutes==0);
 assert(cancel_actions==1&&clears==previous_clears+1&&select_page.now==0);
 checkkey=ThumbPrint_window;HMI_flag.select_flag=false;
 clock_ms+=30;event=ENCODER_DIFF_ENTER;previous_clears=clears;
 HMI_PauseOrStop();assert(checkkey==ThumbPrint&&cancel_actions==1&&clears==previous_clears);
}
'''
with tempfile.TemporaryDirectory(prefix='c13-ui-') as folder:
    source=Path(folder)/'ui.cpp';source.write_text(code)
    binary=Path(folder)/'ui'
    subprocess.run(['g++','-std=c++17','-I',str(ROOT),str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('PASS native MAIN, host-upload Print/Back, preserved Tune/icons/dialogs, two-color full-width layer counts, fixed yellow ETA, live white elapsed, disabled cube caption and Tune restoration, confirmed idle Stop, staggered fields and encoder preemption')
