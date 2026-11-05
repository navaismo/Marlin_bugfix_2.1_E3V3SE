#!/usr/bin/env python3
"""Run the original overflow input and its solid-color control under ASan.

Both inputs must now succeed. --expect-overflow and --source can verify the
historical defect against a saved pre-fix ThumbRender.cpp without any motors.
"""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
MOCK = r'''
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#define DWIN_CREALITY_LCD 1
#define DWIN_RENDER_THUMBNAIL 1
#define ALL(A,B) ((A)&&(B))
struct Card {
  std::string contents;
  size_t pos=0;
  bool opened=false;
  void openFileRead(const char*) {pos=0;opened=true;}
  bool isFileOpen() {return opened;}
  bool eof() {return pos>=contents.size();}
  int16_t get() {return eof()?-1:contents[pos++];}
  void setIndex(size_t p) {pos=p;}
  void closefile() {opened=false;}
};
extern Card card;
struct HAL {void watchdog_refresh() {}};
extern HAL hal;
inline void delay(int) {}
inline void DWIN_Set_Color(uint16_t,uint16_t) {}
inline void DWIN_Fill_Rect_Raw(uint16_t,uint16_t,uint16_t,uint16_t) {}
'''
MAIN = r'''
#include "mock.h"
Card card;
HAL hal;
bool DWIN_RenderThumb(const char*);
int main(int argc,char**) {
  card.contents="; E3V3SE_THUMB_RAW16_BEGIN 96x17\n";
  for (int y=0;y<17;++y) {
    card.contents+="; ";
    for (int x=0;x<96;++x) {
      // Alternating nonzero colors produce 96 runs per row, not 48.
      // Before the last row, 1480 slots are used and 56 remain.
      const unsigned color=argc>1?((y==15 && x>=40)?0:1+(x+y)%2):1;
      char pixel[5];std::snprintf(pixel,sizeof(pixel),"%04X",color);
      card.contents+=pixel;
    }
    card.contents+='\n';
  }
  card.contents+="; E3V3SE_THUMB_RAW16_END\n";
  return DWIN_RenderThumb("mock.gcode")?0:2;
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--source",type=Path,default=ROOT/"Marlin/src/e3v3se/ThumbRender.cpp")
    parser.add_argument("--expect-overflow",action="store_true")
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="marlin-thumb-audit-") as tmp:
        tmp=Path(tmp)
        dest=tmp/"e3v3se/ThumbRender.cpp"
        dest.parent.mkdir()
        shutil.copyfile(args.source,dest)
        (tmp/"mock.h").write_text(MOCK)
        (tmp/"main.cpp").write_text(MAIN)
        for name in ["inc/MarlinConfigPre.h","inc/MarlinConfig.h",
                     "lcd/dwin/creality/dwin_lcd.h","sd/cardreader.h","HAL/shared/Delay.h"]:
            p=tmp/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text('#pragma once\n#include "mock.h"\n')
        subprocess.run([os.environ.get("CXX") or shutil.which("clang++") or "g++","-std=c++11","-O1","-g","-fsanitize=address",
                        "-fno-omit-frame-pointer","-I",str(tmp),str(dest),
                        str(tmp/"main.cpp"),"-o",str(tmp/"test")],check=True)
        env=dict(os.environ,ASAN_OPTIONS="detect_leaks=0:halt_on_error=1")
        control=subprocess.run([str(tmp/"test")],env=env,capture_output=True,text=True)
        if control.returncode:
            raise RuntimeError("Solid-color control failed:\n"+control.stderr)
        result=subprocess.run([str(tmp/"test"),"alternating"],env=env,capture_output=True,text=True)
        if args.expect_overflow:
            if result.returncode==0 or "global-buffer-overflow" not in result.stderr or "thumb_runs" not in result.stderr:
                raise RuntimeError("Expected historical overflow was not reproduced:\n"+result.stderr)
            outcome="historical global-buffer-overflow reproduced in thumb_runs"
        else:
            if result.returncode:
                raise RuntimeError("Thumbnail overflow regression failed:\n"+result.stderr)
            outcome="alternating-color overflow regression: PASS (no ASan errors)"
        report="Solid-color control: PASS\n"+outcome+"\n"+result.stderr
        if args.output:args.output.write_text(report)
        print("Solid-color control: PASS; "+outcome+".")


if __name__=="__main__":
    main()
