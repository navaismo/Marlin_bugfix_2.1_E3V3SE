#!/usr/bin/env python3
"""Verify the production Control -> Motion -> Input Shaping LCD entry and drawing."""
from pathlib import Path
import re
import subprocess
import tempfile
import test_dwin_powerloss as base
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]

CAPTURE = r'''
#include <cassert>
#include <vector>
#include <string>
#include <algorithm>
#include <cmath>
struct Caption {int x,y;std::string text;bool visible=true;};
struct Icon {int id,x,y;};
std::vector<Caption> captions;
std::vector<Icon> icons;
int input_values=0,cursor_row=-1;
void rectangle(int fill,int color,int x1,int y1,int x2,int y2){
 if(fill!=1||color!=0)return;
 for(auto &c:captions)
  if(x1<c.x+int(c.text.size())*8 && x2>=c.x && y1<c.y+16 && y2>=c.y)c.visible=false;
}
char *caption_text(const char *key){return const_cast<char*>(std::string(key)=="MSG_INPUT_SHAPING"?"Input Shaping":key);}
'''

EXTRA = r'''
#undef F
#define F(V) const_cast<char*>(V)
#define GET_TEXT_F(V) caption_text(#V)
#define USE_STRING_HEADINGS
constexpr int Color_White=65535,Color_Bg_Black=0,VALUERANGE_X=192;
constexpr int LBLX=42,JPN_OFFSET_TEST=-5,Rectangle_Color=11,Line_Color=12,BLUELINE_X=232;
Selection select_speed,select_acc,select_jerk,select_step,select_input_shaping,select_skew;
void Draw_Motion_Menu();
void Draw_Control_Menu(){}
template<class...T>void DWIN_Frame_AreaCopy(T...){}
void Draw_Max_Speed_Menu(){}
void Draw_Max_Accel_Menu(){}
void Draw_Max_Jerk_Menu(){}
void Draw_Steps_Menu(){}
void Draw_SkewItems_Menu(){}
void Draw_Title(char *s){captions.push_back({14,4,s});}
void draw_max_en(int){}
void draw_speed_en(int,int){}
void draw_max_accel_en(int){}
void draw_jerk_en(int){}
void draw_steps_per_mm(int){}
void DWIN_ICON_Not_Filter_Show(int lib,int id,int x,int y){DWIN_ICON_Show(lib,id,x,y);}
void DWIN_Draw_Line(int,int x1,int y1,int x2,int y2){assert(x1>=0&&x1<=DWIN_WIDTH&&x2>=0&&x2<=DWIN_WIDTH&&y1>=0&&y1<320&&y2>=0&&y2<320);}
template<class...T>void DWIN_Draw_FloatValue(T...){++input_values;}
struct {
 float get_shaping_frequency(int a){return a==0?42.0f:40.0f;}
 float get_shaping_damping_ratio(int){return 0.15f;}
}stepper [[maybe_unused]];
constexpr int X_AXIS=0,Y_AXIS=1;
'''

TESTS = r'''
void control(ENCODER_DiffState e){event=e;HMI_Control();}
void motion_input(ENCODER_DiffState e){event=e;HMI_Motion();}
bool has_input_label(){
 return std::any_of(captions.begin(),captions.end(),[](const Caption &c){
  return c.visible && c.text=="Input Shaping" && c.x==LBLX && c.y>=25;
 });
}
int main(){
 // Exercise both the language-image path and the text fallback of Motion.
 for(int language:{4,Language_Max}){
  HMI_flag.language=language;checkkey=Control;select_control.reset();index_control=MROWS;
  for(int n=0;n<CONTROL_CASE_MOVE;++n)control(ENCODER_DIFF_CW);
  control(ENCODER_DIFF_ENTER);
  assert(checkkey==MotionMenu && select_motion.now==0);
  #if ENABLED(DWIN_INPUT_SHAPING_MENU)
   assert(has_input_label());
   const int row=MOTION_CASE_INPUT_SHAPING;
   assert(row>0 && row<=MROWS);
   bool bounds=false;
   for(const auto &c:captions)if(c.visible&&c.text=="Input Shaping"&&c.y>=25){
    assert(c.y==MBASE(row)||c.y==MBASE(row)+2);
    assert(c.x>=0&&c.x+int(c.text.size())*8<=DWIN_WIDTH);
    assert(c.y+16<=MBASE(MROWS+1)-10);bounds=true;
   }
   assert(bounds);
   assert(std::any_of(icons.begin(),icons.end(),[row](const Icon &i){return i.id==ICON_Setspeed&&i.y==MBASE(row);}));
   for(int n=0;n<row;++n)motion_input(ENCODER_DIFF_CW);
   assert(select_motion.now==row && cursor_row==row && has_input_label());
   motion_input(ENCODER_DIFF_ENTER);assert(checkkey==InputShaping && select_input_shaping.now==0);
   assert(input_values>=4);
   // All four real submenu labels must survive the final drawing commands.
   for(int line=1;line<=4;++line)
    assert(std::any_of(captions.begin(),captions.end(),[line](const Caption&c){return c.visible&&c.x==LBLX&&c.y==MBASE(line);}));
   event=ENCODER_DIFF_ENTER;HMI_InputShaping();
   assert(checkkey==MotionMenu && select_motion.now==row && has_input_label());
  #else
   assert(!has_input_label());
   for(int n=0;n<20;++n)motion_input(ENCODER_DIFF_CW);
   assert(select_motion.now==MOTION_CASE_TOTAL && select_motion.now<=MROWS);
  #endif
 }
 std::cout<<"PASS Control -> Motion: Input Shaping label/icon, bounds, knob entry and return; enabled="<<DWIN_INPUT_SHAPING_MENU<<"\n";
}
'''


def main():
    dwin = (ROOT/'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
    stubs = base.STUBS
    stubs = stubs.replace('Info,Pstats','Info,Pstats,MaxSpeed,MaxAcceleration,MaxJerk,Step,InputShaping,InputShaping_XFreq,InputShaping_YFreq,InputShaping_XZeta,InputShaping_YZeta,SkewCorrection')
    stubs = stubs.replace('struct { int show_mode=0; } HMI_ValueStruct;', 'struct {int show_mode=0;int32_t InputShaping_scaled=0;} HMI_ValueStruct;')
    stubs = stubs.replace('void Draw_Motion_Menu(){}','void Draw_Motion_Menu();')
    stubs = stubs.replace('void Clear_Main_Window(){}','void Clear_Main_Window(){captions.clear();icons.clear();}')
    stubs = re.sub(r'void DWIN_ICON_Show\(int,int icon,int,int y\)\{[^\n]+\}', 'void DWIN_ICON_Show(int,int icon,int x,int y){assert(x>=0&&x<DWIN_WIDTH&&y>=0&&y<320);icons.push_back({icon,x,y});}',stubs)
    stubs = stubs.replace('template<class...Args> void DWIN_Draw_Rectangle(Args...){}','void DWIN_Draw_Rectangle(int a,int b,int c,int d,int e,int f){rectangle(a,b,c,d,e,f);}')
    stubs = stubs.replace('template<class...Args> void DWIN_Draw_String(Args...){}','void DWIN_Draw_String(bool,bool,int,int,int,int x,int y,char *s){captions.push_back({x,y,s});}')
    stubs = stubs.replace('void Move_Highlight(int,int row){assert(row>=0 && row<=MROWS);}','')
    stubs = stubs.replace('void Draw_Menu_Cursor(int row){assert(row>=0 && row<=MROWS);}','')
    for prefix in ('void Draw_Menu_Line(', 'void Draw_More_Icon(', 'void Draw_Menu_Icon(', 'void Draw_Back_First('):
        body = function(stubs,prefix)
        # function() strips comments; these four fixtures have none.
        stubs = stubs.replace(body.rstrip(),'')
    motion_constants = dwin[dwin.index('#define MOTION_CASE_RATE'):dwin.index('// #define LINEAR_ADV_KFACTOR')]
    controls = dwin[dwin.index('#define CONTROL_CASE_TEMP'):dwin.index('#define LEVEL_CASE_BEDVIS')]
    cursor = function(dwin,'void Draw_Menu_Cursor(').replace('void Draw_Menu_Cursor(', 'void Production_Draw_Menu_Cursor(',1)
    cursor += 'void Draw_Menu_Cursor(uint8_t row){assert(row<=MROWS);cursor_row=row;Production_Draw_Menu_Cursor(row); }\n'
    cursor += function(dwin,'void Erase_Menu_Cursor(')+function(dwin,'void Move_Highlight(')
    helpers = cursor+'\n'.join(function(dwin,p) for p in (
        'void Draw_More_Icon(', 'void Draw_Menu_Icon(', 'void Draw_Menu_Item(', 'void Draw_Menu_Line(',
        'void Draw_Back_Label()', 'void Draw_Back_First(', 'void DWIN_Draw_Label(const uint16_t y, char *string)'))
    optional = '#if ENABLED(DWIN_SKEW_MENU)\n'+function(dwin,'void Draw_Skew_Menu(')+'\n#endif\n'
    optional += '#if ENABLED(DWIN_INPUT_SHAPING_MENU)\n'+''.join(function(dwin,p) for p in (
        'void draw_input_shaping(', 'static void Draw_InputShaping_Value(', 'void Draw_InputShaping_Menu()', 'void HMI_InputShaping()'))+'\n#endif\n'
    code = helpers+optional+function(dwin,'void Draw_Motion_Menu()')+function(dwin,'void HMI_Control()')+function(dwin,'void HMI_Motion()')
    resources = sorted(set(re.findall(r'\b(?:ICON_|LANGUAGE_)\w+',code)))
    source = CAPTURE+'enum {'+','.join(resources)+'};\n'+stubs+EXTRA+motion_constants+controls+code+TESTS
    with tempfile.TemporaryDirectory(prefix='dwin-shaping-visibility-') as folder:
        folder = Path(folder)
        cpp,exe = folder/'test.cpp',folder/'test'
        cpp.write_text(source)
        for enabled,jerk,skew,strings in ((1,0,0,0),(1,0,1,0),(1,1,0,0),(1,1,1,0),(1,0,0,1),(0,0,0,0),(0,1,1,1)):
            flags=[f'-DDWIN_INPUT_SHAPING_MENU={enabled}',f'-DHAS_CLASSIC_JERK={jerk}',f'-DDWIN_SKEW_MENU={skew}']
            if strings:
                flags.append('-DUSE_STRING_TITLES')
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function',*flags,str(cpp),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)


if __name__ == '__main__':
    main()
