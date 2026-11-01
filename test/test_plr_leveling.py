#!/usr/bin/env python3
"""Exercise production PLR resume and leveling with an independent physical Z.

The G-code adapter models G92.9 as a counter rebase, not a physical move.
Leveling transforms and enable/disable position handling come from Marlin.
"""
from pathlib import Path
import subprocess
import tempfile
import test_plr_checkpoint as checkpoint

ROOT = checkpoint.ROOT


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


def harness():
    source = checkpoint.STUBS
    source = replace_once(source, '#define HAS_LEVELING 0', r'''
#define HAS_LEVELING 1
#define AUTO_BED_LEVELING_BILINEAR 1
#define ABL_PLANAR 0
#define HAS_MESH 1
#define MESH_BED_LEVELING 0
#define ENABLE_LEVELING_FADE_HEIGHT 1
#define DIFF_TERN(V,A,B) TERN(V,(A)-(B),A)
#define TERN1(V,A) TERN(V,A,1)
#define DEBUG_SECTION(...)
#define DEBUGGING(...) false
#define DEBUG_POS(...) do{}while(0)
#define FLIP(V) ((V)=!(V))
''')
    source = replace_once(source, '#define HAS_POSITION_MODIFIERS 0', '#define HAS_POSITION_MODIFIERS 1')
    source = replace_once(source, 'float zraise=5;', 'float zraise=5,fade=0;')
    source = replace_once(source, 'bool raised=false,dryrun=false,allow_cold_extrusion=false;',
                          'bool raised=false,dryrun=false,allow_cold_extrusion=false,leveling=false;')
    source = replace_once(source, 'struct {\n Position position,home_offset,workspace_offset;',
                          'struct Motion {\n void sync_plan_position();\n Position position,home_offset,workspace_offset;')
    source = replace_once(source, 'struct {\n uint16_t flow_percentage[1]={100};', r'''
using xyz_pos_t=Position;
Position physical_position;
float z_counter_origin=0;
struct {float constant=0,dx=0,dy=0;
 float get_z_correction(const Position &p){return constant+dx*p.x+dy*p.y;}
} bedlevel;
bool leveling_is_valid(){return true;}
void set_bed_leveling_enabled(bool);
struct Planner {
 bool leveling_active=false;
 float z_fade_height=0,inverse_z_fade_height=0;
 void apply_leveling(Position &);
 void unapply_leveling(Position &);
 void apply_modifiers(Position &p,bool use=true){if(use)apply_leveling(p);}
 void unapply_modifiers(Position &p,bool use=true){if(use)unapply_leveling(p);}
 float fade_scaling_factor_for_z(float z){return z_fade_height==0?1:(z>=z_fade_height?0:1-z/z_fade_height);}
 uint16_t flow_percentage[1]={100};''')
    source = replace_once(source, '} planner;', r'''} planner;
void Motion::sync_plan_position(){
 Position machine=position;
 planner.apply_modifiers(machine,true);
 // Setting planner/stepper coordinates changes the reference, not physical Z.
 z_counter_origin=machine.z-physical_position.z;
}
''')
    source = replace_once(source, 'Position physical_position;\nstruct Gcode', 'struct Gcode')
    source = replace_once(source,
        'if(line.rfind("G92.9Z",0)==0)motion.position.z=std::stof(line.substr(6));', r'''
   if(line.rfind("G92.9Z",0)==0){motion.position.z=std::stof(line.substr(6));motion.sync_plan_position();}
   if(line.rfind("M420S",0)==0){
    const bool enable=line[5]!='0';
    const auto z=line.find('Z');
    if(z!=std::string::npos){
     const float fade=std::stof(line.substr(z+1));
     // M420 / set_z_fade_height preserve physical position when changing fade.
     if(fade!=planner.z_fade_height){
      const bool was=planner.leveling_active;
      set_bed_leveling_enabled(false);
      planner.z_fade_height=fade;planner.inverse_z_fade_height=fade?1/fade:0;
      set_bed_leveling_enabled(was);
     }
    }
    set_bed_leveling_enabled(enable);
   }
''')
    source = replace_once(source, 'if(line=="G28R0XY"){',
                          'if(line=="G28R0XY"){set_bed_leveling_enabled(false);')
    source = replace_once(source, 'physical_position.x=-4;physical_position.y=-17;', r'''
    physical_position.x=-4;physical_position.y=-17;
    motion.sync_plan_position();
    set_bed_leveling_enabled(TEST_LEVELING_AFTER_G28);
''')
    source = replace_once(source, "const auto pos=line.find('E');", r'''
    Position machine=motion.position;
    planner.apply_modifiers(machine,true);
    physical_position.z=machine.z-z_counter_origin;
    const auto pos=line.find('E');''')
    return source


TESTS = r'''
int main(){
 (void)print_job_timer;
 for(bool enabled:{false,true})for(bool boot_enabled:{false,true})
 for(float fade:{0.0f,10.0f})for(float correction:{-0.3f,0.0f,0.3f})
 for(float slope:{0.0f,0.002f})for(bool partial:{false,true}){
  // The saved machine Z contains the leveling correction. Home XY is at
  // another point of this sloped mesh, so the two corrections can differ.
  bedlevel.constant=correction;bedlevel.dx=slope;bedlevel.dy=-slope;
  planner.leveling_active=enabled;planner.z_fade_height=fade;
  planner.inverse_z_fade_height=fade?1/fade:0;
  const Position nominal={90,70,4.2f,45};
  Position saved=nominal;planner.apply_modifiers(saved,true);
  Position live=nominal;
  if(partial){live.x-=4;live.y+=2;live.z+=0.5f;live.e+=0.2f;}
  planner.apply_modifiers(live,true);
  PrintJobRecovery::info={};auto &info=PrintJobRecovery::info;
  info.current_position=live;info.command_start_position=saved;info.sdpos=7000;
  info.home_offset={TERN0(HAS_HOME_OFFSET,2.0f),TERN0(HAS_HOME_OFFSET,-1.0f),0};
  info.workspace_offset={TERN0(HAS_WORKSPACE_OFFSET,3.0f),TERN0(HAS_WORKSPACE_OFFSET,-1.5f),TERN0(HAS_WORKSPACE_OFFSET,0.4f)};
  info.current_position.x+=info.workspace_offset.x;
  info.current_position.y+=info.workspace_offset.y;
  info.current_position.z+=info.workspace_offset.z;
  info.command_start_position.x+=info.workspace_offset.x;
  info.command_start_position.y+=info.workspace_offset.y;
  info.command_start_position.z+=info.workspace_offset.z;
  info.fade=fade;info.flag.leveling=enabled;
  // Reboot: no homed coordinates, but the real nozzle is still at saved Z.
  physical_position=live;motion.position={};z_counter_origin=-live.z;
  physical_position.x-=info.home_offset.x;physical_position.y-=info.home_offset.y;
  motion.home_offset={};motion.workspace_offset={};
  planner.leveling_active=boot_enabled;
  planner.z_fade_height=15;planner.inverse_z_fade_height=1.0f/15;
  PrintJobRecovery::resume();
  assert(planner.leveling_active==enabled && "M420 must restore the saved leveling switch exactly");
  const float error=physical_position.z-saved.z;
  if(fabs(error)>0.001f || fabs(motion.position.z-nominal.z)>0.001f){
   std::cerr<<"Z mismatch: mesh="<<correction<<" slope="<<slope
    <<" saved leveling="<<enabled<<" boot leveling="<<boot_enabled<<" fade="<<fade
    <<" expected physical="<<saved.z<<" actual="<<physical_position.z
    <<" expected nominal="<<nominal.z<<" actual="<<motion.position.z<<'\n';
   return 1;
  }
  assert(fabs(physical_position.x-(nominal.x-info.home_offset.x))<0.001f);
  assert(fabs(physical_position.y-(nominal.y-info.home_offset.y))<0.001f);
  // Next layer of the file must move to its leveled height without a rebase.
  Position next=nominal;next.z+=0.2f;
  planner.apply_modifiers(next,true);
  gcode.process_subcommands_now(TS("G1X",90+info.workspace_offset.x,"Y",70+info.workspace_offset.y,"Z",4.4f+info.workspace_offset.z));
  if(fabs(physical_position.z-next.z)>0.001f){
   std::cerr<<"Next-layer Z mismatch: saved leveling="<<enabled<<" boot="<<boot_enabled
    <<" mesh="<<correction<<" slope="<<slope<<" fade="<<fade
    <<" expected="<<next.z<<" actual="<<physical_position.z<<" origin="<<z_counter_origin<<'\n';
   return 1;
  }
 }
 std::cout<<"PASS PLR nominal/physical Z and next layer: mesh/fade, segmented command, saved/boot leveling; G28 auto-leveling="<<TEST_LEVELING_AFTER_G28<<" offsets="<<HAS_HOME_OFFSET<<'/'<<HAS_WORKSPACE_OFFSET<<'\n';
}
'''


def main():
    level_source = (ROOT/'Marlin/src/module/planner.cpp').read_text()
    bed_source = (ROOT/'Marlin/src/feature/bedlevel/bedlevel.cpp').read_text()
    transforms = '\n'.join(checkpoint.common.function(level_source, prefix) for prefix in (
        'void Planner::apply_leveling(', 'void Planner::unapply_leveling('))
    transforms += checkpoint.common.function(bed_source, 'void set_bed_leveling_enabled(')
    resume = checkpoint.common.function(checkpoint.SOURCE, 'void PrintJobRecovery::resume()')
    with tempfile.TemporaryDirectory(prefix='plr-leveling-') as folder:
        source, binary = Path(folder)/'test.cpp', Path(folder)/'test'
        source.write_text(harness()+transforms+resume+TESTS)
        for after_home, offsets in ((0,0),(1,0),(0,1),(1,1)):
            subprocess.run(['g++','-std=c++17','-O1','-Wall','-Wextra','-Werror',
                            f'-DTEST_HOME_OFFSET={offsets}',f'-DTEST_WORKSPACE_OFFSET={offsets}',
                            f'-DTEST_LEVELING_AFTER_G28={after_home}',
                            str(source),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)


if __name__ == '__main__':
    main()
