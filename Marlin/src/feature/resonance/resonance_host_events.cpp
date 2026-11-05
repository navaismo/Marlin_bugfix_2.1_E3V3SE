/**
 * Marlin 3D Printer Firmware
 * Copyright (c) 2026 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 *
 * Based on Sprinter and grbl.
 * Copyright (c) 2011 Camiel Gubbels / Erik van der Zalm
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 */
#include "../../inc/MarlinConfig.h"

#if ENABLED(PINPUT_RESONANCE_EVENTS)

#include "resonance_host_events.h"
#include "resonance_generator.h"
#include "../../MarlinCore.h"
#include "../../gcode/gcode.h"
#include "../../module/stepper.h"
#if ENABLED(FT_MOTION)
  #include "../../module/ft_motion.h"
#endif

namespace resonance_host_events {

  enum class Phase : uint8_t { Idle, Preparing, WaitingArm, ArmAccepted, Exciting, CompletePending, AbortPending };
  static volatile Phase phase = Phase::Idle;
  static volatile bool cancelled;
  static bool failed, reporting, host_arm;
  static millis_t arm_deadline_ms;
  static constexpr millis_t ARM_TIMEOUT_MS = 30000;
  #if ENABLED(PINPUT_RESONANCE_PROGRESS)
    static millis_t next_progress_ms;
  #endif
  static uint32_t session_id;
  #if HAS_MULTI_SERIAL
    static SerialMask session_port = SerialMask::All;
  #endif

  static void error(const uint32_t id, FSTR_P reason) {
    SERIAL_ECHO_START();
    SERIAL_ECHOLN(F("PIS:RT:ERROR:"), id, C(':'), reason);
  }

  static char upper(const char c) {
    return TERN0(GCODE_CASE_INSENSITIVE, WITHIN(c, 'a', 'z')) ? c - 'a' + 'A' : c;
  }

  // Inspect the original token, not value_ulong(): that would truncate fractions,
  // accept signs, lose leading zeroes, and wrap an oversized integer.
  static bool read_id(uint32_t &id) {
    const char *token = nullptr;
    for (const char *c = parser.command_ptr; *c; ++c) {
      if (upper(*c) != 'I') continue;
      if (token || c == parser.command_ptr || c[-1] != ' ') return false;
      token = c + 1;
    }
    if (!token || !WITHIN(*token, '1', '9')) return false;
    id = 0;
    do {
      const uint8_t digit = *token++ - '0';
      if (id > UINT32_MAX / 10 || (id == UINT32_MAX / 10 && digit > UINT32_MAX % 10)) return false;
      id = id * 10 + digit;
    } while (NUMERIC(*token));
    return !*token || *token == ' ';
  }

  static bool numeric(const char c, float &value) {
    if (!parser.seen(c)) return true;
    if (!parser.has_value()) return false;
    char *end;
    value = strtof(parser.value_string(), &end);
    return isfinite(value) && (!*end || *end == ' ' || WITHIN(upper(*end), 'A', 'Z'));
  }

  static void terminal(FSTR_P event);
  static bool arm_valid();

  static void arm_reply(const uint32_t id, FSTR_P reason=nullptr) {
    SERIAL_ECHO_START();
    SERIAL_ECHO(F("PIS:RT:"), reason ? F("ARM_REJECTED:") : F("ARM_ACK:"), id);
    if (reason) SERIAL_ECHO(C(':'), reason);
    SERIAL_EOL();
  }

  bool reject_command() {
    if (phase != Phase::WaitingArm && phase != Phase::ArmAccepted) return false;
    // Allow only lifecycle, transport, and read-only/reporting commands. Reject
    // before dispatch, including injected G-code, so the prepared state survives.
    if (parser.command_letter == 'M') switch (parser.codenum) {
      case 105: case 110: case 112: case 113: case 114: case 115:
      case 118: case 119: case 154: case 155: case 400: case 495: case 496: case 503:
        return false;
    }
    SERIAL_ERROR_MSG("PIS_ARM_WAIT");
    return true;
  }

  bool command() {
    REMEMBER(report, reporting, true);
    // Query takes precedence, even over S. It cannot reach configuration / motion.
    if (parser.seen_test('Q')) {
      for (char c = 'A'; c <= 'Z'; ++c)
        if (c != 'Q' && parser.seen_test(c)) {
          error(0, F("INVALID_PARAMETERS"));
          return true;
        }
      const bool v2 = parser.seenval('Q');
      // Only the canonical Q2 token opts into the new protocol. Q stays v1.
      if (v2 && (parser.value_string()[0] != '2'
          || (parser.value_string()[1] && parser.value_string()[1] != ' ')))
        error(0, F("INVALID_PARAMETERS"));
      else {
        SERIAL_ECHO_START();
        SERIAL_ECHOLN(F("PIS:RT:READY:"), v2 ? 2 : 1);
      }
      return true;
    }

    const bool instrumented = parser.seen_test('I');
    uint32_t id = 0;
    if (instrumented && !read_id(id)) {
      error(0, F("INVALID_SESSION_ID"));
      return true;
    }
    if (parser.seen_test('R')) {
      bool valid = instrumented && !parser.seenval('R');
      for (char c = 'A'; c <= 'Z'; ++c)
        if (parser.seen_test(c) && c != 'I' && c != 'R') valid = false;
      if (!valid) { arm_reply(id, F("INVALID_PARAMETERS")); return true; }
      #if HAS_MULTI_SERIAL
        for (uint8_t bit = 1; bit; bit <<= 1)
          if (session_port.enabled(SerialMask(bit)) != multiSerial.portMask.enabled(SerialMask(bit))) {
            arm_reply(id, F("PORT_MISMATCH"));
            return true;
          }
      #endif
      if (id != session_id) { arm_reply(id, F("SESSION_MISMATCH")); return true; }
      if (host_arm && phase == Phase::Exciting) {
        // Idempotent acknowledgment only; never regenerate or repeat START.
        if (!cancelled && !EmergencyParser::rt_stop_by_M496
            && marlin.isRunning() && motion.all_axes_trusted()) arm_reply(id);
        else arm_reply(id, F("NOT_WAITING"));
        return true;
      }
      if (!host_arm || phase != Phase::WaitingArm) { arm_reply(id, F("NOT_WAITING")); return true; }
      if (!arm_valid()) return true; // Terminal cancellation / timeout / state error.
      phase = Phase::ArmAccepted; // Consume the authorization before any serial output.
      arm_reply(id);
      if (phase == Phase::ArmAccepted)
        rtg.activate(); // Recheck cancellation/deadline after output, before publishing active.
      return true;
    }
    if (phase != Phase::Idle || (instrumented && rtg.isActive())) {
      // Replaying the active ID must not look like a terminal ERROR for that session.
      if (instrumented && (phase == Phase::Idle || id != session_id)) error(id, F("TEST_BUSY"));
      else SERIAL_ERROR_MSG("TEST_BUSY");
      return true; // Don't mutate settings of an active instrumented test.
    }
    if (!instrumented) {
      if (parser.seen_test('W')) { error(0, F("INVALID_PARAMETERS")); return true; }
      return false;
    }

    const resonance_test_params_t &p = rtg.rt_params;
    const uint8_t axes = parser.seen_test('X') + parser.seen_test('Y') + parser.seen_test('Z');
    float f = p.min_freq, t = p.max_freq, o = p.octave_duration,
          a = p.accel_per_hz, c = p.amplitude_correction;
    bool valid = parser.seen_test('S') && axes <= 1 && (axes || p.axis != NO_AXIS_ENUM);
    for (char key = 'A'; key <= 'Z'; ++key)
      if (parser.seen_test(key) && !strchr("ACFIOSTWXYZ", key)) valid = false;
    valid = !parser.seenval('W') && valid;
    valid = numeric('F', f) && numeric('T', t) && numeric('O', o)
         && numeric('A', a) && numeric('C', c) && valid;
    // Avoid non-finite values and overflow of the existing Q16 amplitude precalc.
    valid = valid && f >= 5 && t > f && t <= 200 && WITHIN(o, 20, 60)
         && a > 0 && WITHIN(c, 1, 8) && floorf(c) == c
         && (c * a * 0.25f) / sq(M_PI) < 32767.0f;
    if (!valid) {
      error(id, F("INVALID_PARAMETERS"));
      return true;
    }
    session_id = id;
    cancelled = failed = false;
    host_arm = parser.seen_test('W');
    #if HAS_MULTI_SERIAL
      session_port = multiSerial.portMask;
    #endif
    phase = Phase::Preparing;
    return false; // Let the native handler configure and start the sweep.
  }

  static void terminal(FSTR_P event) {
    REMEMBER(report, reporting, true);
    #if HAS_MULTI_SERIAL
      PORT_REDIRECT(session_port);
    #endif
    // Clear before serial output, which may service nested idle tasks on some HALs.
    const uint32_t id = session_id;
    phase = Phase::Idle;
    session_id = 0;
    host_arm = false;
    if (failed) error(id, F("MOTION_FAILED"));
    else {
      SERIAL_ECHO_START();
      SERIAL_ECHOLN(F("PIS:RT:"), event, C(':'), id);
    }
  }

  bool stop_requested() { return phase == Phase::Exciting && cancelled; }

  bool cancel() {
    if (phase == Phase::Idle) return false;
    EmergencyParser::rt_stop_by_M496 = false;
    if (phase == Phase::Preparing) {
      // G28 / blocking positioning must return before reporting a stopped session.
      cancelled = true;
    }
    else if (phase == Phase::WaitingArm || phase == Phase::ArmAccepted) {
      cancelled = true;
      rtg.reset(); // No test blocks or FT frames have been generated.
      terminal(F("ABORTED"));
    }
    else if (phase == Phase::Exciting) {
      const bool awake = stepper.suspend();
      if (phase == Phase::Exciting) { // The ISR may have completed before suspend().
        cancelled = true;
        // Standard motion stops at its next block boundary (current_block=nullptr),
        // avoiding a reset while the ISR still owns the synthetic resonance block.
        // FT Motion retains the native atomic reset of its stepping buffer.
        if (TERN0(FT_MOTION, ftMotion.cfg.active)) rtg.abort();
      }
      if (awake) stepper.wake_up();
    }
    return true;
  }

  bool prepared() {
    if (phase != Phase::Preparing) return true; // Legacy start
    if (EmergencyParser::rt_stop_by_M496) cancel();
    if (cancelled) {
      terminal(F("ABORTED"));
      return false;
    }
    FSTR_P reason = nullptr;
    if (!marlin.isRunning()) reason = F("MOTION_FAILED");
    else if (!motion.all_axes_trusted()) reason = F("AXIS_NOT_HOMED");
    if (reason) {
      #if HAS_MULTI_SERIAL
        PORT_REDIRECT(session_port);
      #endif
      const uint32_t id = session_id;
      phase = Phase::Idle;
      session_id = 0;
      error(id, reason);
      return false;
    }
    return true;
  }

  static void fail_wait(FSTR_P reason) {
    REMEMBER(report, reporting, true);
    #if HAS_MULTI_SERIAL
      PORT_REDIRECT(session_port);
    #endif
    const uint32_t id = session_id;
    phase = Phase::Idle;
    session_id = 0;
    host_arm = false;
    rtg.reset();
    error(id, reason);
  }

  static bool arm_valid() {
    if (EmergencyParser::rt_stop_by_M496 || cancelled) { cancel(); return false; }
    if (ELAPSED(millis(), arm_deadline_ms)) { fail_wait(F("ARM_TIMEOUT")); return false; }
    if (!marlin.isRunning()) { fail_wait(F("MOTION_FAILED")); return false; }
    if (!motion.all_axes_trusted()) { fail_wait(F("AXIS_NOT_HOMED")); return false; }
    bool changed = planner.has_blocks_queued();
    LOOP_NUM_AXES(axis)
      if (motion.position[axis] != rtg.rt_params.start_pos[axis]) changed = true;
    #if ENABLED(FT_MOTION)
      changed |= ftMotion.stepping.is_busy() || bool(ftMotion.stepping.step_bits);
    #endif
    if (changed) { fail_wait(F("PREPARED_STATE_CHANGED")); return false; }
    return true;
  }

  void homed() {
    if (!host_arm || phase != Phase::Preparing) return;
    REMEMBER(report, reporting, true);
    #if HAS_MULTI_SERIAL
      PORT_REDIRECT(session_port);
    #endif
    SERIAL_ECHO_START();
    SERIAL_ECHOLN(F("PIS:RT:HOMED:"), session_id, C(':'), millis());
  }

  bool wait_for_arm() {
    if (!host_arm || phase != Phase::Preparing) return false;
    REMEMBER(report, reporting, true);
    #if HAS_MULTI_SERIAL
      PORT_REDIRECT(session_port);
    #endif
    phase = Phase::WaitingArm;
    arm_deadline_ms = millis() + ARM_TIMEOUT_MS;
    SERIAL_ECHO_START();
    SERIAL_ECHOLN(F("PIS:RT:ARMED_WAIT:"), session_id);
    return true;
  }

  bool exciting() {
    if (phase == Phase::ArmAccepted) {
      if (!arm_valid()) return false;
    }
    else if (phase != Phase::Preparing) return phase == Phase::Idle;
    else if (host_arm) return false; // Never bypass the opt-in barrier.
    const Phase accepted_phase = phase;
    REMEMBER(report, reporting, true);
    #if ENABLED(PINPUT_RESONANCE_PROGRESS)
      next_progress_ms = millis() + 1000;
    #endif
    #if HAS_MULTI_SERIAL
      PORT_REDIRECT(session_port);
    #endif
    SERIAL_ECHO_START();
    SERIAL_ECHO(F("PIS:RT:START:"), session_id, C(':'), C(AXIS_CHAR(rtg.rt_params.axis)), C(':'));
    SERIAL_ECHO(p_float_t(rtg.rt_params.min_freq, 2));
    SERIAL_CHAR(':');
    SERIAL_ECHO(p_float_t(rtg.rt_params.max_freq, 2));
    SERIAL_EOL();
    // Serial helpers may service nested idle tasks. An emergency M496 received
    // while emitting ACK/START must still win before the generator is active.
    if (phase != accepted_phase || (host_arm && !arm_valid())) return false;
    phase = Phase::Exciting;
    return true;
  }

  bool stopping(const bool done) {
    if (phase != Phase::Exciting) return true;
    #if ENABLED(FT_MOTION)
      // Native FTMotion::loop calls abort again on each idle pass while done.
      // A final pulse can be scheduled even with zero frame ticks remaining.
      // Wait for the queued/current frames AND the ISR's pending step bits.
      if (done && !cancelled && ftMotion.cfg.active
        && (ftMotion.stepping.is_busy() || bool(ftMotion.stepping.step_bits))) return false;
    #endif
    phase = done && !cancelled ? Phase::CompletePending : Phase::AbortPending;
    return true; // No serial, clock reads, or waits here: standard motion calls from ISR.
  }

  #if ENABLED(PINPUT_RESONANCE_PROGRESS)
    // Some serial wrappers don't expose TX capacity. Skip rather than block.
    template <typename Serial> static auto tx_free(Serial &serial, int) -> decltype(serial.availableForWrite()) {
      return serial.availableForWrite();
    }
    template <typename Serial> static int tx_free(Serial&, ...) { return 0; }
  #endif

  void idle() {
    if (reporting) return;
    if (phase == Phase::Idle) {
      EmergencyParser::rt_stop_by_M496 = false; // Don't carry an idle M496 into a later session.
      return;
    }
    if (EmergencyParser::rt_stop_by_M496) cancel();
    if ((phase == Phase::WaitingArm || phase == Phase::ArmAccepted) && !arm_valid()) return;
    if (phase == Phase::Exciting && !marlin.isRunning()) {
      failed = true;
      cancel();
    }
    if (phase == Phase::CompletePending) terminal(F("COMPLETE"));
    else if (phase == Phase::AbortPending) terminal(F("ABORTED"));
    #if ENABLED(PINPUT_RESONANCE_PROGRESS)
      else if (phase == Phase::Exciting) {
        if (ELAPSED(millis(), next_progress_ms)) {
          next_progress_ms = millis() + 1000;
          #if HAS_MULTI_SERIAL
            PORT_REDIRECT(session_port);
          #endif
          if (tx_free(SERIAL_IMPL, 0) >= 48) { // Maximum line is 43 bytes (including LF).
            REMEMBER(report, reporting, true);
            SERIAL_ECHO_START();
            SERIAL_ECHO(F("PIS:RT:PROGRESS:"), session_id, C(':'));
            SERIAL_ECHO(p_float_t(rtg.host_frequency(), 2));
            SERIAL_EOL();
          }
        }
      }
    #endif
  }

} // namespace resonance_host_events

#endif // PINPUT_RESONANCE_EVENTS
