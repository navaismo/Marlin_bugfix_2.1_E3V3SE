#!/usr/bin/env python3
"""Replay the cube's spiral hop with production arc, PLR and leveling code."""
from pathlib import Path
import subprocess
import tempfile
import test_plr_leveling as leveling

ROOT = leveling.ROOT
replace_once = leveling.replace_once


def harness():
    source = leveling.harness()
    source = replace_once(source, 'void reset(){x=y=z=e=0;}', r'''
 void reset(){x=y=z=e=0;}
 float &operator[](int i){switch(i){case 0:return x;case 1:return y;case 2:return z;default:return e;}}
 const float &operator[](int i)const{return const_cast<Position*>(this)->operator[](i);}
''')
    source = replace_once(source, 'struct Motion {', r'''
enum AxisEnum { X_AXIS,Y_AXIS,Z_AXIS,E_AXIS };
struct PlannerHints {float safe_exit_speed_sqr=0,curve_radius=0;};
struct ab_float_t {
 float a,b;
 ab_float_t operator-()const{return {-a,-b};}
 float operator[](int i)const{return i?b:a;}
};
std::vector<Position> arc_points;
Position buffered_position;
uint32_t arc_sdpos=7000;
size_t capture_limit=7;
struct Motion {
 int extruder=0;
 float mms_scaled(){return 200;}
 void apply_limits(Position &){}
''')
    source = replace_once(source, 'struct Planner {', r'''
struct Planner {
 struct {float max_acceleration_mm_per_s2[4]={3000,3000,500,3000};
         float max_feedrate_mm_s[4]={500,500,10,40};} settings;
 bool buffer_line(const Position &target,float,int,const PlannerHints &){
  if(arc_points.size()<capture_limit)PrintJobRecovery::capture_block(arc_sdpos,buffered_position);
  arc_points.push_back(target);buffered_position=target;return true;
 }
''')
    source = replace_once(source, 'bool allow_cold_extrude=false;', 'void task(){}\n bool allow_cold_extrude=false;')
    source = replace_once(source, 'struct Gcode {', 'struct Gcode {\n void G0_G1(){}')
    return source + r'''
#define CNC_WORKSPACE_PLANES 0
#define HAS_Z_AXIS 1
#define HAS_EXTRUDERS 1
#define ARC_P_CIRCLES 0
#define ARC_SEGMENTS_PER_SEC 0
#define MIN_ARC_SEGMENT_MM 1
#define MAX_ARC_SEGMENT_MM 1
#define MIN_CIRCLE_SEGMENTS 24
#define N_ARC_CORRECTION 25
#define FEEDRATE_SCALING 0
#define PLANNER_LEVELING 1
#define OPTARG(V,...) , __VA_ARGS__
#define ARC_LIJKUVWE_CODE(L,I,J,K,U,V,W,E) L;E
#define GANG_N(N,L,...) L
#define SUB2(N) 1
#define NEAR(A,B) (fabs((A)-(B))<0.0001f)
#define NEAR_ZERO(A) (fabs(A)<0.0001f)
#define HYPOT(A,B) hypotf(A,B)
#define ATAN2(A,B) atan2f(A,B)
#define RADIANS(A) ((A)*3.14159265358979323846f/180)
#define CEIL(A) ceilf(A)
#define FLOOR(A) floorf(A)
#define sq(A) ((A)*(A))
#define ELAPSED(A,B) ((A)>=(B))
#undef _MIN
template<class...T>float arc_min(T...v){return std::min({float(v)...});}
#define _MIN(...) arc_min(__VA_ARGS__)
using feedRate_t=float;
millis_t millis(){return 0;}
struct {void idle(){}} marlin;
'''


TESTS = r'''
int main(){
 (void)print_job_timer;
 // Cube_PETG_8m42s.gcode lines 971..987: previous layer ends here,
 // then G92 E0 / G1 E-1.9 / G3 Z2.8 I-2.24 J.951 P1 F12000.
 const Position start={110.988f,104.777f,1.8f,-1.9f};
 const Position target={start.x,start.y,2.8f,start.e};
 const ab_float_t ij={-2.24f,0.951f};
 motion.position=start;buffered_position=start;
 PrintJobRecovery::init();
 plan_arc(target,ij,false,0); // ARC_P_CIRCLES is disabled in the C13 profile.
 const auto original=arc_points;
 const auto saved=PrintJobRecovery::info;
 assert(original.size()>capture_limit);
 assert(fabs(saved.current_position.x-start.x)>1);
 assert(saved.current_position.z>start.z && saved.current_position.z<target.z);
 assert(saved.command_start_position.x==start.x && saved.command_start_position.e==start.e);
 // Boot with the physical Z still at the intermediate segment. The return
 // must establish Z from that segment, then go back to the whole arc's start.
 physical_position=saved.current_position;z_counter_origin=-physical_position.z;
 motion.position={};PrintJobRecovery::info=saved;
 PrintJobRecovery::resume();
 assert(fabs(motion.position.x-start.x)<0.001f && fabs(motion.position.y-start.y)<0.001f);
 assert(fabs(physical_position.z-start.z)<0.001f && fabs(extruder_origin-start.e)<0.001f);
 // No XY words in the G3: its destination XY is the current position.
 const Position replay_target={motion.position.x,motion.position.y,target.z,motion.position.e};
 buffered_position=motion.position;arc_points.clear();capture_limit=0;
 plan_arc(replay_target,ij,false,0);
 assert(arc_points.size()==original.size());
 for(size_t i=0;i<original.size();++i){
  assert(fabs(arc_points[i].x-original[i].x)<0.001f);
  assert(fabs(arc_points[i].y-original[i].y)<0.001f);
  assert(fabs(arc_points[i].z-original[i].z)<0.001f);
  assert(fabs(arc_points[i].e-original[i].e)<0.001f);
 }
 std::cout<<"PASS cube spiral hop: intermediate checkpoint, independent physical Z, original IJ center and all "<<original.size()<<" replayed arc segments\n";
}
'''


def main():
    source = leveling.checkpoint.SOURCE
    planner = (ROOT/'Marlin/src/module/planner.cpp').read_text()
    bed = (ROOT/'Marlin/src/feature/bedlevel/bedlevel.cpp').read_text()
    arcs = (ROOT/'Marlin/src/gcode/motion/G2_G3.cpp').read_text()
    function = leveling.checkpoint.common.function
    functions = '\n'.join(function(source,p) for p in (
        'void PrintJobRecovery::init()', 'void PrintJobRecovery::capture_block(',
        'void PrintJobRecovery::resume()'))
    functions += '\n'.join(function(planner,p) for p in (
        'void Planner::apply_leveling(', 'void Planner::unapply_leveling('))
    functions += function(bed,'void set_bed_leveling_enabled(')
    functions += function(arcs,'void plan_arc(')
    with tempfile.TemporaryDirectory(prefix='plr-arc-') as folder:
        cpp,binary=Path(folder)/'test.cpp',Path(folder)/'test'
        cpp.write_text(harness()+functions+TESTS)
        subprocess.run(['g++','-std=c++17','-O1','-Wall','-Wextra','-Werror',
                        '-DTEST_HOME_OFFSET=0','-DTEST_WORKSPACE_OFFSET=0',
                        '-DTEST_LEVELING_AFTER_G28=1',str(cpp),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)


if __name__ == '__main__':
    main()
