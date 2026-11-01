#!/usr/bin/env python3
"""Exercise the migrated production scale, command handlers, M73 and plugin protocol."""
import argparse
import ast
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'Marlin/src/e3v3se/bed_scale'


def without_includes(text):
    return re.sub(r'^\s*#(?:include|pragma)[^\n]*', '', text, flags=re.M)


def function(text, name):
    start = text.index(name)
    brace = text.index('{', start)
    pos, depth = brace + 1, 1
    while depth:
        depth += (text[pos] == '{') - (text[pos] == '}')
        pos += 1
    return text[start:pos]


COMMON = r'''
#include <cassert>
#include <cstdint>
#include <cmath>
#include <deque>
#include <iomanip>
#include <sstream>
#include <string>
#include <map>
#include <vector>
#include "Marlin/src/core/macros.h"
#define BED_SCALE 1
#define USE_AUTOZ_TOOL_2 1
#define SET_PROGRESS_MANUALLY 1
std::ostringstream serial;
template<class T> void echo(T v) { serial << v; }
void echo(float v, int n) { serial << std::fixed << std::setprecision(n) << v; }
#define SERIAL_ECHO(...) echo(__VA_ARGS__)
#define SERIAL_ECHOPGM(...) echo(__VA_ARGS__)
#define SERIAL_ECHOLN(...) do { echo(__VA_ARGS__); serial << '\n'; } while (0)
#define SERIAL_ECHOLNPGM(...) SERIAL_ECHOLN(__VA_ARGS__)
#define PSTR(s) s
struct Queue { std::string injected; void inject_P(const char *s) { injected=s; } } queue;
struct xyz_long_t { int32_t x, y, z; };
std::deque<int32_t> readings;
struct HX711 { void init(int, int) {} };
struct ProbeAcq {
  HX711 hx711;
  xyz_long_t readBase(bool reject) {
    assert(reject && !readings.empty());
    int32_t v=readings.front(); readings.pop_front(); return {v,v,v};
  }
};
#define HX711_SCK_PIN 4
#define HX711_SDO_PIN 6
struct Parser {
  std::map<char,float> args; char current;
  bool seen(char c) { current=c; return args.count(c); }
  bool seenval(char c) { return seen(c); }
  uint8_t byteval(char c, int fallback=0) { return args.count(c) ? args[c] : fallback; }
  float floatval(char c) { return args[c]; }
  int32_t value_int() { return args[current]; }
} parser;
struct UI { int layer=0; void set_current_layer(int n) { layer=n; } } ui;
struct GcodeSuite { static void M770(); static void M771(); static void M772(); static void M73(); };
'''

MAIN = r'''
int main() {
  // Production command parsing and protocol. Calibration is intentionally RAM-only.
  readings={100000}; parser.args={{'A',1}}; GcodeSuite::M771();
  assert(bed_scale.offset_raw==100000 && serial.str()=="BS TARE ok offset_raw=100000\n");
  readings={91000}; parser.args={{'I',1},{'S',640},{'A',1}}; GcodeSuite::M772();
  readings={82000}; parser.args={{'I',2},{'S',1280},{'A',1}}; GcodeSuite::M772();
  assert(std::abs(bed_scale_estimate_grams_from_delta(-4500)-320)<0.001f);
  assert(bed_scale_estimate_grams_from_delta(10)==0);
  assert(bed_scale_estimate_grams_from_delta(-20000)==1280);
  serial.str(""); readings={86500}; parser.args={{'A',1}}; GcodeSuite::M770();
  assert(serial.str()=="BS raw=86500 offset=100000 delta=-13500 g_est=960.00\n");
  parser.args={{'I',4},{'S',99}}; GcodeSuite::M772(); // No acquisition for invalid point.
  assert(readings.empty());
  readings={100000}; bed_scale_tare(1);
  readings={91000,91900,92800};
  parser.args={{'L',4}}; GcodeSuite::M73();
  parser.args={{'L',5}}; GcodeSuite::M73();
  serial.str(""); parser.args={{'L',6}}; GcodeSuite::M73();
  assert(serial.str().find("BedScale L6 delta=-7200 g_est=512.00\n")!=std::string::npos);
  assert(serial.str().find("BedScale Object drop detected - Pause requested\n")!=std::string::npos);
#if ENABLED(OCTOPRINT_PLUGIN)
  assert(serial.str().find("M9000 pause-job-bs\n")!=std::string::npos);
  assert(queue.injected.empty());
#else
  assert(queue.injected=="M25");
  assert(serial.str().find("M9000")==std::string::npos);
#endif
#if ENABLED(DWIN_RENDER_THUMBNAIL)
  assert(ui.layer==6);
#endif
  // Timeouts must neither change the tare/calibration nor report a weight/drop.
  auto previous=bed_scale.offset_raw;
  readings={INT32_MIN}; bed_scale_tare(1); assert(bed_scale.offset_raw==previous);
  readings={INT32_MIN}; assert(!bed_scale_set_point(3,100,1));
  serial.str(""); readings={INT32_MIN}; GcodeSuite::M770();
  assert(serial.str()=="BS raw=INVALID\n");
  serial.str(""); readings={INT32_MIN}; GcodeSuite::M73(); assert(serial.str().empty());
  readings={100000,INT32_MIN}; assert(bed_scale_read_raw_avg(2)==INT32_MIN);
  assert(readings.empty());
  serial.str(""); parser.args={{'P',50}}; GcodeSuite::M73(); assert(serial.str().empty());
  // Preserve the existing duplicate-layer and first-three-layers policies.
  bed_scale.have_last_g=false;
  assert(!bed_scale_check_drop_and_pause(1,640));
  assert(!bed_scale_check_drop_and_pause(2,300));
  assert(bed_scale.drop_hits==0);
  assert(!bed_scale_check_drop_and_pause(2,250));
  assert(bed_scale.last_g_est==250);
}
'''


def run_cpp(text, defines=()):
    with tempfile.TemporaryDirectory() as tmp:
        src, exe = Path(tmp)/'test.cpp', Path(tmp)/'test'
        src.write_text(text)
        subprocess.run(['g++', '-std=c++17', '-I', str(ROOT), *defines,
                        str(src), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


def acquisition_checks():
    source = (ROOT/'Marlin/src/e3v3se/AutoOffset.cpp').read_text()
    # Exercise the real filter acquisition loop with controlled ADC samples.
    stubs = COMMON[:COMMON.index('struct HX711')] + r'''
#define PI_COUNT 32
#define LFILTER_K1_NEW 0.9
#define FOR_LOOP_TIMES(i,a,b,...) for (int i=a; i<b; ++i) { __VA_ARGS__; }
#define ARY_MIN(out,a,n) for(int i=0;i<n;++i) if(a[i]<out) out=a[i]
#define ARY_MAX(out,a,n) for(int i=0;i<n;++i) if(a[i]>out) out=a[i]
#define ARY_AVG(out,a,n) do { for(int i=0;i<n;++i) out+=a[i]; out/=n; } while(0)
struct HX711 {
 int getVal(bool, bool) { assert(!readings.empty()); int v=readings.front(); readings.pop_front(); return v; }
};
struct ProbeAcq { HX711 hx711; xyz_long_t readBase(bool=false); };
struct Filters { static void tFilter(double*,int); static void lFilter(double*,int,double); };
'''
    funcs = '\n'.join(function(source, n) for n in (
        'void Filters::tFilter(', 'void Filters::lFilter(', 'xyz_long_t ProbeAcq::readBase('))
    run_cpp(stubs + funcs + r'''
int main() {
 ProbeAcq cell;
 readings=std::deque<int32_t>(32,1000); assert(cell.readBase(true).y==1000); assert(readings.empty());
 for(int at : {0,15,16,31}) {
   readings=std::deque<int32_t>(32,1000); readings[at]=INT32_MIN;
   assert(cell.readBase(true).y==INT32_MIN);
 }
 readings=std::deque<int32_t>(32,-1234); assert(cell.readBase().y==-1234);
}
''')
    # The real HX711 driver rejects a not-ready ADC only when explicitly requested.
    driver = COMMON[:COMMON.index('struct HX711')] + r'''
unsigned tick=0, critical_entries=0, idle_calls=0;
bool not_ready=true;
#define GPIO_GET_VAL(pin) (not_ready ? 1 : 0)
#define GPIO_SET_VAL(pin,value) do {} while(0)
#define GET_TICK_MS() tick
#define MARLIN_CORE_IDLE() do { ++tick; ++idle_calls; } while(0)
#define DISABLE_ALL_ISR() ++critical_entries
#define ENABLE_ALL_ISR() do {} while(0)
#define CHECK_AND_RUN(check,action) do { if(check) action; } while(0)
#define SERIAL_ECHOLNPGM_P(...) do {} while(0)
struct HX711 { int clkPin=4,sdoPin=6; int getVal(bool=false,bool=false); };
'''
    run_cpp(driver + function(source, 'int HX711::getVal(') + r'''
int main() {
 HX711 adc;
 assert(adc.getVal(false,true)==INT32_MIN);
 assert(idle_calls==21 && critical_entries==0);
 // The existing AutoOffset read still runs its original conversion after timeout.
 assert(adc.getVal()==-1 && critical_entries==1);
 not_ready=false;
 assert(adc.getVal(false,true)==0 && critical_entries==2);
}
''')


def plugin_checks(path):
    module = ast.parse(path.read_text())
    handler = next(n for n in ast.walk(module)
                   if isinstance(n, ast.FunctionDef) and n.name=='gcode_received_handler')
    namespace = {}
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(path), 'exec'), namespace)
    printer = Mock()
    printer.is_printing.return_value = True
    plugin = SimpleNamespace(_printer=printer, _plugin_logger=Mock(), bedscale_warn=False)
    namespace['gcode_received_handler'](plugin, None, 'M9000 pause-job-bs')
    printer.pause_print.assert_called_once()
    assert plugin.bedscale_warn, 'Bed Scale pause must enable its specific warning before pausing'
    print('Plugin: pause accepted and Bed Scale warning enabled')


def build_option_checks():
    workflow = (ROOT/'.github/workflows/build-marlin.yml').read_text()
    assert re.search(r'      bed_scale:\n(?:[^\n]*\n){2}        default: true', workflow)
    assert 'BED_SCALE=${{ inputs.bed_scale }}' in workflow
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder/'Marlin').mkdir()
        for header in ('Configuration.h','Configuration_adv.h'):
            (folder/'Marlin'/header).write_text((ROOT/'Marlin'/header).read_text())
        helper = ROOT/'.github/scripts/apply_marlin_options.py'
        for enabled in ('false','true'):
            subprocess.run(['python3',str(helper),f'BED_SCALE={enabled}'], cwd=folder,
                           check=True, capture_output=True)
            text = (folder/'Marlin/Configuration_adv.h').read_text()
            assert bool(re.search(r'^#define BED_SCALE\b',text,re.M)) == (enabled=='true')
            assert re.search(r'^#define USE_AUTOZ_TOOL_2\b',text,re.M)
            assert re.search(r'^#define OCTOPRINT_PLUGIN\b',
                             (folder/'Marlin/Configuration.h').read_text(),re.M)


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--plugin', type=Path)
    args = cli.parse_args()
    source = COMMON + '\n'.join(without_includes((BASE/p).read_text())
                               for p in ('bed_scale.h','bed_scale.cpp','M770_M772.cpp'))
    source += function((ROOT/'Marlin/src/gcode/lcd/M73.cpp').read_text(), 'void GcodeSuite::M73(')
    for host in (0,1):
        for thumbnail in (0,1):
            run_cpp(source + MAIN, [f'-DOCTOPRINT_PLUGIN={host}', f'-DDWIN_RENDER_THUMBNAIL={thumbnail}'])
    acquisition_checks()
    build_option_checks()
    if args.plugin:
        plugin_checks(args.plugin)
    print('Bed Scale: command/calibration/M73, host + SD, thumbnail on + off and acquisition checks passed')
