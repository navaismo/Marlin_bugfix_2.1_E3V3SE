#!/usr/bin/env python3
"""Replay the production DWIN manual-move handlers with a busy motion planner."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Marlin/src/lcd/dwin/creality/dwin.cpp"

STUBS = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#define ENABLED(V) (V)
#define HAS_HOTEND 1
#define F(S) S
#define LIMIT(V,L,H) do { if((V)<(L)) (V)=(L); if((V)>(H)) (V)=(H); } while(0)
#define PENDING(N,T) (int32_t((N)-(T))<0)
#define MBASE(L) (34+36*(L))
constexpr int ENCODER_WAIT_MS=20,MINUNITMULT=10,UNITFDIGITS=1,VALUERANGE_X=172,
              EXTRUDE_MAXLENGTH_e=1000,FEEDRATE_E=60;
constexpr int font8x16=8,Color_Bg_Black=0,Select_Color=1,MROWS=5;
enum AxisEnum { X_AXIS,Y_AXIS,Z_AXIS,E_AXIS };
enum { Prepare,AxisMove,Move_X,Move_Y,Move_Z,Extruder,Max_GUI };
enum ENCODER_DiffState { ENCODER_DIFF_NO,ENCODER_DIFF_CW,ENCODER_DIFF_CCW,ENCODER_DIFF_ENTER };
using millis_t=uint32_t;
using feedRate_t=float;
#define MMM_TO_MMS(V) ((V)/60.0f)
millis_t clock_now=100;
millis_t millis() { return clock_now; }
int checkkey=AxisMove,index_prepare=0,prepare_redraws=0,popup_count=0,move_redraws=0,lcd_updates=0,last_row=-1,last_color=-1;
struct { bool enabled=false; int encoderMoveValue=1; } EncoderRate;
struct {
 float Move_X_scaled=0,Move_Y_scaled=0,Move_Z_scaled=0,Move_E_scaled=0;
} HMI_ValueStruct;
struct { bool ETempTooLow_flag=false; } HMI_flag;
struct Selection {
 int now=0;
 void set(int n) { now=n; }
 bool inc(int total) { if(now+1>=total) return false; ++now; return true; }
 bool dec() { if(!now) return false; --now; return true; }
} select_axis,select_prepare;
struct { struct { float x=0,y=0,z=0,e=0; } position; } motion;
struct {
 bool pending=false;
 int sync_calls=0,buffer_calls=0;
 std::function<void()> on_idle;
 void synchronize() { ++sync_calls; if(on_idle) on_idle(); pending=false; }
} planner;
std::deque<ENCODER_DiffState> events;
ENCODER_DiffState Encoder_ReceiveAnalyze() {
 if(events.empty()) return ENCODER_DIFF_NO;
 const auto next=events.front(); events.pop_front(); return next;
}
void input(ENCODER_DiffState state) { clock_now+=50; events.push_back(state); }
void delay(int ms) { clock_now+=ms; }
void HMI_Plan_Move(feedRate_t) { ++planner.buffer_calls; planner.pending=true; }
void DWIN_Draw_Signed_Float(int,int color,int,int,int,int y,float) { last_row=(y-34)/36;last_color=color; }
void DWIN_UpdateLCD() { ++lcd_updates; }
void Draw_Move_Menu() { ++move_redraws; }
void Draw_Prepare_Menu() { ++prepare_redraws; }
void Move_Highlight(int,int row) { assert(row>=0 && row<=6); }
void Popup_Window_ETempTooLow() { ++popup_count; }
void Clear_Title_Bar() {}
void Draw_Title(const char*) {}
struct { bool cold=false; bool tooColdToExtrude(int) { return cold; } } thermalManager;
struct { void process_subcommands_now(const char*) { assert(false && "unexpected G-code"); } } gcode;
struct { bool deploy() { assert(false); return false; } bool stow() { assert(false); return false; } } probe;
void dispatch() {
 if(checkkey==AxisMove) HMI_AxisMove();
 else if(checkkey==Extruder) HMI_Move_E();
}
'''

TESTS = r'''
int main() {
 // Reproduce: enter Extrude, turn the knob, accept with an extrusion pending.
 select_axis.set(4); motion.position.e=12.5f;
 input(ENCODER_DIFF_ENTER); dispatch();
 assert(checkkey==Extruder && EncoderRate.enabled);
 input(ENCODER_DIFF_CW); dispatch();
 assert(planner.pending && planner.buffer_calls==1);
 const float accepted=HMI_ValueStruct.Move_E_scaled,target=motion.position.e;
 bool reentered=false;
 planner.on_idle=[&] {
  // synchronize() services Marlin's idle loop, which dispatches the LCD again.
  reentered=checkkey==Extruder;
  input(ENCODER_DIFF_CCW); dispatch();
 };
 input(ENCODER_DIFF_ENTER); dispatch();
 assert(!reentered && "accepting a pending extrusion reentered its editor");
 assert(checkkey==AxisMove && !EncoderRate.enabled);
 assert(planner.pending && planner.sync_calls==0 && planner.buffer_calls==1);
 assert(HMI_ValueStruct.Move_E_scaled==accepted && motion.position.e==target);
 assert(last_row==4 && last_color==Color_Bg_Black);
 planner.on_idle={};
 // While extrusion continues, turning the knob must navigate without editing
 // E or scheduling more extrusion. The next click explicitly selects Z.
 input(ENCODER_DIFF_CCW); dispatch();
 assert(checkkey==AxisMove && select_axis.now==3 && planner.pending);
 assert(HMI_ValueStruct.Move_E_scaled==accepted && planner.buffer_calls==1);
 input(ENCODER_DIFF_ENTER); dispatch();
 assert(checkkey==Move_Z && EncoderRate.enabled);
 HMI_Move_Done(Z_AXIS);
 assert(checkkey==AxisMove && !EncoderRate.enabled);
 for(int n=0;n<3;++n) { input(ENCODER_DIFF_CCW); dispatch(); }
 input(ENCODER_DIFF_ENTER); dispatch();
 assert(checkkey==Prepare && prepare_redraws==1 && select_prepare.now==1 && index_prepare==MROWS);
 // The shared completion path must also leave X/Y/Z/E with normal encoder
 // speed and no blocking planner wait, including a negative extruder position.
 for(int axis=0;axis<4;++axis) {
  checkkey=axis==0 ? Move_X:axis==1 ? Move_Y:axis==2 ? Move_Z:Extruder;
  EncoderRate.enabled=true; planner.pending=true;
  HMI_ValueStruct.Move_E_scaled=-50;
  HMI_Move_Done(AxisEnum(axis));
  assert(checkkey==AxisMove && !EncoderRate.enabled && planner.pending);
  assert(last_row==axis+1 && last_color==Color_Bg_Black);
 }
 // Repeated normal edit/accept/navigation cycles never require a restart.
 for(int n=0;n<20;++n) {
  select_axis.set(4); input(ENCODER_DIFF_ENTER); dispatch();
  assert(checkkey==Extruder);
  input(ENCODER_DIFF_ENTER); dispatch();
  assert(checkkey==AxisMove && !EncoderRate.enabled);
  input(ENCODER_DIFF_CCW); dispatch();
  assert(checkkey==AxisMove && select_axis.now==3);
 }
 #if ENABLED(PREVENT_COLD_EXTRUSION)
  thermalManager.cold=true; select_axis.set(4);
  input(ENCODER_DIFF_ENTER); dispatch();
  assert(checkkey==AxisMove && HMI_flag.ETempTooLow_flag && popup_count==1);
  input(ENCODER_DIFF_CCW); dispatch(); assert(select_axis.now==4);
  input(ENCODER_DIFF_ENTER); dispatch();
  assert(checkkey==AxisMove && !HMI_flag.ETempTooLow_flag && move_redraws==1);
 #endif
 assert(planner.sync_calls==0);
 std::cout<<"PASS manual move confirmation, busy planner, navigation, repeat edits, cold protection\n";
}
'''


def function(text, start):
    begin = text.index(start)
    end = text.index("\n}\n", begin) + len("\n}\n")
    return text[begin:end]


def main():
    text = SOURCE.read_text()
    functions = "\n".join(function(text, prefix) for prefix in (
        "template <typename T>\ninline bool Apply_Encoder(",
        "inline ENCODER_DiffState get_encoder_state()",
        "void HMI_Move_Done(", "void HMI_Move_E()", "void HMI_AxisMove()",
    ))
    stubs = STUBS.replace("void dispatch() {", "void HMI_Move_E();\nvoid HMI_AxisMove();\nvoid dispatch() {")
    with tempfile.TemporaryDirectory(prefix="dwin-move-exit-") as folder:
        cpp, binary = Path(folder)/"test.cpp", Path(folder)/"test"
        cpp.write_text(stubs + functions + TESTS)
        for cold_protection in (False, True):
            subprocess.run(["g++", "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
                            *(["-DPREVENT_COLD_EXTRUSION=1"] if cold_protection else []),
                            str(cpp), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
