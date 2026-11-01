#!/usr/bin/env python3
"""Replay the production PLR checkpoint/resume code with moving planner state."""
from pathlib import Path
import subprocess
import tempfile
import test_dwin_powerloss as common

ROOT = common.ROOT
SOURCE = (ROOT/'Marlin/src/feature/powerloss.cpp').read_text()

STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cmath>
#include <cstring>
#include <cfloat>
#include <algorithm>
#include <functional>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#define CAT_(A,B) A##B
#define CAT(A,B) CAT_(A,B)
#define CHOOSE_0(A,B) B
#define CHOOSE_1(A,B) A
#define TERN(V,A,B) CAT(CHOOSE_,V)(A,B)
#define TERN_(V,A) TERN(V,A,)
#define TERN0(V,A) TERN(V,A,0)
#define ENABLED(V) (V)
#define DISABLED(V) (!(V))
#define F(S) S
#define ANY(A,B) ((A)||(B))
#define ABS(V) std::abs(V)
#define _MIN(A,B) std::min(float(A),float(B))
#define _MAX(A,B) std::max(float(A),float(B))
#define COPY(A,B) memcpy(A,B,sizeof(A))
#define MMS_TO_MMM(V) ((V)*60)
#define E_TERN_(...)
#define DEBUG_ECHOLNPGM(...) do{}while(0)
#define SERIAL_ECHOLNPGM(...) do{}while(0)
#define CRITICAL_SECTION_START() ++critical_depth
#define CRITICAL_SECTION_END() --critical_depth
#define SAVE_INFO_INTERVAL_MS 0
#define SAVE_EACH_CMD_MODE 0
#define DWIN_PLR_MENU 1
#define CANCEL_OBJECTS 0
#define GCODE_REPEAT_MARKERS 0
#define HAS_HOME_OFFSET TEST_HOME_OFFSET
#define HAS_WORKSPACE_OFFSET TEST_WORKSPACE_OFFSET
#define HAS_VOLUMETRIC_EXTRUSION 0
#define HAS_HEATED_CHAMBER 0
#define HAS_FAN 0
#define HAS_LEVELING 0
#define HAS_POSITION_MODIFIERS 0
#define GRADIENT_MIX 0
#define FWRETRACT 0
#define HAS_HOTEND 1
#define HAS_HEATED_BED 1
#define HOTEND_LOOP() for(int e=0;e<1;++e)
#define EXTRUDER_LOOP() for(int e=0;e<1;++e)
#define PREVENT_COLD_EXTRUSION 1
#define DEBUG_POWER_LOSS_RECOVERY 0
#define HAS_MULTI_HOTEND 0
#define HAS_MULTI_EXTRUDER 0
#define Z_HOME_TO_MAX 0
#define POWER_LOSS_RECOVER_ZHOME 0
#define BELTPRINTER 0
#define BACKUP_POWER_SUPPLY 0
#define POWER_LOSS_RETRACT_LEN 0
#define NOZZLE_CLEAN_FEATURE 0
#define SOVOL_SV06_RTS 0
#define MAX_CMD_SIZE 128
#define Z_MAX_POS 250
#define PLR_CAN_ABORT 1
#define MARLIN_DEBUG_DRYRUN 8
#define PROCESS_SUBCOMMANDS_NOW(cmd) do{if(card.flag.abort_sd_printing)return;gcode.process_subcommands_now(cmd);}while(0)
using celsius_t=int16_t;
using relative_t=uint8_t;
using millis_t=uint32_t;
int critical_depth=0;
int marlin_debug_flags=0;
constexpr uint8_t E_REL=1;
struct Position {
 float x=0,y=0,z=0,e=0;
 void reset(){x=y=z=e=0;}
 Position &operator-=(const Position &p){x-=p.x;y-=p.y;z-=p.z;return *this;}
};
using xyze_pos_t=Position;
struct job_recovery_info_t {
 uint8_t valid_head=0;
 Position current_position{};
 Position command_start_position{};
 Position home_offset{},workspace_offset{};
 uint32_t sdpos=0;
 uint16_t feedrate=1200;
 int16_t feedrate_percentage=100;
 uint16_t flow_percentage[1]={100};
 float zraise=5;
 celsius_t target_temperature[1]={235},target_temperature_bed=62;
 millis_t print_job_elapsed=0;
 relative_t axis_relative=E_REL;
 struct {bool raised=false,dryrun=false,allow_cold_extrusion=false;} flag{};
 char sd_filename[80]="/MODEL.GCO";
 uint8_t valid_foot=0;
 bool valid(){return valid_head && valid_head==valid_foot;}
};
struct PrintJobRecovery {
 inline static job_recovery_info_t info;
 inline static uint32_t cmd_sdpos=0;
 inline static float last_saved_z=-FLT_MAX;
 inline static volatile bool command_start_valid=false;
 static void init();static void prepare();static void load();
 static void capture_block(uint32_t,const Position &);
 static void save(bool=false,float=-1,bool=false);static void write();static void resume();
 static void open(bool){}static void close();static bool exists(){return true;}
 static void debug(const char*){}static void enable(bool){}
} recovery;
std::vector<job_recovery_info_t> records;
struct File {
 bool short_write=false,close_ok=true;
 int read_limit=-1;
 std::function<void()> on_write;
 int seekSet(int){return 0;}
 int write(const void *data,size_t size){
  assert(critical_depth==0); // Never hold off interrupts during SD I/O.
  job_recovery_info_t stored;
  auto raw=static_cast<const uint8_t*>(data);
  // Simulate the ISR / motion service updating the live tuple during I/O.
  const size_t split=offsetof(job_recovery_info_t,current_position)+offsetof(Position,z);
  auto stored_bytes=reinterpret_cast<uint8_t*>(&stored);
  memcpy(stored_bytes,raw,split);
  if(on_write)on_write();
  memcpy(stored_bytes+split,raw+split,size-split);
  if(!short_write)records.push_back(stored);
  return short_write ? int(size)-1 : int(size);
 }
 int read(void *data,size_t size){if(records.empty())return 0;const int n=read_limit<0?int(size):read_limit;memcpy(data,&records.back(),n);return n;}
 bool close(){return close_ok;}
} file;
void PrintJobRecovery::close(){file.close();}
bool motion_synchronized=false;
int position_reports=0;
struct {
 Position position,home_offset,workspace_offset;
 float feedrate_mm_s=20;
 int feedrate_percentage=100;
 void set_all_homed(){}
 void report_position(){assert(motion_synchronized && position_reports==0);++position_reports;}
 void report_position_real(){assert(motion_synchronized && position_reports==1);++position_reports;}
} motion;
struct {
 uint16_t flow_percentage[1]={100};
 void set_flow(int,int n){flow_percentage[0]=n;}
 void synchronize(){motion_synchronized=true;}
} planner;
struct {
 bool allow_cold_extrude=false;
 int degTargetHotend(int){return 235;}int degTargetBed(){return 62;}
} thermalManager;
struct {millis_t duration(){return 1000;}} print_job_timer;
struct {float zraise(){return 5;}float save_step(){return 0.05f;}float purge(){return 2.5f;}} plrSettings;
struct {
 uint32_t offset=0;
 struct {bool abort_sd_printing=false;} flag;
 uint32_t getIndex(){return offset;}
 void getAbsFilenameInCWD(char *dst){strcpy(dst,"/MODEL.GCO");}
} card;
std::vector<std::string> commands;
std::vector<std::pair<float,float>> extrusions;
float extruder_origin=0;
Position physical_position;
struct Gcode {
 relative_t axis_relative=0;
 void set_relative_mode(bool rel){axis_relative=rel?E_REL:0;}
 void process_subcommands_now(const std::string &command){
  commands.push_back(command);
  std::istringstream input(command);std::string line;
  while(std::getline(input,line)){
   if(line=="G90"){position_reports=0;motion_synchronized=false;}
   if(line=="G90" || line=="M82")axis_relative=0;
   if(line=="M83")axis_relative=E_REL;
   if(line.rfind("G92.9E",0)==0)motion.position.e=extruder_origin=std::stof(line.substr(6));
   if(line.rfind("G92.9Z",0)==0)motion.position.z=std::stof(line.substr(6));
   if(line=="G28R0XY"){
    // Cartesian set_axis_is_at_home: base home + home offset, and clear
    // the workspace offset of each homed axis. The endstops do not move.
    motion.position.x=-4+TERN0(HAS_HOME_OFFSET,motion.home_offset.x);
    motion.position.y=-17+TERN0(HAS_HOME_OFFSET,motion.home_offset.y);
    physical_position.x=-4;physical_position.y=-17;
    TERN_(HAS_WORKSPACE_OFFSET,motion.workspace_offset.x=motion.workspace_offset.y=0);
   }
   if(line.rfind("G1",0)==0){
    motion_synchronized=false;
    auto move_axis=[&](char axis,float &native,float &physical,float workspace,float home){
     const auto at=line.find(axis);
     if(at==std::string::npos)return;
     native=std::stof(line.substr(at+1))-workspace;
     physical=native-home;
    };
    move_axis('X',motion.position.x,physical_position.x,TERN0(HAS_WORKSPACE_OFFSET,motion.workspace_offset.x),TERN0(HAS_HOME_OFFSET,motion.home_offset.x));
    move_axis('Y',motion.position.y,physical_position.y,TERN0(HAS_WORKSPACE_OFFSET,motion.workspace_offset.y),TERN0(HAS_HOME_OFFSET,motion.home_offset.y));
    move_axis('Z',motion.position.z,physical_position.z,TERN0(HAS_WORKSPACE_OFFSET,motion.workspace_offset.z),TERN0(HAS_HOME_OFFSET,motion.home_offset.z));
    const auto pos=line.find('E');
    if(pos!=std::string::npos){
     const float value=std::stof(line.substr(pos+1));
     const float delta=(axis_relative&E_REL)?value:value-extruder_origin;
     const auto f=line.find('F');
     const float feed=f==std::string::npos?0:std::stof(line.substr(f+1, pos>f ? pos-f-1 : std::string::npos));
     extrusions.push_back({delta,feed});extruder_origin+=delta;
     motion.position.e=extruder_origin;
    }
   }
   if(line.rfind("M24S",0)==0){
    assert(motion_synchronized && position_reports==2 && "PLR diagnostics ran before motion finished or after SD resume");
    card.offset=std::stoul(line.substr(4));
   }
  }
 }
} gcode;
inline float p_float_t(float value,int){return value;}
template<class...T>std::string TS(T...args){std::ostringstream s;(s<<...<<args);return s.str();}
template<int N>struct MString:std::string{template<class...T>MString(T...a):std::string(TS(a...)){};};
'''

TESTS = r'''
void moving_sample(float z,uint32_t offset){
 // FTM/stepper already updated the live position to this small vase segment.
 PrintJobRecovery::capture_block(offset,{80,60,z,20});
 motion.position.z=z+0.002f;
 PrintJobRecovery::save();
}
int main(){
 PrintJobRecovery::init();records.clear();
 for(int i=0;i<10000;++i)moving_sample(0.2f+i*0.002f,1000+i*30);
 assert(records.size()>350 && "continuous Z never advances the saved checkpoint");
 assert(records.back().current_position.z>20.1f && "checkpoint is many layers behind");
 std::cout<<"PASS vase-mode small Z increments: "<<records.size()<<" checkpoints, last Z="<<records.back().current_position.z<<"\n";
 // A downward return from a Z-hop must not leave a checkpoint stuck high.
 moving_sample(2,44444);moving_sample(0.2f,44500);
 assert(fabs(records.back().current_position.z-0.2f)<0.001f);
 // A partial write must not advance the last-successful-save baseline.
 const float previous=PrintJobRecovery::last_saved_z;
 file.short_write=true;moving_sample(previous+0.1f,55555);
 assert(PrintJobRecovery::last_saved_z==previous);
 file.short_write=false;moving_sample(previous+0.1f,55555);
 assert(PrintJobRecovery::last_saved_z>previous);
 // A failed close also leaves the previous durable-Z baseline in place.
 const float before_close=PrintJobRecovery::last_saved_z;
 file.close_ok=false;moving_sample(before_close+0.1f,60000);
 assert(PrintJobRecovery::last_saved_z==before_close);file.close_ok=true;
 // A truncated reload must never reuse old valid markers or coordinates.
 file.read_limit=8;PrintJobRecovery::load();assert(!PrintJobRecovery::info.valid());file.read_limit=-1;
 // A pre-anchor recovery record is shorter by one position tuple.
 file.read_limit=sizeof(job_recovery_info_t)-sizeof(Position);
 PrintJobRecovery::load();assert(!PrintJobRecovery::info.valid());file.read_limit=-1;
 // Snapshot must keep XYZ/E and byte offset together while live state changes.
 PrintJobRecovery::info.current_position={1,2,10,45};PrintJobRecovery::info.sdpos=7000;
 PrintJobRecovery::info.command_start_position={0,1,9.8f,44};
 file.on_write=[](){PrintJobRecovery::info.current_position={99,88,20,900};PrintJobRecovery::info.sdpos=9000;PrintJobRecovery::info.command_start_position={98,87,19,890};};
 PrintJobRecovery::save(true);
 file.on_write={};
 assert(records.back().current_position.z==10 && records.back().current_position.e==45 && records.back().sdpos==7000);
 assert(records.back().command_start_position.z==9.8f && records.back().command_start_position.e==44);
 assert(PrintJobRecovery::last_saved_z==10);
 // First resumed line must carry the resumed byte offset, never zero.
 card.offset=7000;PrintJobRecovery::prepare();assert(PrintJobRecovery::cmd_sdpos==7000);
 // Resume recovery commands are absolute; restore the file's M83 or M82 mode.
 for(relative_t mode:{relative_t(0),E_REL}){
  PrintJobRecovery::info={};
  PrintJobRecovery::info.current_position={90,70,12.2f,45};
  PrintJobRecovery::info.command_start_position=PrintJobRecovery::info.current_position;
  PrintJobRecovery::info.sdpos=7000;PrintJobRecovery::info.zraise=5;
  PrintJobRecovery::info.axis_relative=mode;
  commands.clear();extrusions.clear();extruder_origin=0;
  gcode.axis_relative=E_REL; // Also cover manual M1000 issued from relative mode.
  PrintJobRecovery::resume();
  assert(gcode.axis_relative==mode && card.offset==7000);
  assert(extrusions.size()==1 && fabs(extrusions[0].first-2.5f)<0.001f);
  assert(extrusions[0].second>0 && extrusions[0].second<=180 && "purge is too fast to melt PETG");
  assert(extruder_origin==45);
 }
 std::cout<<"PASS immutable checkpoint snapshot, retry after short write, resumed SD offset, relative/absolute E restoration and slow purge\n";
 // A home offset changed after M501, or G92 workspace offset cleared by
 // G28, must not shift the return point. Cover zero offsets as well.
 for(bool nonzero:{false,true}){
  PrintJobRecovery::info={};
  auto &info=PrintJobRecovery::info;
  info.current_position={90,70,12.2f,45};info.sdpos=7000;
  info.command_start_position=info.current_position;
  if(nonzero){info.home_offset={3.25f,-1.5f,0};info.workspace_offset={2.75f,-1,0.4f};}
  // Values at reboot need not be the ones active in the interrupted job.
  motion.home_offset={};motion.workspace_offset={-7,2,-1};
  PrintJobRecovery::resume();
  const float expected_x=90-TERN0(HAS_WORKSPACE_OFFSET,info.workspace_offset.x)-TERN0(HAS_HOME_OFFSET,info.home_offset.x);
  const float expected_y=70-TERN0(HAS_WORKSPACE_OFFSET,info.workspace_offset.y)-TERN0(HAS_HOME_OFFSET,info.home_offset.y);
  assert(fabs(physical_position.x-expected_x)<0.001f && "PLR returns to a shifted physical X");
  assert(fabs(physical_position.y-expected_y)<0.001f && "PLR returns to a shifted physical Y");
  assert(fabs(motion.position.z-(12.2f-TERN0(HAS_WORKSPACE_OFFSET,info.workspace_offset.z)))<0.001f);
  // The first file command at the same logical XY must not jump sideways.
  gcode.process_subcommands_now("G1X90Y70");
  assert(fabs(physical_position.x-expected_x)<0.001f);
  assert(fabs(physical_position.y-expected_y)<0.001f);
 }
 std::cout<<"PASS return to saved physical XY and native Z, with home/workspace offsets "<<HAS_HOME_OFFSET<<'/'<<HAS_WORKSPACE_OFFSET<<"\n";
 std::cout<<"PASS commanded/step-counter reports after motion synchronization and before SD restart\n";
 // Segment boundaries keep updating physical Z, but not the replay start.
 PrintJobRecovery::init();
 PrintJobRecovery::capture_block(0,{90,70,2,0});
 PrintJobRecovery::capture_block(0,{86,72,2.5f,0.2f});
 assert(PrintJobRecovery::info.command_start_position.x==90);
 assert(PrintJobRecovery::info.current_position.x==86 && PrintJobRecovery::info.current_position.z==2.5f);
 PrintJobRecovery::capture_block(200,{91,71,3,1});
 assert(PrintJobRecovery::info.command_start_position.x==91);
 // prepare must reset the anchor even if a new job reuses the last SD offset.
 PrintJobRecovery::prepare();PrintJobRecovery::capture_block(200,{100,80,4,2});
 assert(PrintJobRecovery::info.command_start_position.x==100);
 // Resume M83 at the whole-command start, not halfway through its extrusion.
 PrintJobRecovery::info={};auto &info=PrintJobRecovery::info;
 info.command_start_position={90,70,2,0};info.current_position={86,70,2,0.2f};info.sdpos=200;
 motion.home_offset={};motion.workspace_offset={};
 PrintJobRecovery::resume();
 assert(motion.position.x==90 && extruder_origin==0);
 gcode.process_subcommands_now("G1X80Y70E0.5");
 assert(motion.position.x==80 && fabs(extruder_origin-0.5f)<0.001f);
 std::cout<<"PASS segmented-command anchor, live Z, reused offsets, full-command M83 replay\n";
}
'''


def main():
    functions='\n'.join(common.function(SOURCE,p) for p in (
        'void PrintJobRecovery::init()', 'void PrintJobRecovery::prepare()', 'void PrintJobRecovery::load()',
        'void PrintJobRecovery::capture_block(',
        'void PrintJobRecovery::save(', 'void PrintJobRecovery::write()',
        'void PrintJobRecovery::resume()',))
    # Declare the fake file as the production static member via a token alias.
    functions=functions.replace('file.', '::file.')
    with tempfile.TemporaryDirectory(prefix='plr-checkpoint-') as folder:
        source,binary=Path(folder)/'test.cpp',Path(folder)/'test'
        source.write_text(STUBS+functions+TESTS)
        for home, workspace in ((0,0),(1,0),(0,1),(1,1)):
            subprocess.run(['g++','-std=c++17','-O1','-Wall','-Wextra','-Werror',
                            f'-DTEST_HOME_OFFSET={home}', f'-DTEST_WORKSPACE_OFFSET={workspace}',
                            str(source),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)


if __name__=='__main__':
    main()
