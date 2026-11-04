#!/usr/bin/env python3
"""Execute the production M125 route: LCD purge stays automatic and configurable."""
from pathlib import Path
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]
STUBS = r'''
#include <cassert>
#include "Marlin/src/core/macros.h"
#define HAS_EXTRUDERS 1
#define HAS_Z_AXIS 1
#define HAS_DISPLAY 1
#define PAUSE_PARK_RETRACT_LENGTH 2
#define ADVANCED_PAUSE_PURGE_LENGTH 50
#define NOZZLE_PARK_POINT {10,20,30}
#define NUM_AXIS_CODE(...)
#define DXC_PASS
#define E_AXIS 3
enum { PAUSE_MESSAGE_PARKING, PAUSE_MODE_PAUSE_PRINT };
struct xyz_pos_t { float x,y,z; };
struct {
 float retract=2;
 float axisunitsval(char,int,float) { return retract; }
 bool seenval(char) { return false; }
 float linearval(char) { return 0; }
 bool boolval(char) { return false; }
} parser;
struct { bool printing=true; bool isStillPrinting() { return printing; } } card;
struct { void pause_show_message(int,int) {} } ui;
bool paused=false,confirmed=false,resumed=false,allow_pause=true;
float purge=0;
bool pause_print(float retract,const xyz_pos_t &,bool lcd,float unload) {
 assert(retract==-parser.retract && !lcd && unload==0);
 paused=true;return allow_pause;
}
void wait_for_confirmation(bool reload,int beeps) { assert(!reload && beeps==0);confirmed=true; }
void resume_print(float slow,float fast,float length,int beeps) {
 assert(confirmed && slow==0 && fast==0 && beeps==0);resumed=true;purge=length;
}
struct GcodeSuite { static void M125(); };
'''
MAIN = r'''
int main() {
 for(bool sd : {false,true}) {
  for(float retract : {2.f,7.f}) {
   parser.retract=retract;card.printing=sd;
   paused=confirmed=resumed=false;
   GcodeSuite::M125();assert(paused && confirmed && resumed);
   assert(purge==(DWIN_CREALITY_LCD ? ADVANCED_PAUSE_PURGE_LENGTH : retract));
  }
 }
 allow_pause=false;paused=confirmed=resumed=false;
 GcodeSuite::M125();assert(paused && !confirmed && !resumed);
}
'''

if __name__ == '__main__':
    source = function((ROOT/'Marlin/src/gcode/feature/pause/M125.cpp').read_text(), 'void GcodeSuite::M125(')
    with tempfile.TemporaryDirectory() as folder:
        src, exe = Path(folder)/'pause.cpp', Path(folder)/'pause'
        src.write_text('#include <initializer_list>\n'+STUBS+source+MAIN)
        for lcd in (0, 1):
            subprocess.run(['g++','-std=c++17','-I',str(ROOT),f'-DDWIN_CREALITY_LCD={lcd}',str(src),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
    print('PASS M125 automatic configured LCD purge, SD/host, retract overrides and rejected duplicate pause')
