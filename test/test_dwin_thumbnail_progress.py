#!/usr/bin/env python3
"""Replay production thumbnail redraw calls with a partially completed print."""
from pathlib import Path
import re
import subprocess
import tempfile
from test_dwin_input_shaping import function

ROOT = Path(__file__).resolve().parents[1]
STUBS = r'''
#include <cassert>
#include <vector>
#include "Marlin/src/core/macros.h"
#define DWIN_RENDER_THUMBNAIL 1
#define DWIN_CREALITY_320_LCD 1
#define F(V) V
#define DWIN_Draw_String(...)
#define SERIAL_ECHOLN(...)
enum { ThumbPrint };
bool OctoRefresh=false,hasThumbnail=true,isPaused=false;
char title[]="Test print";
int checkkey=-1;
struct { bool Refresh_bottom_flag=true; } HMI_flag;
struct {
 int progress=0,layer=17,total=40,remaining=600,elapsed=300,resets=0;
 void progress_reset() { progress=0;++resets; }
 int get_current_layer() { return layer; }
} ui;
struct Rectangle { int x1,y1,x2,y2; };
std::vector<Rectangle> cleared;
void DWIN_Draw_Rectangle(int,int,int x1,int y1,int x2,int y2) { cleared.push_back({x1,y1,x2,y2}); }
constexpr int Color_Bg_Black=0;
void Clear_Title_Bar() {}
void Draw_OctoTitle(const char*) {}
void Draw_Mid_Status_Area(bool) {}
void Draw_Print_ProgressBar() {}
void Draw_Print_Time() {}
void Draw_Print_ProgressElapsed() {}
void Draw_Print_ProgressRemain() {}
void Draw_Layer_Number(bool) {}
void ICON_Tune() {}
void ICON_Continue() {}
void ICON_Pause() {}
void ICON_Stop() {}
void reset() { ui.progress=6734;ui.resets=0;cleared.clear(); }
void preserved() {
 assert(ui.progress==6734 && ui.resets==0);
 assert(ui.layer==17 && ui.total==40 && ui.remaining==600 && ui.elapsed==300);
 assert(hasThumbnail && checkkey==ThumbPrint);
 for (const auto &r : cleared) assert(r.y1>=123); // Upper thumbnail is untouched.
}
'''


def main():
    dwin = (ROOT/'Marlin/src/lcd/dwin/creality/dwin.cpp').read_text()
    header = (ROOT/'Marlin/src/lcd/dwin/creality/dwin.h').read_text()
    prototype = re.search(r'void Goto_ThumbPrint\([^;]+;', header)[0]
    renderer = function(dwin, 'void Goto_ThumbPrint(')
    clear = function(dwin, 'void Clear_Below_Area(')
    navigation = '\n'.join(function(dwin, name) for name in (
        'void HMI_Printing(', 'void HMI_PauseOrStop(', 'void HMI_ThumbPrint(',
        'void HMI_ThumbTune(', 'void MarlinUI::pause_show_message('))
    starts = function(dwin, 'void Show_G_Pic(')
    host_source = ROOT/'Marlin/src/e3v3se/OctoHost.cpp'
    if host_source.exists():
        starts += '\n' + function(host_source.read_text(), 'void GcodeSuite::M9000(')
    with tempfile.TemporaryDirectory() as folder:
        source, binary = Path(folder)/'progress.cpp', Path(folder)/'progress'
        for host in (0, 1):
            # Extract the call arguments from the actual compiled navigation branches.
            prefix = STUBS + f'\n#define OCTOPRINT_PLUGIN {host}\n'
            preprocessed = subprocess.run(['g++','-E','-P','-x','c++','-I',str(ROOT),'-'],
                input=prefix+navigation, text=True, capture_output=True, check=True).stdout
            calls = re.findall(r'Goto_ThumbPrint\(([^)]*)\)', preprocessed)
            assert calls, 'No navigation calls covered'
            checks = '\n'.join('reset(); Goto_ThumbPrint('+args+'); preserved();' for args in calls)
            new_calls = re.findall(r'Goto_ThumbPrint\(([^)]*)\)', starts)
            assert new_calls, 'No new-print entry covered'
            new_checks = '\n'.join('reset(); Goto_ThumbPrint('+args+'); assert(ui.progress==0 && ui.resets==1);' for args in new_calls)
            source.write_text(prefix+prototype+'\n'+clear+'\n'+renderer+'\nint main() {\n'+checks+'\n'+new_checks+'\n}')
            subprocess.run(['g++','-std=c++17','-I',str(ROOT),str(source),'-o',str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
    print('PASS thumbnail progress/metadata/image across pause, resume, cancel and Tune redraws; new prints reset')


if __name__ == '__main__':
    main()
