#!/usr/bin/env python3
"""Exercise production PLR entry points and DWIN handlers with simulated hardware."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DWIN = (ROOT / 'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
PLR = (ROOT / 'Marlin/src/feature/powerloss.cpp').read_text()
M1000 = (ROOT / 'Marlin/src/gcode/feature/powerloss/M1000.cpp').read_text()


def function(source, prefix):
    start = source.index(prefix)
    # Several production helpers are indented inside feature guards.
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <algorithm>
#define CAT_(A,B) A##B
#define CAT(A,B) CAT_(A,B)
#define TERN_0(A,B) B
#define TERN_1(A,B) A
#define TERN(V,A,B) CAT(TERN_,V)(A,B)
#define TERN0(V,A) TERN(V,A,0)
#define TERN_(V,A) TERN(V,A,)
#define SERIAL_ECHOLNPGM(...)
#define ENABLED(V) (V)
#define DISABLED(V) (!(V))
#define DWIN_PLR_MENU 0
#define F(V) V
#define _MIN(A,B) std::min(float(A),float(B))
#define constrain(V,L,H) std::clamp(int(V),int(L),int(H))
#define PLR_HEAT_BED_ON_REBOOT 1
#define POWER_LOSS_RECOVERY 1
#define EEPROM_SETTINGS 1
#define MBASE(L) (34+36*(L))
#define WITHIN(V,L,H) ((V)>=(L) && (V)<=(H))
#define HAS_PLR_BED_THRESHOLD 1
#define HAS_PLR_UI_FLAG 1
#define HAS_MARLINUI_MENU 0
#define EXTENSIBLE_UI 0
#define DEBUG_POWER_LOSS_RECOVERY 0
#define DWIN_CREALITY_LCD 1
#define DWIN_CREALITY_LCD_JYERSUI 0
#define DWIN_CREALITY_320_LCD 1
#define DWIN_CREALITY_480_LCD 0
#define BED_MAX_TARGET 110
#define Z_MAX_POS 250
using celsius_t=int16_t;
struct MediaFile {};
constexpr int Color_Bg_Window=0,Select_Color=1,font8x16=8,Popup_Text_Color=2,
 MENU_CHAR_LIMIT=24,DWIN_WIDTH=240,MENU_CHR_W=8,MROWS=5;
enum { MainMenu,SelectFile,Control,PowerLossResume,PrintProcess,Tune,TemperatureID,MotionMenu,Print_window,Info,Pstats };
enum ENCODER_DiffState { ENCODER_DIFF_NO, ENCODER_DIFF_CW, ENCODER_DIFF_CCW, ENCODER_DIFF_ENTER };
int checkkey=MainMenu, previews=0, main_visits=0, print_visits=0, polls=0, control_row=-1;
bool dwin_abort_flag=false,reset_flag=false,hasThumbnail=false;
struct {bool enabled=false;} EncoderRate;
ENCODER_DiffState event=ENCODER_DIFF_NO;
ENCODER_DiffState get_encoder_state() { ++polls; auto e=event;event=ENCODER_DIFF_NO;return e; }
struct { int language=4; bool select_flag=true,Refresh_bottom_flag=true,done_confirm_flag=false,
 print_finish=false,disallow_recovery_flag=false; } HMI_flag;
struct { int show_mode=0; } HMI_ValueStruct;
struct Selection {
 int now=0; void reset(){now=0;} void set(int n){now=n;}
 bool inc(int count){if(now+1>=count)return false;++now;return true;}
 bool dec(){if(!now)return false;--now;return true;}
} select_page,select_print,select_control,select_temp,select_motion;
int index_control=MROWS;
constexpr int TITLE_X=12,TITLE_Y=4,ICON=0,Language_Max=26,JPN_OFFSET=-5,DWIN_SCROLL_UP=1,DWIN_SCROLL_DOWN=0;
struct {bool save(){return true;} bool load(){return true;}} settings;
struct {
 bool mounted=true;
 int root_calls=0;
 std::string path,selected;
 bool isMounted(){return mounted;}
 bool isStillPrinting(){return marlin_printing;}
 bool marlin_printing=false;
 void cdroot(){++root_calls;}
 const char *diveToFile(bool,MediaFile*&,const char *name){path=name;return strrchr(name,'/')+1;}
 void selectFileByName(const char *name){selected=name;}
 const char *longest_filename(){return "Interrupted nested print.gcode";}
} card;
struct { bool printing=false,paused=false; bool printingIsActive(){return printing;} bool printingIsPaused(){return paused;} } marlin;
struct {
 int target=0,current=20;
 void setTargetBed(int value){target=value;}
 int degBed(){return current;}
} thermalManager;
struct { std::string command;void inject(const char *value){command=value;} } queue;
struct PrintJobRecovery {
 bool ui_flag_resume=false,enabled=true,valid_data=false;
 int resumes=0,purges=0,loads=0,bed_temp_threshold=0;
 struct { char sd_filename[80]="/MODELS/TEST/OLD.GCO"; celsius_t target_temperature_bed=60; int valid_head=1; } info;
 bool valid(){return valid_data && card.mounted;}
 void load(){++loads;}
 void purge(){valid_data=false;++purges;}
 void enable(bool);
 void changed();
 void save(bool){}
 void resume(){++resumes;assert(checkkey==PrintProcess);}
 void set_bed_temp(bool);
 void cancel();
 bool check();
} recovery;
struct { bool S=false,C=false; bool seen_test(char c){return c=='S'?S:C;} } parser;
struct GcodeSuite { static void M1000(); };
void plr_error(const char*) {}
void DWIN_PowerLossResume();
void Goto_PrintProcess(){checkkey=PrintProcess;++print_visits;}
void Goto_MainMenu(){checkkey=MainMenu;++main_visits;}
void Goto_FilePreview(){++previews;}
void Popup_Window_Resume(){}
void Erase_Menu_Text(int row){control_row=row;}
void Draw_Menu_Line(int row,int=0,const char * =nullptr,bool=false){assert(row>=0 && row<=MROWS);}
void DWIN_ICON_Show(int,int icon,int,int y){if(icon!=LANGUAGE_Control)assert(y>=25 && y<=MBASE(MROWS)+10);}
void Draw_Menu_Cursor(int row){assert(row>=0 && row<=MROWS);}
void Move_Highlight(int,int row){assert(row>=0 && row<=MROWS);}
void Draw_More_Icon(int){}
void Draw_Menu_Icon(int,int){}
void Draw_Back_First(bool=false){}
void Item_Control_Reset(int){}
void Item_Control_Info(int){}
void Item_Control_Stats(int){}
void Scroll_Menu(int){}
void Clear_Main_Window(){}
void Draw_Mid_Status_Area(bool){}
void Draw_Temperature_Menu(){}
void Draw_Motion_Menu(){}
void Popup_window_PauseOrStop(){}
void Draw_Info_Menu(){}
void Draw_PStats_Menu(){}
void HMI_AudioFeedback(bool){}
void Draw_Chkb_Line(int,bool){}
template<class...Args> void DWIN_Draw_Rectangle(Args...){}
template<class...Args> void DWIN_Draw_String(Args...){}
void DWIN_UpdateLCD(){}
'''

TESTS = r'''
void input(ENCODER_DiffState state){event=state;HMI_PowerLossRecovery();}
int main(){
 // Boot checkpoint selects M1000 S before a new-file preview is allowed.
 recovery.valid_data=true;
 assert(recovery.check());assert(queue.command=="M1000S" && recovery.loads==1);
 parser.S=true;GcodeSuite::M1000();
 assert(recovery.ui_flag_resume && thermalManager.target==60+PLR_HEAT_BED_EXTRA && recovery.resumes==0);
 checkkey=MainMenu;one_click_print();assert(previews==0);
 Goto_PowerLossRecovery();
 assert(checkkey==PowerLossResume && !recovery.ui_flag_resume);
 assert(card.path=="/MODELS/TEST/OLD.GCO" && card.selected=="OLD.GCO");
 one_click_print();assert(previews==0);
 // No input returns immediately; the main loop can service heaters/media.
 for(int n=0;n<100;++n)input(ENCODER_DIFF_NO);
 assert(checkkey==PowerLossResume && recovery.resumes==0 && polls==100);
 // Turning to Cancel and accepting never resumes or previews a new file.
 input(ENCODER_DIFF_CCW);assert(!HMI_flag.select_flag);
 input(ENCODER_DIFF_ENTER);
 assert(checkkey==MainMenu && !recovery.valid_data && thermalManager.target==0);
 assert(recovery.resumes==0 && previews==0);
 recovery.valid_data=true;queue.command.clear();
 Goto_PowerLossRecovery();
 card.mounted=false;input(ENCODER_DIFF_ENTER);
 assert(queue.command.empty() && checkkey==PowerLossResume);
 card.mounted=true;
 dwin_abort_flag=HMI_flag.done_confirm_flag=HMI_flag.print_finish=HMI_flag.disallow_recovery_flag=true;
 input(ENCODER_DIFF_ENTER);
 assert(queue.command=="M1000" && checkkey==PrintProcess);
 assert(!dwin_abort_flag && !HMI_flag.done_confirm_flag && !HMI_flag.print_finish && !HMI_flag.disallow_recovery_flag);
 parser.S=false;GcodeSuite::M1000();assert(recovery.resumes==1);
 // Automatic threshold recovery must initialize the print UI too.
 checkkey=MainMenu;hasThumbnail=true;recovery.bed_temp_threshold=50;thermalManager.current=55;
 parser.S=true;GcodeSuite::M1000();
 assert(checkkey==PrintProcess && recovery.resumes==2 && !recovery.ui_flag_resume && !hasThumbnail);
 // Optional reboot heat is nonblocking, bounded, and never heats a saved-off bed.
 recovery.info.target_temperature_bed=130;recovery.set_bed_temp(true);assert(thermalManager.target==110);
 recovery.info.target_temperature_bed=0;recovery.set_bed_temp(true);assert(thermalManager.target==0);
 recovery.set_bed_temp(false);assert(thermalManager.target==0);
 // An absent/invalid checkpoint must not leave a recovery command pending.
 recovery.valid_data=false;queue.command.clear();
 assert(!recovery.check() && queue.command.empty());
 // After recovery is cancelled/absent, normal One Click Print is available.
 checkkey=MainMenu;one_click_print();assert(previews==1);
 marlin.printing=true;one_click_print();assert(previews==1);marlin.printing=false;
 // With the menu flag disabled, Control must expose no PLR entry.
 checkkey=Control;select_control.reset();index_control=MROWS;control_row=-1;
 for(int n=0;n<CONTROL_CASE_TOTAL;++n){event=ENCODER_DIFF_CW;HMI_Control();Draw_Control_Menu();}
 assert(CONTROL_CASE_TOTAL==CONTROL_CASE_STATS && select_control.now==CONTROL_CASE_STATS && control_row==-1);
 event=ENCODER_DIFF_ENTER;HMI_Control();assert(checkkey==Pstats && recovery.enabled);
 checkkey=Control;
 for(int n=0;n<CONTROL_CASE_TOTAL;++n){event=ENCODER_DIFF_CCW;HMI_Control();Draw_Control_Menu();}
 assert(select_control.now==0 && index_control==MROWS);
 std::cout<<"PASS PLR menu disabled: no Control entry, normal navigation and visible row bounds\n";
 std::cout<<"PASS PLR checkpoint -> M1000 S -> DWIN dialog, nested path, OCP priority, cancel/resume, missing SD, bed heating, automatic resume\n";
}
'''


def main():
    # The boot ordering and dispatcher are production integration points.
    card_source = (ROOT / 'Marlin/src/sd/cardreader.cpp').read_text()
    boot = card_source[card_source.index('  // First mount on boot?'):card_source.index('  // On first mount at boot run auto#.g')]
    assert boot.index('recovery.check()') < boot.index('one_click_check()')
    assert 'DWIN_lcd_sd_status && recovery.ui_flag_resume' in DWIN
    assert 'case PowerLossResume:\n    HMI_PowerLossRecovery();' in DWIN
    assert 'Item_Control_PLR(CSCROL(CONTROL_CASE_PLR));' in DWIN
    assert 'case CONTROL_CASE_PLR:\n          Item_Control_PLR(MROWS);' in DWIN
    assert 'dwin_flag' not in DWIN
    import re
    controls = DWIN[DWIN.index('#define CONTROL_CASE_TEMP'):DWIN.index('#define LEVEL_CASE_BEDVIS')]
    drawing = function(DWIN, 'void Draw_Control_Menu()')
    control_handler = function(DWIN, 'void HMI_Control()')
    icons = sorted(set(re.findall(r'\b(?:ICON_|LANGUAGE_)\w+', drawing + control_handler)))
    resources = 'enum {' + ','.join(icons) + '};\n'
    helpers = '\n'.join(function(DWIN, prefix) for prefix in (
        'void Item_Control_PLR(', 'static void Draw_PLR_Selection(',
        'static void Goto_PowerLossRecovery()', 'static void HMI_PowerLossRecovery()',
        'void DWIN_PowerLossResume()', 'void one_click_print()',
    ))
    core = '\n'.join(function(PLR, prefix) for prefix in (
        'void PrintJobRecovery::enable(', 'void PrintJobRecovery::changed()',
        'bool PrintJobRecovery::check()', 'void PrintJobRecovery::cancel()',
        'void PrintJobRecovery::set_bed_temp(',
    ))
    command = function(M1000, 'void GcodeSuite::M1000()')
    with tempfile.TemporaryDirectory(prefix='dwin-plr-') as folder:
        cpp,binary=Path(folder)/'test.cpp',Path(folder)/'test'
        cpp.write_text(resources+STUBS+controls+helpers+drawing+control_handler+core+command+TESTS)
        # Exercise both an omitted extra-temperature option and an explicit value.
        for extra in (None,5):
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',
                            *([] if extra is None else [f'-DPLR_HEAT_BED_EXTRA={extra}']),
                            str(cpp),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
        # The production header must honor explicit resume clearance without UPS.
        header=(ROOT/'Marlin/src/feature/powerloss.h').read_text()
        start=header.index('#if !defined(POWER_LOSS_STATE)')
        end=header.index('//#define DEBUG_POWER_LOSS_RECOVERY',start)
        zline=next(line.strip() for line in PLR.splitlines() if 'const float z_raised =' in line)
        cpp.write_text('#define PIN_EXISTS(V) 0\n'+header[start:end]+r'''
#include <cassert>
#include <algorithm>
#define _MIN(A,B) std::min(float(A),float(B))
#define Z_MAX_POS 250
int main(){
 static_assert(POWER_LOSS_ZRAISE==5);
 struct {float zraise=POWER_LOSS_ZRAISE;} info;
 for(float z_print:{10.0f,249.0f}) {
''' + zline + r'''
  assert(z_raised==(z_print==10.0f?15.0f:250.0f));
 }
}
''')
        subprocess.run(['g++','-std=c++17','-DPOWER_LOSS_ZRAISE=5',str(cpp),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
        print('PASS configured Z clearance without UPS and Z maximum limit')


if __name__=='__main__':
    main()
