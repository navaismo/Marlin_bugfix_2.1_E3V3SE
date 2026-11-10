#!/usr/bin/env python3
"""Replay the production completion sound, menu, EEPROM and SD/host entry points."""
from pathlib import Path
import os
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
settings = (ROOT / 'Marlin/src/module/settings.cpp').read_text()
host = (ROOT / 'Marlin/src/e3v3se/OctoHost.cpp').read_text()
start = source.index('  namespace PrintDoneSound {')
end = source.index('\n#endif', start)
sound = source[start:end]
assert 'delay(' not in sound and 'BUZZ(' not in sound and 'new ' not in sound

prefix = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include "Marlin/src/core/macros.h"
#define DWIN_LCD_BEEP 1
#define M9001_DRAW_PROTOCOL 1
#define DWIN_RENDER_THUMBNAIL 1
#define OCTOPRINT_PLUGIN 1
#define HAS_MEDIA SDSUPPORT
#define HAS_FILAMENT_SENSOR 1
#define F(V) V
#define PENDING(N,T) (int32_t((N)-(T))<0)
#define BEEPER_PIN 1
#define HIGH 1
#define LOW 0
#define WRITE(P,V) pins.push_back({now,bool(V)})
#define MBASE(R) (34+36*(R))
using millis_t=uint32_t;
uint32_t now=100;
millis_t millis(){return now;}
struct Pin{millis_t time;bool on;};std::vector<Pin> pins;
enum ENCODER_DiffState {ENCODER_DIFF_NO,ENCODER_DIFF_CW,ENCODER_DIFF_CCW,ENCODER_DIFF_ENTER};
ENCODER_DiffState event=ENCODER_DIFF_NO;
ENCODER_DiffState get_encoder_state(){return event;}
struct Selection{uint8_t now=0;bool inc(int n){if(now+1>=n)return false;++now;return true;}
 bool dec(){if(!now)return false;--now;return true;}}select_display,select_prepare;
enum {Prepare,Display_Menu,Max_LCD_Bright,Dimm_Bright,DimmTime,MainMenu,SelectFile,ThumbPrint,M117Info};
int checkkey=Display_Menu;
constexpr int MROWS=5,ICON_Contact=1,ICON_PrintSize=2,ICON_Hardware_version=3,ICON_PrintTime=4,
 ICON_WriteEEPROM=5,font8x16=1,Color_White=1,Color_Bg_Black=0,Select_Color=2,VALUERANGE_X=180,
 LANGUAGE_Store=1,JPN_OFFSET=0,PREPARE_CASE_DISPLAY=9,LANGUAGE_LEVEL_FINISH=2,
 TITLE_X=0,TITLE_Y=0,LANGUAGE_Confirm=3,OK_BUTTON_X=10,Language_Max=1,PROGRESS_SCALE=1,DWIN_WIDTH=240;
int MAX_SCREEN_BRIGHTNESS=230,DIMM_SCREEN_BRIGHTNESS=175,TURN_OFF_TIME=5;
uint8_t toggle_LCDBeep=0;
bool OctoRefresh=false,serial_connection_active=false;
char title[50]={};
struct {bool Refresh_bottom_flag=false,done_confirm_flag=false,print_finish=false,
 disallow_recovery_flag=false;int language=0;} HMI_flag;
struct {int Dimm_Time=5;}HMI_ValueStruct;
struct {bool enabled=false;}EncoderRate;
uint8_t stored=0;
#define EEPROM_WRITE(V) stored=(V)
#define EEPROM_READ(V) (V)=stored
void save_beeper();
struct {int saves=0;void save(){++saves;save_beeper();}}settings;
std::vector<std::string> labels;int clears=0,checks=0;bool last_check=false;
void Clear_Main_Window(){++clears;labels.clear();}
void Draw_Mid_Status_Area(bool){}void Draw_Back_First(bool=true){}
void Draw_Title(const char*){}
void DWIN_Draw_Label(int y,const char*s){assert(y>=34&&y<=MBASE(5));labels.emplace_back(s);}
void Draw_Menu_Line(int row,int){assert(row>=0&&row<=MROWS);}
void Draw_Chkb_Line(int row,bool v){assert(row>=0&&row<=MROWS);++checks;last_check=v;}
void Draw_Menu_Cursor(int row){assert(row>=0&&row<=MROWS);}
void DWIN_Draw_IntValue(bool,bool,int,int,int,int,int,int,int,int){}
void DWIN_ICON_Show(int,int,int,int y){assert(y<=MBASE(5));}
void DWIN_ICON_Not_Filter_Show(int,int,int,int){}
void Move_Highlight(int,int row){assert(row>=0&&row<=MROWS);}
void Draw_Prepare_Menu(){}void DWIN_UpdateLCD(){}
void Clear_Below_Area(){}void Clear_Title_Bar(){}void Draw_Print_ProgressBar(){}
void DWIN_Draw_Rectangle(int,int,int,int,int,int){}
void Clear_Thumb_UpperArea(){}void Goto_ThumbPrint(){}void Draw_OctoTitle(const char*){}
void Goto_MainMenu(){checkkey=MainMenu;}
struct {void set_progress(int){}void set_current_layer(int){}int get_total_layer_count(){return 30;}
 void set_remaining_time(int){}void set_total_layers(int){}void set_print_time(uint32_t){} }ui;
namespace HostPrint{uint16_t layer_height_um=0;uint32_t total_minutes=0;
 void clear_status(){}void finish_fields(){}void set_paused(bool){}void refresh(bool){}}
struct {bool wait_for_user=false;bool printJobOngoing(){return false;}
 bool printingIsPaused(){return false;}}marlin;
struct {bool has_blocks_queued(){return false;}}planner;
namespace LcdDraw{bool busy=false;bool active(){return busy;}}
void DWIN_HandleScreen(){}void EachMomentUpdate(){}void HMI_SDCardUpdate(){}
void Remove_card_window_check(){}
struct {bool isPrinting(){return false;}}card;
struct {char key=0;uint32_t value=0;const char *string_arg=nullptr;
 bool seen(char c){return key==c;}bool seenval(char c){return seen(c);}
 bool boolval(char c){return seen(c)&&value;}bool value_bool(){return value;}
 int value_int(){return value;}uint32_t value_ulong(){return value;}
 uint16_t value_ushort(){return value;}uint8_t value_byte(){return value;}
 float value_float(){return value;}}parser;
struct GcodeSuite{static void M9000();};
'''
code = prefix + sound
# Compile the real save/load statements, preserving the serialized byte count.
save = settings[settings.index('      // Reuse the existing byte:'):]
save = save[:save.index('      // uint8_t prealert')]
load = settings[settings.index('        uint8_t beep;'):]
load = load[:load.index('        // uint8_t prealert')]
code += '\nvoid save_beeper(){\n' + save + '\n}\nvoid load_beeper(){\n' + load + '\n}\n'
reset = settings[settings.index('  #if ALL(DWIN_CREALITY_LCD, DWIN_LCD_BEEP)'):]
reset = reset[reset.index('\n') + 1:reset.index('  #endif')]
code += '\nvoid reset_beeper(){\n' + reset + '\n}\n'
for name in ('Draw_Display_Menu', 'HMI_Display_Menu', 'DWIN_Update', 'Goto_ThumbFinish'):
    code += '\n' + function(source, 'void ' + name + '(')
code += '\n' + function(host, 'static void copy_title(')
code += '\n' + function(host, 'void GcodeSuite::M9000(')
code += r'''
void drain(){for(int n=0;n<1000;++n){++now;PrintDoneSound::tick();}}
int main(){
 // Legacy EEPROM values and all combinations of the two independent switches.
 for(stored=0;stored<4;++stored){load_beeper();assert(toggle_LCDBeep==(stored&1));
   assert(PrintDoneSound::enabled==bool(stored&2));}
 for(int click=0;click<2;++click)for(int done=0;done<2;++done){
   toggle_LCDBeep=click;PrintDoneSound::enabled=done;save_beeper();
   assert(stored==(click|(done<<1)));toggle_LCDBeep=9;PrintDoneSound::enabled=!done;
   load_beeper();assert(toggle_LCDBeep==click&&PrintDoneSound::enabled==bool(done));}
 PrintDoneSound::enabled=true;reset_beeper();assert(!PrintDoneSound::enabled);
 pins.clear();PrintDoneSound::start();drain();assert(pins.empty());
 PrintDoneSound::enabled=true;now=100;PrintDoneSound::start();PrintDoneSound::tick();
 assert(pins.size()==1&&pins[0].on);PrintDoneSound::start(); // No restart while playing.
 drain();assert(pins.size()==6);
 uint32_t times[]={100,180,260,340,420,660};
 for(int i=0;i<6;++i){assert(pins[i].time==times[i]);assert(pins[i].on==!(i&1));}
 // Disabling while sounding releases the pin; clock rollover is safe.
 PrintDoneSound::start();PrintDoneSound::tick();PrintDoneSound::enabled=false;
 PrintDoneSound::tick();assert(!pins.back().on);auto n=pins.size();drain();assert(pins.size()==n);
 PrintDoneSound::enabled=true;now=UINT32_MAX-70;pins.clear();PrintDoneSound::start();
 PrintDoneSound::tick();drain();assert(pins.size()==6&&!pins.back().on);
 // Menu toggles only the completion switch; Store uses the existing save path.
 select_display.now=0;Draw_Display_Menu();assert(labels.back()=="Print done sound");
 constexpr int done_item=DWIN_DIMM_MENU?5:2,store_item=done_item+1;
 auto enter=[](){event=ENCODER_DIFF_ENTER;HMI_Display_Menu();};
 select_display.now=done_item;PrintDoneSound::enabled=false;toggle_LCDBeep=0;pins.clear();
 enter();assert(PrintDoneSound::enabled&&toggle_LCDBeep==0&&last_check&&pins.empty());
 enter();assert(!PrintDoneSound::enabled&&!last_check&&pins.empty());
 enter();select_display.now=store_item;enter();assert(settings.saves==1&&stored==2);
 // Traverse every row both ways, including the optional dimmer's scrolled Store.
 select_display.now=0;event=ENCODER_DIFF_CW;
 for(int i=0;i<store_item+2;++i)HMI_Display_Menu();assert(select_display.now==store_item);
 event=ENCODER_DIFF_CCW;for(int i=0;i<store_item+2;++i)HMI_Display_Menu();assert(!select_display.now);
 enter();assert(checkkey==Prepare&&select_prepare.now==PREPARE_CASE_DISPLAY);
 // Host uses actual M9000 S1/F1 paths; repeated F1 doesn't replay a completed alert.
 checkkey=MainMenu;parser.key='S';parser.value=1;GcodeSuite::M9000();
 parser.key='F';GcodeSuite::M9000();PrintDoneSound::tick();drain();
 assert(pins.size()==6&&HMI_flag.done_confirm_flag);GcodeSuite::M9000();drain();assert(pins.size()==6);
 checkkey=MainMenu;parser.key='S';GcodeSuite::M9000();assert(!HMI_flag.done_confirm_flag);
 parser.key='F';GcodeSuite::M9000();PrintDoneSound::tick();drain();assert(pins.size()==12);
 // SD completion is observed even in a menu and during host drawing ownership.
 #if SDSUPPORT
 PrintDoneSound::cancel();HMI_flag.print_finish=false;DWIN_Update();pins.clear();
 checkkey=Display_Menu;LcdDraw::busy=true;HMI_flag.print_finish=true;DWIN_Update();drain();
 assert(pins.size()==6);DWIN_Update();drain();assert(pins.size()==6);
 HMI_flag.print_finish=false;DWIN_Update(); // Abort/no completion stays silent.
 drain();assert(pins.size()==6);HMI_flag.print_finish=true;DWIN_Update();drain();assert(pins.size()==12);
 #endif
}
'''
with tempfile.TemporaryDirectory(prefix='dwin-print-done-') as folder:
    cpp = Path(folder) / 'replay.cpp'
    binary = Path(folder) / 'replay'
    cpp.write_text(code)
    for dimm, sd in ((0, 0), (1, 0), (0, 1), (1, 1)):
        subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++17', '-g',
                        '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                        '-I', str(ROOT), f'-DDWIN_DIMM_MENU={dimm}', f'-DSDSUPPORT={sd}',
                        str(cpp), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
        print(f'PASS completion sound / EEPROM / menu / host / SD: dimmer={dimm}, SD={sd}')
