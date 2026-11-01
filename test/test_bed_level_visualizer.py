#!/usr/bin/env python3
"""Exercise the actual LCD renderer on a host, without a printer.

Run: python3 test/test_bed_level_visualizer.py
Optional LCD command previews: --preview-dir /tmp/bed-level-preview
Only the LCD transport and bed mesh are replaced; geometry and rendering are production code.
"""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
LCD = ROOT / "Marlin/src/lcd/dwin/creality"

STUBS = r'''
#include <cassert>
#include <algorithm>
#include <cstring>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cctype>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include "bed_level_surface.h"
#include "bed_level_assessment.h"
#define PROGMEM
#define pgm_read_byte(P) (*(P))
#include "bed_level_help_qr.h"
int firmware_snprintf(char *text,size_t capacity,const char *format,...) {
 // A host's printf supports floats even when the embedded nano printf does not.
 // Reject them here so a successful host test cannot hide blank LCD values.
 for(const char *p=format;*p;++p) if(*p=='%') {
  ++p; while(*p && (!std::isalpha(*p) || *p=='l' || *p=='h')) ++p;
  assert(*p && !strchr("fFeEgGaA",*p));
 }
 va_list arguments; va_start(arguments,format);
 const int result=vsnprintf(text,capacity,format,arguments);
 va_end(arguments); return result;
}
#define snprintf firmware_snprintf
#define ENABLED(V) (V)
#ifndef BED_LEVEL_VISUALIZER
 #define BED_LEVEL_VISUALIZER 1
#endif
#define _MIN(A,B) ((A)<(B)?(A):(B))
#define _MAX(A,B) ((A)>(B)?(A):(B))
#define F(S) S
#define PENDING(N,T) (int32_t((N)-(T))<0)
using millis_t=uint32_t;
millis_t clock_now=0;
millis_t millis() { return clock_now; }
using __FlashStringHelper = char;
constexpr int DWIN_WIDTH=240, DWIN_HEIGHT=320;
constexpr int Color_White=0xffff, Color_Bg_Black=0, Color_Bg_Blue=0x001f, Color_Yellow=0xfe29;
constexpr int font6x12=6, font8x16=8;
struct { bool valid=true; float z_values[GRID_MAX_POINTS_X][GRID_MAX_POINTS_Y];
         bool mesh_is_valid() { return valid; } } bedlevel;
struct Op {
 char kind; int x0,y0,x1,y1,color; std::string text;
 bool operator==(const Op &b) const {
  return kind==b.kind && x0==b.x0 && y0==b.y0 && x1==b.x1 && y1==b.y1 && color==b.color && text==b.text;
 }
};
std::vector<Op> ops;
std::vector<millis_t> draw_times;
void point(int x,int y) { assert(x>=0 && x<DWIN_WIDTH && y>=0 && y<DWIN_HEIGHT); }
void DWIN_Draw_Rectangle(int mode,int color,int x0,int y0,int x1,int y1) {
 assert(mode==1 && x0<=x1 && y0<=y1); point(x0,y0); point(x1,y1);
 ops.push_back({'R',x0,y0,x1,y1,color,{}});
 draw_times.push_back(clock_now);
}
void DWIN_Draw_Line(int color,int x0,int y0,int x1,int y1) {
 point(x0,y0); point(x1,y1); ops.push_back({'L',x0,y0,x1,y1,color,{}});
 draw_times.push_back(clock_now);
}
void DWIN_Draw_String(bool,bool,int font,int color,int,int x,int y,const char *text) {
 point(x,y); assert(x+int(strlen(text))*font<=DWIN_WIDTH);
 ops.push_back({'T',x,y,font,0,color,text});
 draw_times.push_back(clock_now);
}
void DWIN_UpdateLCD() {}
enum { Level, Leveling, BedLevelView, MROWS=5 };
int checkkey=Level, level_redraws=0, highlighted_row=0;
bool back_selected=true;
struct {
 bool Refresh_bottom_flag=false,leveling_offset_flag=false,Pressure_Height_end=false,
      G29_finish_flag=false,Edit_Only_flag=false;
 int language=0;
} HMI_flag;
struct Selection {
 int now=0;
 void set(int n) { now=n; }
 void reset() { now=0; }
 bool inc(int count) { if(now+1>=count) return false; ++now; return true; }
 bool dec() { if(!now) return false; --now; return true; }
} select_cextr,select_page;
enum { ENCODER_DIFF_NO, ENCODER_DIFF_ENTER, ENCODER_DIFF_CW, ENCODER_DIFF_CCW };
using ENCODER_DiffState=int;
int event=ENCODER_DIFF_NO;
int get_encoder_state() { return event; }
#define DWIN_CREALITY_320_LCD 1
#define DWIN_CREALITY_480_LCD 0
#define MBASE(L) (34+36*(L))
constexpr int LBLX=42,ICON_SetHome=1,ICON_Edit_Level_Data=2,LANGUAGE_EDIT_LEVEL_DATA=3,JPN_OFFSET=-5;
void Draw_Menu_Line(uint8_t row,int) { assert(row<=MROWS); }
void Draw_More_Icon(uint8_t row) { assert(row<=MROWS); }
void DWIN_Draw_Label(uint16_t y,const char *text) {
 DWIN_Draw_String(false,true,font8x16,Color_White,Color_Bg_Black,LBLX,y,text);
}
void Clear_Main_Window() {
 ++level_redraws;
 DWIN_Draw_Rectangle(1,Color_Bg_Black,0,25,DWIN_WIDTH-1,239);
}
void Draw_Mid_Status_Area(bool) {}
void Draw_Back_First(bool selected) { back_selected=selected; highlighted_row=0; }
void Draw_Title(const char *text) { DWIN_Draw_String(false,false,font8x16,Color_White,0,12,4,text); }
void DWIN_ICON_Show(int,int,int,int) {}
void Draw_Menu_Cursor(int row) { assert(row>0 && row<=MROWS); highlighted_row=row; }
void Move_Highlight(int,int row) { highlighted_row=row; }
// Opening the read-only map must never execute any calibration operation.
void Goto_MainMenu() { assert(false); }
void Popup_Window_Home() { assert(false); }
void Popup_Window_Leveling() { assert(false); }
void Refresh_Leveling_Value() { assert(false); }
struct { void process_subcommands_now(const char*) { assert(false); } } gcode;
#define RUN_AND_WAIT_GCODE_CMD(...) assert(false)
'''

TESTS = r'''
void complete() {
 for(int tick=0; tick<30000 && BedLevelVisualizer::busy(); ++tick) {
  const auto before=ops.size(); BedLevelVisualizer::update();
  assert(ops.size()-before<=1); // Header, QR, legend and surface share the same pacing.
  const auto after=ops.size();
  BedLevelVisualizer::update(); assert(ops.size()==after);
  clock_now+=BED_LEVEL_VISUALIZER_DRAW_DELAY_MS-1;
  BedLevelVisualizer::update(); assert(ops.size()==after);
  ++clock_now;
 }
 assert(!BedLevelVisualizer::busy() && "renderer did not finish within its work budget");
 for(size_t i=1;i<draw_times.size();++i)
  assert(millis_t(draw_times[i]-draw_times[i-1])>=BED_LEVEL_VISUALIZER_DRAW_DELAY_MS);
}
void shape(int kind) {
 bedlevel.valid=true;
 for(int x=0;x<GRID_MAX_POINTS_X;++x) for(int y=0;y<GRID_MAX_POINTS_Y;++y) {
  const float u=float(x)/(GRID_MAX_POINTS_X-1)*2-1, v=float(y)/(GRID_MAX_POINTS_Y-1)*2-1;
  bedlevel.z_values[x][y]=kind==0 ? 0 : kind==1 ? (u+v)*0.2f : kind==2 ? (1-u*u-v*v)*0.3f : u*v*0.4f;
 }
 ops.clear(); draw_times.clear();
}
void dump(const std::string &path) {
 if(path.empty()) return;
 std::ofstream file(path);
 for(const auto &op:ops)
  file<<op.kind<<' '<<op.x0<<' '<<op.y0<<' '<<op.x1<<' '<<op.y1<<' '<<op.color<<' '<<op.text<<'\n';
}
bool has_text(const char *needle) {
 for(const auto &op:ops) if(op.text.find(needle)!=std::string::npos) return true;
 return false;
}
void check_surface_coverage() {
 using namespace BedLevelSurface;
 // Replay the LCD rectangles under both far-corner conventions. Every pixel
 // inside the projected mesh must have a fill, even on an exclusive-end panel.
 for(int exclusive : {0,1}) {
  bool pixels[DWIN_WIDTH][DWIN_HEIGHT]={};
  for(const auto &op:ops) if(op.kind=='R')
   for(int x=op.x0;x<=op.x1-exclusive;++x)
    for(int y=op.y0;y<=op.y1-exclusive;++y) pixels[x][y]=op.color!=Color_Bg_Black;
  auto inside=[](const Point &a,const Point &b,const Point &c,float x,float y) {
   auto cross=[=](const Point &p,const Point &q) { return (q.x-p.x)*(y-p.y)-(q.y-p.y)*(x-p.x); };
   const float ca=cross(a,b),cb=cross(b,c),cc=cross(c,a);
   return (ca>0.001f && cb>0.001f && cc>0.001f) || (ca<-0.001f && cb<-0.001f && cc<-0.001f);
  };
  const auto &bounds=BedLevelVisualizer::plot;
  for(int cx=0;cx<GRID_MAX_POINTS_X-1;++cx) for(int cy=0;cy<GRID_MAX_POINTS_Y-1;++cy) {
   Point p[4]; const int dx[]={0,1,1,0},dy[]={0,0,1,1};
   for(int n=0;n<4;++n) p[n]=project(float(cx+dx[n])/(GRID_MAX_POINTS_X-1),float(cy+dy[n])/(GRID_MAX_POINTS_Y-1),
    bedlevel.z_values[cx+dx[n]][cy+dy[n]],BedLevelVisualizer::center_z,BedLevelVisualizer::z_scale,bounds);
   for(int x=bounds.left;x<bounds.right;++x) for(int y=bounds.top;y<bounds.bottom;++y)
    if(inside(p[0],p[1],p[2],x+0.5f,y+0.5f) || inside(p[0],p[2],p[3],x+0.5f,y+0.5f))
     assert(pixels[x][y] && "unfilled pixel inside the heatmap");
  }
 }
}
void check_qr_pixels() {
 constexpr int size=BedLevelHelpQR::EXTENT, left=DWIN_WIDTH-size-12, top=30;
 int pixels[size][size]={};
 for(const auto &op:ops) if(op.kind=='R')
  for(int x=std::max(left,op.x0);x<=std::min(left+size-1,op.x1);++x)
   for(int y=std::max(top,op.y0);y<=std::min(top+size-1,op.y1);++y)
    pixels[x-left][y-top]=op.color;
 for(int x=0;x<size;++x) for(int y=0;y<size;++y) {
  const int qx=x/BedLevelHelpQR::SCALE-BedLevelHelpQR::QUIET,
            qy=y/BedLevelHelpQR::SCALE-BedLevelHelpQR::QUIET;
  const bool dark=qx>=0 && qy>=0 && qx<BedLevelHelpQR::SIZE && qy<BedLevelHelpQR::SIZE && BedLevelHelpQR::dark(qx,qy);
  assert(pixels[x][y]==(dark ? Color_Bg_Black : Color_White));
 }
}
void check_axes() {
 using namespace BedLevelVisualizer;
 int axes=0,labels=0; bool surface_started=false;
 for(const auto &op:ops) {
  const bool surface=op.kind=='R' && op.y0>=plot.top && op.y1<=plot.bottom;
  if(surface) surface_started=true;
  if(op.kind=='L' && op.color==AXIS_COLOR) {
   assert(!surface_started); // Surface must occlude the background axes.
   ++axes;
   assert(op.x0==lroundf(axis_origin().x) && op.y0==lroundf(axis_origin().y));
  }
  if(op.kind=='T' && (op.text=="X" || op.text=="Y" || op.text=="Z")) {
   ++labels; assert(surface_started);
   for(const auto &fill:ops) if(fill.kind=='R' && fill.y0>=plot.top && fill.y1<=plot.bottom)
    assert(op.x0+6<=fill.x0 || op.x0>fill.x1 || op.y0+12<=fill.y0 || op.y0>fill.y1);
   assert(op.y0>=120 && op.y0+12<256); // Clear of header, QR and legend.
  }
 }
 assert(axes==3 && labels==3 && !has_text("X+") && !has_text("Y+"));
}
int main(int argc,char **argv) {
 const std::string preview=argc>1 ? std::string(argv[1])+"/" : "";
 using namespace BedLevelSurface;
 using BedLevelAssessment::Score;
 using BedLevelAssessment::classify;
 // Reusing a row after a longer leveling label must leave no trailing text.
 for(uint8_t row=0;row<=MROWS;++row) {
  ops.clear(); draw_times.clear();
  DWIN_Draw_Label(MBASE(row),"Start Bed Leveling"); Item_Level_BedVisualizer(row);
  bool pixels[DWIN_WIDTH][DWIN_HEIGHT]={};
  for(const auto &op:ops) {
   if(op.kind=='R') for(int x=op.x0;x<=op.x1;++x) for(int y=op.y0;y<=op.y1;++y) pixels[x][y]=false;
   if(op.kind=='T') for(int x=op.x0;x<op.x0+int(op.text.size())*op.x1;++x)
    for(int y=op.y0;y<op.y0+16;++y) pixels[x][y]=true;
  }
  for(int x=LBLX+int(strlen("Bed Level Map"))*8;x<LBLX+int(strlen("Start Bed Leveling"))*8;++x)
   for(int y=MBASE(row);y<MBASE(row)+16;++y) assert(!pixels[x][y]);
 }
 char formatted[13];
 BedLevelVisualizer::format_mm(formatted,sizeof(formatted),-0.00001f,3,true);
 assert(strcmp(formatted,"+0.000")==0); // Avoid displaying negative zero.
 BedLevelVisualizer::format_mm(formatted,sizeof(formatted),1.2346f);
 assert(strcmp(formatted,"1.235")==0);
 BedLevelVisualizer::format_mm(formatted,sizeof(formatted),-1.2346f);
 assert(strcmp(formatted,"-1.235")==0);
 BedLevelVisualizer::format_mm(formatted,sizeof(formatted),INFINITY);
 assert(strcmp(formatted,"out of range")==0);
 BedLevelVisualizer::format_mm(formatted,sizeof(formatted),1e30f);
 assert(strcmp(formatted,"out of range")==0);
 assert(classify(0.3f,0.1f)==Score::Perfect);
 assert(classify(0.5f,0.2f)==Score::Good);
 assert(classify(1.0f,0.3f)==Score::Ok);
 assert(classify(2.0f,1.0f)==Score::Bad);
 assert(classify(2.01f,0.01f)==Score::Horrible);
 assert(classify(0.01f,1.01f)==Score::Horrible);
 assert(classify(0.4f,0.01f)==Score::Good); // Both original limits must be met.
 assert(classify(0.1f,0.25f)==Score::Ok);
 assert(classify(INFINITY,0)==Score::Incomplete);
 BedLevelAssessment::Stats sample;
 sample.add(-1);sample.add(1);
 assert(sample.range()==2 && sample.stddev()==1 && sample.score()==Score::Bad);
 sample.add(NAN);assert(sample.score()==Score::Incomplete && sample.missing==1);
 assert(color(0,1)==0x07e0 && color(-1,1)==0x001f && color(1,1)==0xf800);
 assert(color(-100,1)==color(-1,1) && color(100,1)==color(1,1));
 // Complementary triangles fill an entire square, with no empty seams.
 bool coverage[40][40]={}; Triangle raster; Span span;
 const Bounds bounds={20,40,59,79};
 const Point a={20,40,0},b={60,40,0},c={60,80,0},d={20,80,0};
 for(int half=0;half<2;++half) {
  raster.begin(a,half==0 ? b:c,half==0 ? c:d,bounds,1);
  while(raster.next(span)) {
   assert(span.left>=20 && span.right<=59 && span.y>=40 && span.y+PIXEL_SIZE-1<=79);
   for(int x=span.left;x<=span.right;++x) for(int y=span.y;y<span.y+PIXEL_SIZE;++y) coverage[x-20][y-40]=true;
  }
 }
 for(auto &column:coverage) for(bool filled:column) assert(filled);
 raster.begin(a,a,a,bounds,1); assert(!raster.next(span));

 for(int kind=0;kind<4;++kind) {
  shape(kind); float original[GRID_MAX_POINTS_X][GRID_MAX_POINTS_Y];
  memcpy(original,bedlevel.z_values,sizeof(original));
  BedLevelVisualizer::start(); complete();
  assert(memcmp(original,bedlevel.z_values,sizeof(original))==0);
  assert(has_text("Range:") && !ops.empty());
  bool title=false;
  for(const auto &op:ops) if(op.kind=='T' && op.text=="Bed Level Map") {
   title=true; assert(op.color==Color_Yellow && op.y0==4);
   assert(op.x0==(DWIN_WIDTH-int(op.text.size())*8)/2);
  }
  assert(title);
  assert(has_text("StdDev:") && has_text("Score:") && has_text("Help QR"));
  assert(!has_text("Mesh ") && !has_text("0,0"));
  if(kind==0) {
   assert(has_text("Min:+0.000 mm") && has_text("Max:+0.000 mm"));
   assert(has_text("Range:0.000 mm") && has_text("StdDev:0.000 mm"));
   assert(has_text("-0.05") && has_text("+0.05 mm"));
  }
  if(kind==1) {
   assert(has_text("Min:-0.400 mm") && has_text("Max:+0.400 mm"));
   assert(has_text("Range:0.800 mm"));
   char expected[32],value[16];
   BedLevelVisualizer::format_mm(value,sizeof(value),BedLevelVisualizer::stats.stddev());
   snprintf(expected,sizeof(expected),"StdDev:%s mm",value); assert(has_text(expected));
   assert(has_text("-0.40") && has_text("+0.40 mm"));
  }
  if(kind==0) assert(has_text("Score: PERFECT"));
  check_qr_pixels();
  check_surface_coverage();
  check_axes();
  int faces=0,edges=0; bool warm=false,cool=false;
  for(const auto &op:ops) {
   if(op.kind=='R' && op.y0>=128 && op.y1<=246 && op.y1-op.y0==PIXEL_SIZE) {
    ++faces; if(kind==0) assert(op.color==0x07e0);
    if((op.color>>11)>16 && (op.color&31)<8) warm=true;
    if((op.color&31)>16 && (op.color>>11)<8) cool=true;
   }
   if(op.kind=='L' && op.color==BedLevelVisualizer::GRID_COLOR) ++edges;
  }
  assert(faces>0 && edges==4*(GRID_MAX_POINTS_X-1)*(GRID_MAX_POINTS_Y-1));
  if(kind!=0 && GRID_MAX_POINTS_X>2 && GRID_MAX_POINTS_Y>2) assert(warm && cool);
  const char *name[]={"flat","tilted","curved","saddle"};
  if(!preview.empty()) dump(preview+name[kind]+".draw");
 }

 // Every original rating must also reach the LCD, not just the classifier.
 const float amplitude[]={0.05f,0.17f,0.25f,0.7f,1.2f};
 const char *ratings[]={"Score: PERFECT","Score: GOOD","Score: OK","Score: BAD","Score: HORRIBLE"};
 for(int rating=0;rating<5;++rating) {
  shape(0);
  for(auto &column:bedlevel.z_values) for(int y=0;y<GRID_MAX_POINTS_Y;++y) column[y]=(y&1 ? -1:1)*amplitude[rating];
  BedLevelVisualizer::start(); assert(ops.empty()); complete(); assert(has_text(ratings[rating]));
 }

 // Cancel both while drawing the QR and while drawing the surface.
 for(bool surface : {false,true}) {
  shape(1); BedLevelVisualizer::start();
  while(BedLevelVisualizer::busy()) {
   clock_now+=BED_LEVEL_VISUALIZER_DRAW_DELAY_MS; BedLevelVisualizer::update();
   const auto &op=ops.back();
   if(op.kind=='R' && op.y1-op.y0==(surface ? PIXEL_SIZE:1) && (surface ? op.y0>=128 && op.y1<=246 : op.y0>=30 && op.y1<=103)) break;
  }
  assert(BedLevelVisualizer::busy()); BedLevelVisualizer::cancel();
  auto canceled=ops; clock_now+=10000; BedLevelVisualizer::update(); assert(ops==canceled);
 }

 // A rendering uses a snapshot, even if another command later changes the live mesh.
 shape(1); BedLevelVisualizer::start(); complete(); auto reference=ops;
 shape(1); BedLevelVisualizer::start();
 for(auto &column:bedlevel.z_values) for(auto &z:column) z=99;
 complete(); assert(ops==reference);
 shape(1); BedLevelVisualizer::start(); BedLevelVisualizer::update();
 BedLevelVisualizer::cancel(); auto stopped=ops; complete(); assert(ops==stopped);

 // Empty, incomplete, non-finite, and large values stay within the panel bounds.
 shape(0); bedlevel.valid=false; BedLevelVisualizer::start(); complete();
 assert(has_text("No bed mesh") && has_text("Score: INCOMPLETE") && has_text("Help QR"));
 if(!preview.empty()) dump(preview+"empty.draw");
 shape(1); bedlevel.z_values[0][0]=NAN; BedLevelVisualizer::start(); complete();
 bool gray=false;
 for(const auto &op:ops) if(op.kind=='R' && op.y0>=128 && op.y1<=246 && op.color==MISSING_COLOR) gray=true;
 assert(gray && has_text("Score: INCOMPLETE")); if(!preview.empty()) dump(preview+"missing.draw");
 shape(0); for(auto &column:bedlevel.z_values) for(auto &z:column) z=INFINITY;
 BedLevelVisualizer::start(); complete(); assert(has_text("No measured points"));
 for(float value : {0.000001f,3.0f,1000.0f,-1000.0f}) {
  shape(0); for(auto &column:bedlevel.z_values) for(auto &z:column) z=value;
  BedLevelVisualizer::start(); complete();
  check_axes();
 }
 // The timer also works across millis() overflow.
 shape(0); clock_now=UINT32_MAX-5; BedLevelVisualizer::start(); complete();
 // Reach the new Leveling row with the real encoder handler. Its bounds and
 // Back selection must work without invoking homing, probing or mesh editing.
 shape(2); select_cextr.reset(); Draw_Level_Menu();
 assert(back_selected && has_text("Bed Level Map"));
 event=ENCODER_DIFF_CW;
 for(int n=0;n<LEVEL_CASE_BEDVIS;++n) HMI_Level_Menu();
 HMI_Level_Menu(); // Stop at the last row.
 assert(select_cextr.now==LEVEL_CASE_BEDVIS && highlighted_row==LEVEL_CASE_BEDVIS);
 for(int phase=0;phase<3;++phase) {
  shape(2); event=ENCODER_DIFF_ENTER; HMI_Level_Menu();
  assert(checkkey==BedLevelView && HMI_flag.Refresh_bottom_flag);
  event=ENCODER_DIFF_NO;
  while(BedLevelVisualizer::busy()) {
   HMI_BedLevelVisualizer(); clock_now+=BED_LEVEL_VISUALIZER_DRAW_DELAY_MS;
   if((phase==0 && BedLevelVisualizer::stage==BedLevelVisualizer::Stage::Header)
     || (phase==1 && BedLevelVisualizer::stage==BedLevelVisualizer::Stage::QrData)
     || (phase==2 && BedLevelVisualizer::stage==BedLevelVisualizer::Stage::Surface)) break;
  }
  assert(BedLevelVisualizer::busy());
  const int before=level_redraws;
  event=ENCODER_DIFF_ENTER; HMI_BedLevelVisualizer();
  assert(checkkey==Level && level_redraws==before+1 && !HMI_flag.Refresh_bottom_flag);
  assert(select_cextr.now==LEVEL_CASE_BEDVIS && highlighted_row==LEVEL_CASE_BEDVIS && !back_selected);
  auto returned=ops; draw_times.clear(); // Menu redraws are outside the paced map renderer.
  complete(); assert(ops==returned);
 }
 std::cout<<"PASS "<<GRID_MAX_POINTS_X<<'x'<<GRID_MAX_POINTS_Y
          <<": surfaces, assessment, QR, partial meshes, cancel, "<<BED_LEVEL_VISUALIZER_DRAW_DELAY_MS<<" ms pacing\n";
}
'''


def check_qr_payload():
    """Read the fixed version-3/M QR's format and byte payload independently.

    There is one data block at this version/ECC level, so no deinterleaving is
    needed. This also catches accidental changes to the case-sensitive URL.
    """
    header = (LCD / "bed_level_help_qr.h").read_text()
    data = header.split("modules[SIZE][4]")[1].split("};", 1)[0]
    packed = bytes(int(value, 16) for value in re.findall(r"0x([0-9A-F]{2})", data))
    assert len(packed) == 29 * 4
    matrix = [[bool(packed[y * 4 + x // 8] & (0x80 >> (x % 8))) for x in range(29)] for y in range(29)]
    positions = [(8, i if i < 6 else i + 1 if i < 8 else 29 - 15 + i) for i in range(15)]
    encoded_format = sum(int(matrix[y][x]) << i for i, (x, y) in enumerate(positions))

    def format_bits(value):
        remainder = value << 10
        while remainder.bit_length() >= 11:
            remainder ^= 0x537 << (remainder.bit_length() - 11)
        return ((value << 10) | remainder) ^ 0x5412

    format_value = next(value for value in range(32) if format_bits(value) == encoded_format)
    assert format_value >> 3 == 0  # Medium error correction.
    mask = format_value & 7
    reserved = {(x, y) for y in range(29) for x in range(29)
                if (x <= 8 and y <= 8) or (x >= 21 and y <= 8) or (x <= 8 and y >= 21)
                or x == 6 or y == 6 or (20 <= x <= 24 and 20 <= y <= 24)}

    def masked(x, y):
        return ((x + y) % 2 == 0, y % 2 == 0, x % 3 == 0, (x + y) % 3 == 0,
                (y // 2 + x // 3) % 2 == 0, (x * y) % 2 + (x * y) % 3 == 0,
                ((x * y) % 2 + (x * y) % 3) % 2 == 0,
                ((x * y) % 3 + (x + y) % 2) % 2 == 0)[mask]

    bits, right, upward = [], 28, True
    while right > 0:
        if right == 6:
            right -= 1
        for y in (range(28, -1, -1) if upward else range(29)):
            for x in (right, right - 1):
                if (x, y) not in reserved:
                    bits.append(int(matrix[y][x] != masked(x, y)))
        upward, right = not upward, right - 2
    assert len(bits) == 567
    position = 0

    def take(count):
        nonlocal position
        value = 0
        for bit in bits[position:position + count]:
            value = value * 2 + bit
        position += count
        return value

    assert take(4) == 4  # Byte mode, without uppercasing or rewriting the link.
    payload = bytes(take(8) for _ in range(take(8))).decode("ascii")
    assert payload == "https://bit.ly/navaismo-bed-leveling"
    print(f"PASS QR payload: {payload}")


def previews(directory):
    def rgb(color):
        return "#%02x%02x%02x" % ((color >> 11) * 255 // 31, ((color >> 5) & 63) * 255 // 63, (color & 31) * 255 // 31)

    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="740" font-family="DejaVu Sans Mono" xml:space="preserve">',
           '<rect width="800" height="740" fill="#181c25"/>']
    for index, name in enumerate(("flat", "tilted", "curved", "saddle", "missing", "empty")):
        x, y = 20 + index % 3 * 260, 20 + index // 3 * 360
        svg.append(f'<text x="{x}" y="{y + 12}" fill="white" font-size="12">{name.capitalize()}</text>')
        svg.append(f'<g transform="translate({x},{y + 22})">')
        for line in (directory / f"{name}.draw").read_text().splitlines():
            kind, x0, y0, x1, y1, color, *text = line.split(" ", 6)
            x0, y0, x1, y1, color = map(int, (x0, y0, x1, y1, color))
            if kind == "R":
                svg.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0+1}" height="{y1-y0+1}" fill="{rgb(color)}"/>')
            elif kind == "L":
                svg.append(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}" stroke="{rgb(color)}"/>')
            else:
                value = text[0] if text else ""
                font = 10 if x1 == 6 else 13
                svg.append(f'<text x="{x0}" y="{y0+font}" fill="{rgb(color)}" font-size="{font}">{escape(value)}</text>')
        svg.append('</g>')
    svg.append('</svg>')
    path = directory / "bed-level-visualizer.svg"
    path.write_text("\n".join(svg))
    if shutil.which("magick"):
        subprocess.run(["magick", "-background", "#181c25", str(path), str(path.with_suffix('.png'))], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--sanitize", action="store_true", help="Enable UBSan (requires libubsan)")
    args = parser.parse_args()
    check_qr_payload()
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
    # Keep every production statement; replace only the header-provided hardware dependencies.
    implementation = re.sub(r'^#include .*$', '', (LCD / 'bed_level_visualizer.cpp').read_text(), flags=re.M)
    with tempfile.TemporaryDirectory(prefix="bed-level-visualizer-") as tmp:
        cpp, binary = Path(tmp) / "renderer.cpp", Path(tmp) / "renderer"
        dwin = (LCD / 'dwin.cpp').read_text()
        handler_start = dwin.index('  static void HMI_BedLevelVisualizer()')
        handler_end = dwin.index('\n  }', handler_start) + 4
        handler = dwin[handler_start:handler_end]
        control = dwin[dwin.index('void HMI_Control()'):dwin.index('// Change leveling value')]
        assert 'BedLevelView' not in control and 'BedLevelVisualizer' not in control
        level_defines = '\n'.join(line for line in dwin.splitlines() if line.startswith('#define LEVEL_CASE_')) + '\n'
        def menu_function(start, end):
            first = dwin.index(start)
            return dwin[first:dwin.index(end, first) + len(end)]
        menu = menu_function('void Erase_Menu_Text(', '\n}\n')
        menu += '#if ENABLED(BED_LEVEL_VISUALIZER)\n'
        menu += menu_function('  static void Item_Level_BedVisualizer(', '\n  }\n')
        menu += '#endif\n'
        menu += menu_function('void Draw_Level_Menu(', '\n}\n')
        menu += menu_function('void HMI_Level_Menu(', '\n}\n')
        cpp.write_text(STUBS + level_defines + implementation + menu + handler + TESTS)
        for nx, ny, delay in ((6, 6, 10), (2, 2, 10), (3, 9, 10), (9, 3, 10), (11, 11, 10), (6, 6, 20)):
            subprocess.run(["g++", "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
                            *(["-fsanitize=undefined"] if args.sanitize else []),
                            f"-DGRID_MAX_POINTS_X={nx}", f"-DGRID_MAX_POINTS_Y={ny}",
                            f"-DBED_LEVEL_VISUALIZER_DRAW_DELAY_MS={delay}", "-I", str(LCD),
                            str(cpp), "-o", str(binary)], check=True)
            preview_args = [str(args.preview_dir)] if nx == ny == 6 and delay == 10 and args.preview_dir else []
            subprocess.run([str(binary), *preview_args], check=True)
        # Compile the actual Leveling menu without the feature as well. Its
        # fourth row and entry must disappear, retaining the original bounds.
        disabled = r'''
int main() {
 static_assert(LEVEL_CASE_TOTAL==3);
 Draw_Level_Menu();
 assert(back_selected && !HMI_flag.Refresh_bottom_flag);
 for(const auto &op:ops) assert(op.text!="Bed Level Map");
 event=ENCODER_DIFF_CW;
 for(int n=0;n<10;++n) HMI_Level_Menu();
 assert(select_cextr.now==3 && highlighted_row==3);
 std::cout<<"PASS Leveling menu with BED_LEVEL_VISUALIZER disabled\n";
}
'''
        cpp.write_text(STUBS + level_defines + menu + disabled)
        subprocess.run(["g++", "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
                        "-DBED_LEVEL_VISUALIZER=0", "-DGRID_MAX_POINTS_X=6", "-DGRID_MAX_POINTS_Y=6",
                        "-I", str(LCD), str(cpp), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    if args.preview_dir:
        previews(args.preview_dir)
        print(f"Preview: {args.preview_dir / 'bed-level-visualizer.svg'}")


if __name__ == "__main__":
    main()
