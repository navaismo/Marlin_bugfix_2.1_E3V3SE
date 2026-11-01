#!/usr/bin/env python3
"""Exercise legacy DWIN edits against the production Stepper, M593 and EEPROM paths."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, prefix):
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    start = source.index(prefix)
    brace = source.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <map>
#include <sstream>
#include <string>
#include <vector>
#include <iostream>
#define CAT_(A,B) A##B
#define CAT(A,B) CAT_(A,B)
#define TERN_0(A,B) B
#define TERN_1(A,B) A
#define TERN(V,A,B) CAT(TERN_,V)(A,B)
#define TERN0(V,A) TERN(V,A,0)
#define TERN_(V,A) TERN(V,A,)
#define ENABLED(V) (V)
#define DISABLED(V) (!(V))
#define ALL(A,B) ((A)&&(B))
#define ANY(A,B) ((A)||(B))
#define NOLESS(V,L) do{if((V)<(L))(V)=(L);}while(0)
#define LIMIT(V,L,H) do{if((V)<(L))(V)=(L);else if((V)>(H))(V)=(H);}while(0)
#define WITHIN(V,L,H) ((V)>=(L)&&(V)<=(H))
#define FLOOR(V) floorf(V)
#define sq(V) ((V)*(V))
#define F(V) V
#define GET_TEXT_F(V) #V
#define GCODE_ERR_MSG(...) "invalid frequency"
#define SERIAL_ECHO_MSG(...) serial(__VA_ARGS__)
#define SERIAL_ECHOLNPGM(...) serial(__VA_ARGS__)
#define MARLIN_SMALL_BUILD 0
#define INPUT_SHAPING_X 1
#define INPUT_SHAPING_Y 1
#define INPUT_SHAPING_Z 0
#define HAS_ZV_SHAPING 1
#define HAS_HOTEND 0
#define DWIN_INPUT_SHAPING_MENU 1
#define STEPPER_TIMER_RATE 2000000UL
#define EXTRUDE_MAXLENGTH_e 1000
#define MINUNITMULT 10
#define MBASE(N) (34+36*(N))
using shaping_time_t=SHAPING_TIMER_TYPE;
enum AxisEnum {X_AXIS,Y_AXIS,Z_AXIS};
enum ENCODER_DiffState {ENCODER_DIFF_NO,ENCODER_DIFF_CW,ENCODER_DIFF_CCW,ENCODER_DIFF_ENTER};
enum {InputShaping,InputShaping_XFreq,InputShaping_YFreq,InputShaping_XZeta,InputShaping_YZeta,MotionMenu,Extruder};
constexpr int font8x16=8,Color_White=65535,Color_Bg_Black=0,Select_Color=1,VALUERANGE_X=172,
 ICON_MaxAccX=1,ICON_MaxAccY=2,ICON_MaxSpeedX=3,ICON_MaxSpeedY=4,MOTION_CASE_INPUT_SHAPING=5;
int checkkey=InputShaping,lcd_updates=0,motion_draws=0;
struct {int encoderMoveValue=1;bool enabled=false;}EncoderRate;
struct {int32_t InputShaping_scaled=0;}HMI_ValueStruct;
struct {bool Refresh_bottom_flag=false;}HMI_flag;
struct Selection {int now=0;bool inc(int n){if(now+1>=n)return false;++now;return true;}bool dec(){if(!now)return false;--now;return true;}}select_input_shaping,select_motion;
ENCODER_DiffState event=ENCODER_DIFF_NO;
ENCODER_DiffState Encoder_ReceiveAnalyze(){auto e=event;event=ENCODER_DIFF_NO;return e;}
ENCODER_DiffState get_encoder_state(){return Encoder_ReceiveAnalyze();}
struct {bool enabled=true;int off=0;bool isr_state(){return enabled;}void isr_off(){enabled=false;++off;}void isr_on(){enabled=true;}}hal;
struct {int syncs=0;void synchronize(){++syncs;}}planner;
struct {int32_t x=123,y=456;}count_position;
std::map<int,int32_t> drawn;
void DWIN_Draw_FloatValue(bool,bool,int,int,int,int,int digits,int decimals,int,int y,int32_t value){assert(decimals==2);assert(digits==3||digits==1);drawn[y]=value;}
void DWIN_UpdateLCD(){++lcd_updates;}
void Move_Highlight(int,int){}
void Draw_Motion_Menu(){++motion_draws;}
void Clear_Main_Window(){}
void Draw_Title(const char*){}
void DWIN_Draw_Label(int,const char*){}
void Draw_Back_First(){}
void Draw_Menu_Line(int,int){}
std::ostringstream log_output;
template<class...T>void serial(T...v){(log_output<<...<<v);log_output<<'\n';}
void report_heading_etc(bool,const char*){}
void report_echo_start(bool){}
struct Parser {
 std::map<char,float> values;char current=0;
 bool seen_any(){return !values.empty();}
 bool seen_test(char c){return values.count(c);}
 bool seen(char c){current=c;return values.count(c);}
 float value_float(){return values.at(current);}
}parser;
struct GcodeSuite {static void M593();static void M593_report(bool=true);};
std::vector<uint8_t> eeprom;
size_t read_index=0;
template<class T>void ee_write(const T &value){auto p=reinterpret_cast<const uint8_t*>(&value);eeprom.insert(eeprom.end(),p,p+sizeof(value));}
template<class T>void ee_read(T &value){assert(read_index+sizeof(value)<=eeprom.size());memcpy(&value,eeprom.data()+read_index,sizeof(value));read_index+=sizeof(value);}
#define EEPROM_WRITE(V) ee_write(V)
#define EEPROM_READ(V) ee_read(V)
'''

TESTS = r'''
void menu(ENCODER_DiffState e){event=e;HMI_InputShaping();}
void edit(ENCODER_DiffState e,int amount=1){event=e;EncoderRate.encoderMoveValue=amount;HMI_InputShaping_Values();}
bool close(float a,float b){return fabsf(a-b)<0.0001f;}
void enter(int row){checkkey=InputShaping;select_input_shaping.now=row;menu(ENCODER_DIFF_ENTER);assert(EncoderRate.enabled);}
int main(){
 stepper.set_shaping_frequency(X_AXIS,42);stepper.set_shaping_frequency(Y_AXIS,40);
 stepper.set_shaping_damping_ratio(X_AXIS,0.15f);stepper.set_shaping_damping_ratio(Y_AXIS,0.15f);
 Draw_InputShaping_Menu();assert(drawn.at(MBASE(INPUT_SHAPING_CASE_XFREQ)+3)==4200);
 enter(INPUT_SHAPING_CASE_XFREQ);assert(HMI_ValueStruct.InputShaping_scaled==4200);
 const int before=planner.syncs;edit(ENCODER_DIFF_CW,437);assert(close(stepper.get_shaping_frequency(X_AXIS),42));
 edit(ENCODER_DIFF_ENTER);assert(checkkey==InputShaping && !EncoderRate.enabled);
 assert(close(stepper.get_shaping_frequency(X_AXIS),46.37f));assert(planner.syncs==before+1 && hal.enabled);
 assert(ShapingQueue::delay_x==shaping_time_t(1000000.0f/46.37f));
 assert(stepper.shaping_x.enabled && stepper.shaping_x.last_block_end_pos==123);
 enter(INPUT_SHAPING_CASE_YFREQ);edit(ENCODER_DIFF_CCW,123);edit(ENCODER_DIFF_ENTER);
 assert(close(stepper.get_shaping_frequency(Y_AXIS),38.77f));assert(close(stepper.get_shaping_frequency(X_AXIS),46.37f));
 assert(ShapingQueue::delay_y==shaping_time_t(1000000.0f/38.77f));
 enter(INPUT_SHAPING_CASE_XZETA);assert(HMI_ValueStruct.InputShaping_scaled==15);edit(ENCODER_DIFF_CW,18);edit(ENCODER_DIFF_ENTER);
 assert(close(stepper.get_shaping_damping_ratio(X_AXIS),0.33f));assert(stepper.shaping_x.factor1+stepper.shaping_x.factor2==128);
 assert(stepper.shaping_x.factor2<64 && stepper.shaping_x.factor2>0);
 enter(INPUT_SHAPING_CASE_YZETA);edit(ENCODER_DIFF_CW,100000);edit(ENCODER_DIFF_ENTER);
 assert(close(stepper.get_shaping_damping_ratio(Y_AXIS),1));assert(stepper.shaping_y.factor2==0);
 enter(INPUT_SHAPING_CASE_YZETA);edit(ENCODER_DIFF_CCW,100000);edit(ENCODER_DIFF_ENTER);
 assert(close(stepper.get_shaping_damping_ratio(Y_AXIS),0));assert(stepper.shaping_y.factor2==64);
 enter(INPUT_SHAPING_CASE_XFREQ);edit(ENCODER_DIFF_CW,100000);edit(ENCODER_DIFF_ENTER);assert(close(stepper.get_shaping_frequency(X_AXIS),999.99f));
 enter(INPUT_SHAPING_CASE_XFREQ);edit(ENCODER_DIFF_CCW,100000);edit(ENCODER_DIFF_ENTER);
 assert(stepper.get_shaping_frequency(X_AXIS)==0 && !stepper.shaping_x.enabled && ShapingQueue::delay_x==shaping_time_t(-1));
 enter(INPUT_SHAPING_CASE_XFREQ);edit(ENCODER_DIFF_CW);edit(ENCODER_DIFF_ENTER);
 constexpr float min_freq=float(uint32_t(STEPPER_TIMER_RATE)/2)/shaping_time_t(-2);
 assert(stepper.get_shaping_frequency(X_AXIS)>min_freq && stepper.shaping_x.enabled);
 enter(INPUT_SHAPING_CASE_XFREQ);edit(ENCODER_DIFF_CCW,1);edit(ENCODER_DIFF_ENTER);
 assert(stepper.get_shaping_frequency(X_AXIS)==0);
 // M593 and the LCD read and update the same production Stepper state.
 parser.values={{'Y',0},{'F',51.23f},{'D',0.24f}};GcodeSuite::M593();parser.values.clear();
 enter(INPUT_SHAPING_CASE_YFREQ);assert(HMI_ValueStruct.InputShaping_scaled==5123);edit(ENCODER_DIFF_ENTER);
 enter(INPUT_SHAPING_CASE_YZETA);assert(HMI_ValueStruct.InputShaping_scaled==24);edit(ENCODER_DIFF_ENTER);
 log_output.str("");GcodeSuite::M593();assert(log_output.str().find("51.23")!=std::string::npos && log_output.str().find("0.24")!=std::string::npos);
 save_shaping();assert(eeprom.size()==16);
 stepper.set_shaping_frequency(Y_AXIS,77);stepper.set_shaping_damping_ratio(Y_AXIS,0.9f);load_shaping();
 assert(close(stepper.get_shaping_frequency(Y_AXIS),51.23f) && close(stepper.get_shaping_damping_ratio(Y_AXIS),0.24f));
 hal.enabled=false;stepper.set_shaping_frequency(Y_AXIS,40);stepper.set_shaping_damping_ratio(Y_AXIS,0.15f);assert(!hal.enabled);hal.enabled=true;
 checkkey=InputShaping;select_input_shaping.now=0;
 for(int i=0;i<10;++i)menu(ENCODER_DIFF_CW);assert(select_input_shaping.now==INPUT_SHAPING_CASE_YZETA);
 for(int i=0;i<10;++i)menu(ENCODER_DIFF_CCW);menu(ENCODER_DIFF_ENTER);assert(checkkey==MotionMenu && select_motion.now==MOTION_CASE_INPUT_SHAPING);
 std::cout<<"PASS legacy LCD: live delay, enable/disable, damping factors, M593, EEPROM reload, bounds, navigation, synchronization/ISR state\n";
}
'''


def check_configuration():
    adv = (ROOT/'Marlin/Configuration_adv.h').read_text()
    start = adv.index('//#define INPUT_SHAPING_X')
    block = adv[start:adv.index('// @section motion', start)]
    post = (ROOT/'Marlin/src/inc/Conditionals-4-adv.h').read_text()
    start = post.index('// This DWIN menu edits the legacy X/Y')
    post = post[start:post.index('\n#endif', start)+len('\n#endif')]
    macros = '#include \"' + str(ROOT/'Marlin/src/core/macros.h') + '\"\n'
    with tempfile.TemporaryDirectory(prefix='shaping-config-') as tmp:
        tmp = Path(tmp)
        (tmp/'Marlin').mkdir()
        originals = {n:(ROOT/'Marlin'/n).read_bytes() for n in ('Configuration.h','Configuration_adv.h')}
        def apply(*args):
            subprocess.run([sys.executable,str(ROOT/'.github/scripts/apply_marlin_options.py'),*args],cwd=tmp,check=True,capture_output=True)
            return (tmp/'Marlin/Configuration_adv.h').read_text()
        def enabled(text, name):
            return bool(re.search(r'^\s*#define\s+'+name+r'\b',text,re.M))
        for ftm in (False,True):
            for menu in (False,True):
                for name,data in originals.items():
                    (tmp/'Marlin'/name).write_bytes(data)
                result = apply(f'FT_MOTION={str(ftm).lower()}',f'DWIN_INPUT_SHAPING_MENU={str(menu).lower()}')
                assert enabled(result,'FT_MOTION') == ftm
                assert enabled(result,'DWIN_INPUT_SHAPING_MENU') == (menu and not ftm)
                manual = block.replace('//#define DWIN_INPUT_SHAPING_MENU','#define DWIN_INPUT_SHAPING_MENU') if menu else block
                code = macros + ('#define FT_MOTION\n' if ftm else '') + manual + '\n' + post
                pp = subprocess.run(['g++','-E','-dM','-x','c++','-'],input=code,capture_output=True,text=True,check=True).stdout
                assert enabled(pp,'DWIN_INPUT_SHAPING_MENU') == (menu and not ftm)
                for axis in ('X','Y'):
                    assert enabled(pp,'INPUT_SHAPING_'+axis) == (menu and not ftm)
        # Partial overrides must also honor FT_MOTION already present in the file.
        for name,data in originals.items():
            (tmp/'Marlin'/name).write_bytes(data)
        apply('FT_MOTION=true')
        assert not enabled(apply('DWIN_INPUT_SHAPING_MENU=true'),'DWIN_INPUT_SHAPING_MENU')
        apply('FT_MOTION=false')
        assert enabled(apply('DWIN_INPUT_SHAPING_MENU=true'),'DWIN_INPUT_SHAPING_MENU')
        for value in ('0','false'):
            path = tmp/'Marlin/Configuration_adv.h'
            path.write_text(re.sub(r'^\s*(?://\s*)?#define FT_MOTION\b[^\n]*', '#define FT_MOTION '+value, path.read_text(), count=1, flags=re.M))
            assert enabled(apply('DWIN_INPUT_SHAPING_MENU=true'),'DWIN_INPUT_SHAPING_MENU')
        result = apply('FT_MOTION=true')
        assert not enabled(result,'DWIN_INPUT_SHAPING_MENU')
        assert not re.search(r'^\s*#define FT_MOTION\s+(?:0|false)\b',result,re.M)
    for ftm, x_axis, y_axis in ((False,False,False),(False,True,False),(False,False,True),(False,True,True),(True,True,True)):
        code = macros + '#define DWIN_INPUT_SHAPING_MENU\n'
        for name, active in (('FT_MOTION',ftm),('INPUT_SHAPING_X',x_axis),('INPUT_SHAPING_Y',y_axis)):
            if active:
                code += '#define '+name+'\n'
        pp = subprocess.run(['g++','-E','-dM','-x','c++','-'],input=code+post,capture_output=True,text=True,check=True).stdout
        assert enabled(pp,'DWIN_INPUT_SHAPING_MENU') == (not ftm and x_axis and y_axis)
    print('PASS manual and workflow feature matrix, legacy X/Y inclusion and partial overrides')


def main():
    check_configuration()
    dwin = (ROOT/'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
    stepper = (ROOT/'Marlin/src/module/stepper.cpp').read_text()
    header = (ROOT/'Marlin/src/module/stepper.h').read_text()
    constants = dwin[dwin.index('#if ENABLED(DWIN_INPUT_SHAPING_MENU)\n  #define INPUT_SHAPING_CASE_'):dwin.index('// #define LINEAR_ADV_KFACTOR')]
    params = function(header,'struct ShapeParams') + ';\n'
    queue = 'struct ShapingQueue {inline static shaping_time_t delay_x=0,delay_y=0;\n'+function(header,'static void set_delay(')+'};\n'
    cls = 'struct Stepper {inline static ShapeParams shaping_x{},shaping_y{};static void set_shaping_frequency(AxisEnum,float);static float get_shaping_frequency(AxisEnum);static void set_shaping_damping_ratio(AxisEnum,float);static float get_shaping_damping_ratio(AxisEnum); } stepper;\n'
    core = ''.join(function(stepper,p) for p in ('void Stepper::set_shaping_frequency(', 'float Stepper::get_shaping_frequency(', 'void Stepper::set_shaping_damping_ratio(', 'float Stepper::get_shaping_damping_ratio('))
    ui = 'template<typename T>\n'+function(dwin,'inline bool Apply_Encoder(')
    ui += ''.join(function(dwin,p) for p in ('static void Draw_InputShaping_Value(', 'void HMI_InputShaping_Values()', 'void Draw_InputShaping_Menu()', 'void HMI_InputShaping()'))
    m593 = (ROOT/'Marlin/src/gcode/feature/input_shaping/M593.cpp').read_text()
    commands = function(m593,'void GcodeSuite::M593_report(')+function(m593,'void GcodeSuite::M593()')
    settings = (ROOT/'Marlin/src/module/settings.cpp').read_text()
    first = settings.index('    // Input Shaping\n')
    save = settings[settings.index('    #if HAS_ZV_SHAPING',first):settings.index('    //\n    // HOTEND_IDLE_TIMEOUT',first)]
    second = settings.index('      // Input Shaping\n',first+1)
    load = settings[settings.index('      #if ENABLED(INPUT_SHAPING_X)',second):settings.index('      //\n      // HOTEND_IDLE_TIMEOUT',second)]
    persistence = 'void save_shaping(){\n'+save+'}\nvoid load_shaping(){bool validating=false;\n'+load+'}\n'
    source = STUBS+constants+params+queue+cls+core+ui+commands+persistence+TESTS
    with tempfile.TemporaryDirectory(prefix='dwin-input-shaping-') as folder:
        folder = Path(folder)
        for bits in (16,32):
            cpp,exe = folder/'test.cpp',folder/'test'
            cpp.write_text(source.replace('SHAPING_TIMER_TYPE',f'uint{bits}_t'))
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',str(cpp),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)


if __name__ == '__main__':
    main()
