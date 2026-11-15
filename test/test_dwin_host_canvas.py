#!/usr/bin/env python3
"""Exercise production full-screen admission, ownership and native UI preemption."""
from pathlib import Path
import os
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]
dwin = (ROOT/'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
io = (ROOT/'Marlin/src/e3v3se/LcdDrawIO.cpp').read_text()
prefix = r'''
#include <cassert>
#include "Marlin/src/core/macros.h"
#define M9001_DRAW_PROTOCOL 1
#define HAS_FILAMENT_SENSOR 1
#define RESONANCE_TEST 1
enum {MainMenu, M117Info, HostCanvas, ThumbPrint, SafetyDialog, Prepare};
enum {ENCODER_DIFF_NO, ENCODER_DIFF_ENTER, ENCODER_DIFF_CW};
constexpr int Color_Bg_Black=0;
int checkkey=MainMenu, event=ENCODER_DIFF_NO, clears=0, native_updates=0, main_visits=0;
bool OctoRefresh=true, drawing=false;
struct {bool Refresh_bottom_flag=false;} HMI_flag;
struct {bool running=true, paused=false, wait_for_user=false;
 bool isRunning(){return running;} bool printingIsPaused(){return paused;}} marlin;
struct {bool queued=false;bool has_blocks_queued(){return queued;}} planner;
struct {bool active=false;bool isActive(){return active;}} rtg;
namespace HostPrint {int status_clears=0;void clear_status(){++status_clears;}}
namespace LcdDraw {bool active(){return drawing;}}
namespace LcdDrawIO {void end_fullscreen();}
void DWIN_Draw_Rectangle(int fill,int color,int x0,int y0,int x1,int y1){
 assert(fill==1 && color==0 && x0==0 && y0==0 && x1==239 && y1==319);++clears;
}
void DWIN_UpdateLCD(){}
void Goto_MainMenu(){++main_visits;checkkey=MainMenu;drawing=false;}
int get_encoder_state(){int old=event;event=ENCODER_DIFF_NO;if(old) drawing=false;return old;}
void EachMomentUpdate(){++native_updates;}
void HMI_HostCanvas();
void DWIN_HandleScreen(){if(checkkey==HostCanvas)HMI_HostCanvas();}
'''
code = prefix
for name in ('DWIN_HostCanvas', 'HMI_HostCanvas', 'DWIN_Update'):
    code += '\n' + function(dwin, 'void '+name+'(')
code += '\nnamespace LcdDrawIO {\n'
for name in ('bool allowed(', 'bool begin_fullscreen(', 'void end_fullscreen('):
    code += function(io, name)+'\n'
code += r'''}
int main(){
 // No print-card entry, progress resets, or print controls are called.
 assert(LcdDrawIO::begin_fullscreen());
 assert(checkkey==HostCanvas && clears==1 && !OctoRefresh && HMI_flag.Refresh_bottom_flag);
 assert(LcdDrawIO::allowed(true) && !LcdDrawIO::allowed(false));
 assert(LcdDrawIO::begin_fullscreen() && clears==2); // Each new screen clears every pixel.
 for(bool active:{true,false}){drawing=active;DWIN_Update();assert(native_updates==0);}
 // A completed image is retained while the planner runs homing/excitation.
 drawing=false;planner.queued=true;DWIN_Update();assert(native_updates==0 && checkkey==HostCanvas);
 assert(!LcdDrawIO::allowed(true));planner.queued=false;
 // Rotate aborts a transfer, but does not launch a menu or printer action.
 drawing=true;event=ENCODER_DIFF_CW;DWIN_Update();assert(!drawing && checkkey==HostCanvas);
 event=ENCODER_DIFF_ENTER;DWIN_Update();assert(main_visits==1 && clears==3 && checkkey==MainMenu);
 for(int context:{ThumbPrint,SafetyDialog,Prepare}){
   checkkey=context;assert(!LcdDrawIO::begin_fullscreen());assert(checkkey==context);
 }
 checkkey=MainMenu;
 marlin.running=false;assert(!LcdDrawIO::begin_fullscreen());marlin.running=true;
 marlin.paused=true;assert(!LcdDrawIO::begin_fullscreen());marlin.paused=false;
 marlin.wait_for_user=true;assert(!LcdDrawIO::begin_fullscreen());marlin.wait_for_user=false;
 planner.queued=true;assert(!LcdDrawIO::begin_fullscreen());planner.queued=false;
 rtg.active=true;assert(!LcdDrawIO::begin_fullscreen());rtg.active=false;
 checkkey=M117Info;assert(LcdDrawIO::begin_fullscreen());
 // A native safety transition takes priority. A late release cannot erase it.
 checkkey=SafetyDialog;drawing=false;assert(!LcdDrawIO::allowed(true));
 int before=clears;LcdDrawIO::end_fullscreen();assert(clears==before && checkkey==SafetyDialog);
 DWIN_Update();assert(native_updates==1);
 checkkey=ThumbPrint;assert(LcdDrawIO::allowed(false));
}
'''
code = code.replace('#include <cassert>', '#include <cassert>\n#include <initializer_list>')
with tempfile.TemporaryDirectory(prefix='c13-canvas-ui-') as folder:
    source, binary = Path(folder)/'canvas.cpp', Path(folder)/'canvas'
    source.write_text(code)
    subprocess.run(['clang++', '-std=c++17', '-g', '-O1', '-fsanitize=address,undefined',
                    '-I', str(ROOT), str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0',
                                                      UBSAN_OPTIONS='halt_on_error=1'))
print('PASS full-screen clear, exclusive canvas, stationary admission, retention after DONE, encoder exit and safety preemption')
