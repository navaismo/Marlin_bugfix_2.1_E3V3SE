// Host lifecycle tests: no hardware operations occur in this executable.
#include "mock_marlin.h"
#include "feature/resonance/resonance_generator.h"
#include "feature/resonance/resonance_host_events.h"

#ifndef TEST_STANDARD
  #define TEST_STANDARD 0
#endif
#define TEST_FTM_ACTIVE (FT_MOTION && !TEST_STANDARD)

millis_t now_ms=0;
MockSerial singleSerial;
MultiSerial multiSerial;
std::string output;
std::function<void()> serial_hook;
std::vector<int> output_ports;
Planner planner;
Motion motion;
Marlin marlin;
Stepper stepper;
FTMotion ftMotion;
UI ui;
Parser parser;
GcodeSuite gcode;
bool EmergencyParser::rt_stop_by_M496=false;

static void command(const char *line) {
  parser.parse(line);
  if (TERN0(PINPUT_RESONANCE_EVENTS, resonance_host_events::reject_command())) return;
  GcodeSuite::M495();
}
static void clear_output() { output.clear(); output_ports.clear(); }
static size_t count(const char *str) {
  size_t n=0, pos=0;
  while ((pos=output.find(str,pos))!=std::string::npos) {++n;pos+=strlen(str);}
  return n;
}
static void poll() { TERN_(PINPUT_RESONANCE_EVENTS, resonance_host_events::idle()); }
#if PINPUT_RESONANCE_EVENTS
static void finish_cancel() {
  #if !TEST_FTM_ACTIVE && PINPUT_RESONANCE_EVENTS
    // Model the ISR reaching the next block boundary after its last pulse.
    if (rtg.isActive() && resonance_host_events::stop_requested()) {
      assert(rtg.generate_resonance_block()==nullptr);
      rtg.abort();
    }
  #endif
  poll();
}
#endif
static void exhaust() {
  // Emulate the native consumers: the standard ISR calls abort after nullptr;
  // FTMotion::loop calls abort on its next pass after done. No serial in either.
  #if TEST_FTM_ACTIVE
    ftMotion.stepping.current=true; // Model the last dequeued frame still executing.
    while (!rtg.isDone()) {
      ftMotion.stepping.frames=0;
      rtg.fill_stepper_plan_buffer();
    }
  #else
    while (rtg.generate_resonance_block()) {}
  #endif
  rtg.abort();
}

int main() {
  ftMotion.cfg.active=TEST_FTM_ACTIVE;
  // No unsolicited startup events; ordinary report / M496 never home or move.
  poll(); assert(output.empty());
  command("M495"); GcodeSuite::M496();
  assert(!gcode.homes && !motion.position_calls && !count("PIS:RT"));
  clear_output();

  #if PINPUT_RESONANCE_EVENTS
    // A capability query is read-only, including an accidentally appended S.
    const float old_freq=rtg.rt_params.min_freq;
    command("M495 Q");
    assert(output=="echo:PIS:RT:READY:1\n");
    command("M495 Q X S I22 F30");
    assert(count("ERROR:0:INVALID_PARAMETERS")==1);
    assert(!gcode.homes && !motion.position_calls && !rtg.isActive());
    assert(rtg.rt_params.min_freq==old_freq);

    const char *bad_ids[]={"M495 X S I", "M495 X S I0", "M495 X S I01",
      "M495 X S I-1", "M495 X S I+1", "M495 X S I1.0", "M495 X S I1e2",
      "M495 X S I4294967296", "M495 X S I99999999999999999999999999",
      "M495 X S I1 I2", "M495 X S I1X", "M495 X S I 1", "M495 X S I\"1\""};
    for (const char *line:bad_ids) {
      clear_output();command(line);
      assert(output=="echo:PIS:RT:ERROR:0:INVALID_SESSION_ID\n");
      assert(!rtg.isActive() && !gcode.homes);
    }
    const char *bad_parameters[]={"M495 X I10", "M495 X Y S I10", "M495 S I10",
      "M495 X S I10 F4", "M495 X S I10 F40 T30", "M495 X S I10 T201",
      "M495 X S I10 O19", "M495 X S I10 O61", "M495 X S I10 A-1",
      "M495 X S I10 A99999999999999999999999999999999999999999999999999",
      "M495 X S I10 C1.5", "M495 X S I10 C9", "M495 X S I10 F",
      "M495 X S I10 F20.3.4", "M495 X S I10 G10"};
    for (const char *line:bad_parameters) {
      clear_output();command(line);
      assert(output=="echo:PIS:RT:ERROR:10:INVALID_PARAMETERS\n");
      assert(!rtg.isActive() && !gcode.homes);
    }

    // An M496 received with no session cannot poison a later accepted request.
    EmergencyParser::rt_stop_by_M496=true;
    poll();assert(!EmergencyParser::rt_stop_by_M496);

    // Capture exact ordering: neither blocking preparation stage can see START.
    clear_output();
    gcode.homing=[] { assert(!count("PIS:RT:START")); };
    motion.positioning=[] { assert(!count("PIS:RT:START")); };
    multiSerial.portMask=SerialMask(2);
    command("M495 X F20 T20.1 O20 A40 I4294967295 S");
    assert(rtg.isActive() && gcode.homes==1 && motion.position_calls==1);
    assert(count("echo:PIS:RT:START:4294967295:X:20.00:20.10\n")==1);
    const auto before_busy=rtg.rt_params;
    command("M495 Y F30 I4294967295 S");
    assert(count("Error:TEST_BUSY")==1 && !count("PIS:RT:ERROR:4294967295:"));
    command("M495 Y F30 I33 S");
    assert(count("ERROR:33:TEST_BUSY")==1);
    command("M495 Y F30");
    assert(rtg.rt_params.axis==before_busy.axis && rtg.rt_params.min_freq==before_busy.min_freq);
    assert(gcode.homes==1);
    gcode.homing=nullptr;motion.positioning=nullptr;
    clear_output();
    multiSerial.portMask=SerialMask(4);
    exhaust();
    assert(!count("PIS:RT")); // abort hook never prints, even at natural exhaustion
    #if TEST_FTM_ACTIVE
      assert(rtg.isActive());
      poll();assert(!count("COMPLETE"));
      ftMotion.stepping.frames=0;ftMotion.stepping.current=true;
      rtg.abort();poll();assert(rtg.isActive() && !count("COMPLETE"));
      ftMotion.stepping.current=false;
      ftMotion.stepping.step_bits=true; // Final pulse may be scheduled at frame end.
      rtg.abort();poll();assert(rtg.isActive() && !count("COMPLETE"));
      ftMotion.stepping.step_bits=false;
      rtg.abort();
    #endif
    assert(!rtg.isActive());
    poll();poll();GcodeSuite::M496();poll();
    assert(count("echo:PIS:RT:COMPLETE:4294967295\n")==1);
    assert(!count("ABORTED"));
    #if HAS_MULTI_SERIAL
      // Event output returns to its originating port and restores the caller's.
      assert(output_ports[0]==2 && multiSerial.portMask.mask==4);
    #endif

    // Repeated sessions, emergency cancellation, direct cancellation, no duplicates.
    for (int i=1;i<=3;++i) {
      clear_output();command("M495 Y F20 T20.1 O20 A40 I123 S");
      assert(rtg.isActive() && count("START:123:Y")==1);
      if (i==1) {EmergencyParser::rt_stop_by_M496=true;poll();}
      else {GcodeSuite::M496();GcodeSuite::M496();poll();}
      #if !TEST_FTM_ACTIVE
        assert(rtg.isActive() && !count("ABORTED"));
      #endif
      finish_cancel();
      assert(!rtg.isActive() && !EmergencyParser::rt_stop_by_M496);
      poll();assert(count("ABORTED:123")==1 && !count("COMPLETE"));
    }

    // Cancel after generating the final point but before the FT buffer drains.
    #if TEST_FTM_ACTIVE
      clear_output();command("M495 X F20 T20.1 I21 S");exhaust();
      assert(rtg.isActive() && rtg.isDone());
      GcodeSuite::M496();poll();
      assert(count("ABORTED:21")==1 && !count("COMPLETE"));
      assert(!rtg.isActive() && !ftMotion.stepping.is_busy());
    #endif

    // Preparation cancellation waits for synchronous homing / positioning return.
    clear_output();
    const int old_positions=motion.position_calls;
    gcode.homing=[] {
      EmergencyParser::rt_stop_by_M496=true;poll();
      assert(!count("ABORTED") && !count("START"));
    };
    command("M495 X F20 T20.1 I45 S");
    assert(count("ABORTED:45")==1 && !count("START") && !rtg.isActive());
    assert(motion.position_calls==old_positions);
    gcode.homing=nullptr;
    clear_output();
    motion.positioning=[] {EmergencyParser::rt_stop_by_M496=true;poll();assert(!count("ABORTED"));};
    command("M495 X F20 T20.1 I46 S");
    assert(count("ABORTED:46")==1 && !count("START") && !rtg.isActive());
    motion.positioning=nullptr;

    // Real observable failures: untrusted axes after G28, and a recoverable stop.
    clear_output();motion.trusted=false;
    command("M495 X F20 T20.1 I50 S");
    assert(count("ERROR:50:AXIS_NOT_HOMED")==1 && !count("START") && !rtg.isActive());
    motion.trusted=true;marlin.running=false;clear_output();
    command("M495 X F20 T20.1 I51 S");
    assert(count("ERROR:51:MOTION_FAILED")==1 && !count("START") && !rtg.isActive());
    marlin.running=true;clear_output();command("M495 X F20 T20.1 I52 S");
    marlin.running=false;poll();finish_cancel();poll();
    assert(count("ERROR:52:MOTION_FAILED")==1 && !count("COMPLETE") && !count("ABORTED"));
    marlin.running=true;

    // v2 negotiation does not change Q or any v1 lifecycle.
    clear_output();command("M495 Q2");
    assert(output=="echo:PIS:RT:READY:2\n");
    for (const char *query : {"M495 Q3", "M495 Q2 S", "M495 Q2.0", "M495 Q02"}) {
      clear_output();command(query);assert(count("ERROR:0:INVALID_PARAMETERS")==1);
    }
    for (const char *bad : {"M495 X S W", "M495 X S W1 I70", "M495 I70 R S", "M495 I70 R1"}) {
      clear_output();const int homes=gcode.homes;command(bad);
      assert(!rtg.isActive() && gcode.homes==homes && !count("ARM_ACK"));
    }

    // Preparation can take longer than 30 s: the arming deadline starts AFTER it.
    clear_output();now_ms=100;
    gcode.homing=[] {now_ms+=60000;assert(!count("ARMED_WAIT") && !count("START"));};
    motion.positioning=[] {now_ms+=60000;assert(!count("ARMED_WAIT") && !count("START"));};
    multiSerial.portMask=SerialMask(2);
    command("M495 X F20 T20.1 O20 A40 I70 S W");
    assert(!rtg.isActive() && count("HOMED:70:60100")==1 && count("ARMED_WAIT:70")==1);
    gcode.homing=nullptr;motion.positioning=nullptr;
    const auto prepared_params=rtg.rt_params;
    for (const char *conflict : {"G1 X30", "G28", "G92 X0", "M84", "M493 S0", "M501", "T0"}) {
      parser.parse(conflict);assert(resonance_host_events::reject_command());
      assert(!rtg.isActive() && rtg.rt_params.min_freq==prepared_params.min_freq);
    }
    for (const char *status : {"M105", "M114", "M118 fence", "M496", "M495 Q2"}) {
      parser.parse(status);assert(!resonance_host_events::reject_command());
    }
    clear_output();command("M495 I71 R");
    assert(count("ARM_REJECTED:71:SESSION_MISMATCH")==1 && !count("ARM_ACK") && !rtg.isActive());
    #if HAS_MULTI_SERIAL
      multiSerial.portMask=SerialMask(4);command("M495 I70 R");
      assert(count("ARM_REJECTED:70:PORT_MISMATCH")==1 && !count("ARM_ACK") && !rtg.isActive());
      multiSerial.portMask=SerialMask(2);
    #endif
    now_ms+=29000;poll();assert(!rtg.isActive() && !count("ARM_TIMEOUT"));
    clear_output();command("M495 I70 R");
    assert(rtg.isActive() && count("ARM_ACK:70")==1 && count("START:70:")==1);
    assert(output.find("ARM_ACK:70")<output.find("START:70:"));
    command("M495 I70 R");
    assert(count("ARM_ACK:70")==2 && count("START:70:")==1);
    GcodeSuite::M496();finish_cancel();
    assert(count("ABORTED:70")==1);
    clear_output();command("M495 I70 R");
    assert(!rtg.isActive() && !count("ARM_ACK") && !count("START"));

    // Full v2 completion preserves the existing standard/FT terminal drain rules.
    command("M495 X F20 T20.1 O20 A40 I71 S W");command("M495 I71 R");
    assert(rtg.isActive());exhaust();
    #if TEST_FTM_ACTIVE
      ftMotion.stepping.frames=0;ftMotion.stepping.current=false;ftMotion.stepping.step_bits=false;rtg.abort();
    #endif
    poll();assert(!rtg.isActive() && count("COMPLETE:71")==1);

    // Late ARM cannot race a deadline that idle() has not checked yet, including wrap.
    for (const millis_t begin : {millis_t(100), millis_t(UINT32_MAX-20000)}) {
      clear_output();now_ms=begin;command("M495 X F20 T20.1 I72 S W");
      now_ms+=30000;command("M495 I72 R");
      assert(count("ERROR:72:ARM_TIMEOUT")==1 && !count("ARM_ACK") && !count("START") && !rtg.isActive());
      poll();command("M495 I72 R");assert(count("ERROR:72:ARM_TIMEOUT")==1 && !rtg.isActive());
    }
    clear_output();command("M495 X F20 T20.1 I73 S W");now_ms+=30000;poll();poll();
    assert(count("ERROR:73:ARM_TIMEOUT")==1 && !count("START") && !rtg.isActive());

    // Every prerequisite is validated BEFORE authorization is acknowledged.
    for (int failure=0;failure<6;++failure) {
      clear_output();command("M495 X F20 T20.1 I74 S W");
      if (failure==0) EmergencyParser::rt_stop_by_M496=true;
      if (failure==1) marlin.running=false;
      if (failure==2) motion.trusted=false;
      if (failure==3) planner.queued=true;
      if (failure==4) motion.position[0]+=1;
      if (failure==5) {GcodeSuite::M496();GcodeSuite::M496();}
      command("M495 I74 R");
      assert(!count("ARM_ACK") && !count("START") && !rtg.isActive());
      assert(count("ABORTED:74")+count("ERROR:74:")==1);
      marlin.running=true;motion.trusted=true;planner.queued=false;
    }
    // An emergency arriving during ACK/START serial emission still wins activation.
    for (const char *boundary : {"ARM_ACK:75", "START:75:"}) {
      clear_output();command("M495 X F20 T20.1 I75 S W");
      serial_hook=[boundary] {if (output.find(boundary)!=std::string::npos) EmergencyParser::rt_stop_by_M496=true;};
      command("M495 I75 R");serial_hook=nullptr;poll();
      assert(!rtg.isActive() && count("ABORTED:75")==1 && !count("COMPLETE"));
    }
    // A direct UI cancellation may run inside a serial helper's nested idle.
    for (const char *boundary : {"ARM_ACK:76", "START:76:"}) {
      clear_output();command("M495 X F20 T20.1 I76 S W");
      bool cancelled_in_output=false;
      serial_hook=[boundary, &cancelled_in_output] {
        if (!cancelled_in_output && output.find(boundary)!=std::string::npos) {
          cancelled_in_output=true;
          GcodeSuite::M496();
        }
      };
      command("M495 I76 R");serial_hook=nullptr;poll();
      assert(!rtg.isActive() && count("ABORTED:76")==1 && !count("COMPLETE"));
    }
    // A reset/reconnect cannot revive a terminated authorization.
    clear_output();command("M495 I75 R");assert(!count("START") && !rtg.isActive());

    #if PINPUT_RESONANCE_PROGRESS
      clear_output();now_ms=100;
      command("M495 X F20 T21 I60 S");
      poll();assert(!count("PROGRESS"));
      now_ms=1100;singleSerial.free=0;poll();assert(!count("PROGRESS"));
      now_ms=2100;singleSerial.free=64;poll();
      #if HAS_MULTI_SERIAL
        assert(!count("PROGRESS")); // Wrapper has no capacity API: skip safely.
      #else
        assert(count("PROGRESS:60:20.00")==1);
        poll();assert(count("PROGRESS")==1);
      #endif
      GcodeSuite::M496();poll();
      const size_t progress_count=count("PROGRESS");
      now_ms+=5000;poll();assert(count("PROGRESS")==progress_count);
    #endif
  #endif

  // Existing non-instrumented commands retain their native semantics in all builds.
  clear_output();command("M495 X F20 T20.1 O20 A40 S");
  assert(rtg.isActive() && !count("PIS:RT"));
  exhaust();
  assert(!rtg.isActive()); // Legacy FT still resets immediately, even if buffered.
  poll();GcodeSuite::M496();assert(!count("PIS:RT"));
  command("M495 X F20 T60 O20 A40 S");
  assert(rtg.isActive());GcodeSuite::M496();assert(!rtg.isActive() && !count("PIS:RT"));
  #if !PINPUT_RESONANCE_EVENTS
    clear_output();command("M495 Q");assert(!count("PIS:RT") && !rtg.isActive());
  #endif
}
