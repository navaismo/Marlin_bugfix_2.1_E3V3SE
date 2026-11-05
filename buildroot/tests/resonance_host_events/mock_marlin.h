// Host-only mocks. The compiled handler, generator, and protocol are production sources.
#pragma once
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

#define RESONANCE_TEST 1
#define HAS_STANDARD_MOTION 1
#define HAS_FTM_DIR_CHANGE_HOLD 0
#define GCODE_CASE_INSENSITIVE 1
#define MARLIN_SMALL_BUILD 0
#define ENABLED(V) V
#define DISABLED(V) (!(V))
#define JOIN_(A,B) A##B
#define JOIN(A,B) JOIN_(A,B)
#define TERN0_0(...) false
#define TERN0_1(...) __VA_ARGS__
#define TERN0(C,...) JOIN(TERN0_,C)(__VA_ARGS__)
#define TERN1_0(...) true
#define TERN1_1(...) __VA_ARGS__
#define TERN1(C,...) JOIN(TERN1_,C)(__VA_ARGS__)
#define TERN__0(...)
#define TERN__1(...) __VA_ARGS__
#define TERN_(C,...) JOIN(TERN__,C)(__VA_ARGS__)
#define WITHIN(V,L,H) ((V)>=(L) && (V)<=(H))
#define NUMERIC(C) WITHIN(C,'0','9')
#define NOMORE(V,M) do { if ((V)>(M)) (V)=(M); } while (0)
#define _MAX(A,B) ((A)>(B)?(A):(B))
#define sq(V) ((V)*(V))
#define F(V) (V)
#define C(V) char(V)
#define AXIS_CHAR(A) ("XYZE"[A])
#define LOOP_NUM_AXES(A) for (uint8_t A=0; A<3; ++A)
#define X_CENTER 100.0f
#define Y_CENTER 100.0f
#define Z_CLEARANCE_FOR_HOMING 10.0f
using std::isfinite;
using std::abs;
using FSTR_P = const char*;
using millis_t = uint32_t;
extern millis_t now_ms;
inline millis_t millis() { return now_ms; }
#define ELAPSED(N,T) (int32_t((N)-(T))>=0)
template<class T> struct Remember { T &ref; T old; Remember(T &r,T v):ref(r),old(r){r=v;} ~Remember(){ref=old;} };
#define REMEMBER(N,R,V) Remember<decltype(R)> N(R,V)

struct SerialMask {
  int mask;
  enum { All = 255 };
  SerialMask(int m): mask(m) {}
  bool enabled(SerialMask other) const { return mask & other.mask; }
};
struct MockSerial {
  int free = 64;
  int availableForWrite() { return free; }
};
struct MultiSerial { SerialMask portMask = SerialMask::All; }; // No TX capacity API
extern MockSerial singleSerial;
extern MultiSerial multiSerial;
#if HAS_MULTI_SERIAL
  #define SERIAL_IMPL multiSerial
  #define PORT_REDIRECT(P) REMEMBER(port, multiSerial.portMask, P)
#else
  #define SERIAL_IMPL singleSerial
#endif
extern std::string output;
extern std::vector<int> output_ports;
template<class T> void serial_one(T value) {
  std::ostringstream s; s << value; output += s.str();
  output_ports.push_back(multiSerial.portMask.mask);
}
struct p_float_t {
  float value; int digits;
  p_float_t(float v, int d): value(v), digits(d) {}
};
inline void SERIAL_CHAR(char c) {serial_one(c);}
inline void serial_one(p_float_t value) {
  float v=value.value; int digits=value.digits;
  std::ostringstream s; s << std::fixed << std::setprecision(digits) << v; serial_one(s.str());
}

inline void SERIAL_ECHO_START() { serial_one("echo:"); }
extern std::function<void()> serial_hook;
inline void SERIAL_EOL() { serial_one('\n'); if (serial_hook) serial_hook(); }
inline void SERIAL_ECHO() {}
template<class T,class... Rest> void SERIAL_ECHO(T v,Rest... rest) { serial_one(v); SERIAL_ECHO(rest...); }
template<class... Args> void SERIAL_ECHOLN(Args... args) { SERIAL_ECHO(args...); SERIAL_EOL(); }
#define SERIAL_ECHOLNPGM(...) SERIAL_ECHOLN(__VA_ARGS__)
#define SERIAL_ERROR_MSG(V) SERIAL_ECHOLN("Error:",V)

enum AxisEnum { NO_AXIS_ENUM=-1, X_AXIS, Y_AXIS, Z_AXIS, E_AXIS };
struct xyze_pos_t {
  float data[4]{};
  float &operator[](int i) { assert(i>=0 && i<4); return data[i]; }
  const float &operator[](int i) const { assert(i>=0 && i<4); return data[i]; }
};
using xyze_float_t = xyze_pos_t;
struct block_t {
  uint32_t initial_rate=0, step_event_count=0, direction_bits=0, steps[4]{};
  void reset() { *this=block_t(); }
};
struct Planner {
  bool queued=false;
  bool has_blocks_queued() { return queued; }
  struct { float axis_steps_per_mm[4]={80,80,400,100}; } settings; };
extern Planner planner;
struct Motion {
  xyze_pos_t position;
  bool trusted = true;
  int position_calls = 0;
  std::function<void()> positioning;
  bool all_axes_trusted() { return trusted; }
  void blocking_move_xy(float x,float y,float) {
    ++position_calls;
    if (positioning) positioning();
    position[0]=x; position[1]=y;
  }
};
extern Motion motion;
struct Marlin { bool running=true; bool isRunning() {return running;} };
extern Marlin marlin;
struct Stepper {
  bool awake=true;
  bool suspend(){bool prev=awake;awake=false;return prev;}
  void wake_up(){awake=true;}
};
extern Stepper stepper;
struct EmergencyParser { static bool rt_stop_by_M496; };
struct UI { void refresh() {} };
extern UI ui;
struct FTMotion {
  struct { bool active=FT_MOTION; } cfg;
  struct {
    int frames=0;
    bool current=false, step_bits=false;
    bool is_full() {return frames>=4;}
    bool is_busy() {return frames || current;}
  } stepping;
  int resets=0;
  void reset(){++resets;stepping.frames=0;stepping.current=false;stepping.step_bits=false;}
  void stepping_enqueue(xyze_pos_t) {++stepping.frames;}
};
extern FTMotion ftMotion;

struct Parser {
  std::vector<char> storage;
  char command_letter='M';
  uint16_t codenum=495;
  char *command_ptr=nullptr, *value=nullptr;
  char *values[26]{};
  bool flags[26]{};
  void parse(const char *text) {
    storage.assign(text,text+strlen(text)+1);
    command_ptr=storage.data(); value=nullptr;
    memset(values,0,sizeof(values)); memset(flags,0,sizeof(flags));
    command_letter=*command_ptr;
    char *p;
    codenum=strtoul(command_ptr+1,&p,10);
    while (*p) {
      char c=*p++;
      if (c>='a' && c<='z') c+='A'-'a';
      if (c<'A' || c>'Z') continue;
      while (*p==' ') ++p;
      flags[c-'A']=true;
      if (NUMERIC(*p) || *p=='-' || *p=='+' || *p=='.') {
        values[c-'A']=p;
        while (NUMERIC(*p) || *p=='-' || *p=='+' || *p=='.') ++p;
      }
    }
  }
  bool seen_test(char c) { return flags[c-'A']; }
  bool seen(char c) { if (!seen_test(c)) return false; value=values[c-'A']; return true; }
  bool has_value() { return value; }
  bool seenval(char c) { return seen(c) && has_value(); }
  bool seen_any() { for (bool f:flags) if(f)return true; return false; }
  char *value_string() {return value;}
  float value_float() {return value?strtof(value,nullptr):0;}
  int value_int() {return int(value_float());}
};
extern Parser parser;
struct GcodeSuite {
  int homes=0;
  std::function<void()> homing;
  void home_all_axes() {++homes;if(homing)homing();}
  static void M495();
  static void M496();
};
extern GcodeSuite gcode;
