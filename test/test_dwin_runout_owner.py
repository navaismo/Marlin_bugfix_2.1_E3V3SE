#!/usr/bin/env python3
"""The production DWIN update must not overwrite core M600 or bypass M412."""
from pathlib import Path
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]
STUBS = r'''
#include <cassert>
#include <string>
#include "Marlin/src/core/macros.h"
#define POWER_LOSS_RECOVERY 0
#define HAS_MEDIA 1
#define SDSUPPORT 1
struct {bool disallow_recovery_flag=false,cloud_printing_flag=false;} HMI_flag;
struct {bool printing=true;bool isPrinting(){return printing;}} card;
struct {bool enabled=true,host_handling=false;} runout;
std::string pending;
int legacy_calls=0;
void HMI_SDCardUpdate() {}
void Remove_card_window_check() {}
void EachMomentUpdate() {}
void DWIN_HandleScreen() {}
void Check_Filament_Update() {++legacy_calls;pending="M25";}
'''
MAIN = r'''
int main() {
 for(bool enabled : {false,true}) for(bool host : {false,true}) {
   runout.enabled=enabled;runout.host_handling=host;
   pending=enabled && !host ? "M600" : "";
   const auto expected=pending;
   DWIN_Update();
   #if HAS_FILAMENT_SENSOR
     assert(pending==expected && legacy_calls==0);
   #else
     assert(pending=="M25");
   #endif
 }
}
'''
if __name__=='__main__':
    source=function((ROOT/'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text(),'void DWIN_Update()')
    with tempfile.TemporaryDirectory() as folder:
        src,exe=Path(folder)/'test.cpp',Path(folder)/'test'
        src.write_text(STUBS+source+MAIN)
        for core in (0,1):
            subprocess.run(['g++','-std=c++17','-I',str(ROOT),f'-DHAS_FILAMENT_SENSOR={core}',
                            str(src),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
    print('PASS DWIN defers to core runout, preserves M600/M412 choices and retains legacy fallback')
