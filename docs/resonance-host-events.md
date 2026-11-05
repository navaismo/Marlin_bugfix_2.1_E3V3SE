# M495 host events (PIS:RT versions 1 and 2)

## Enabling the Pinput_Shaping flow on c13_octoprint

`RESONANCE_TEST` and `PINPUT_RESONANCE_EVENTS` are **disabled by default**.
FT Motion and the branch's X/Y shaping configuration are retained. To use
the OctoPrint Pinput_Shaping resonance-test flow, enable this complete set in
`Marlin/Configuration_adv.h`:

| Option | Purpose |
| --- | --- |
| `FT_MOTION` | Compiles FT Motion and the M495/M496 dispatcher entries in this checkout |
| At least one `FTM_SHAPER_*` algorithm | Supplies FT Motion input-shaping support; the branch already enables these algorithms |
| `INPUT_SHAPING_X`, `INPUT_SHAPING_Y` | Includes both standard-motion X/Y shapers for the supported plugin build configuration |
| `RESONANCE_TEST` | Includes the native sweep generator and command handler |
| `PINPUT_RESONANCE_EVENTS` | Enables M495 capability queries, session events and the v2 host-arming flow |
| `EMERGENCY_PARSER` | Required by resonance testing for M496 cancellation; already enabled in this branch |

Use the exact spelling `PINPUT_RESONANCE_EVENTS`.
`PINPUT_RESONANCE_PROGRESS` remains optional and disabled by default.
After changing the configuration, regenerate and check the active profile:

```sh
python3 buildroot/share/e3v3se/config_profile.py --profile c13_octoprint derive
python3 buildroot/share/e3v3se/config_profile.py --profile c13_octoprint check
pio run -e STM32F103RET6_creality
```

The OctoPrint build workflow exposes one **RESONANCE_TEST +
PINPUT_RESONANCE_EVENTS** checkbox, off by default. Selecting it enables
both flags, FT Motion, X/Y shaping and the emergency parser. It overrides an
unchecked FT Motion input and forces the legacy LCD shaping menu off.
Leaving it unchecked disables resonance testing and host events without
changing the existing X/Y shaping settings. This document and workflow
describe `c13_octoprint`; no SD-branch workflow option is introduced.

Once an enabled build is installed, use the read-only capability query
`M495 Q2` to check for `echo:PIS:RT:READY:2`. With the default build,
M495/M496 are unavailable and no READY event is returned. Ordinary transport
`ok` is never proof that the resonance protocol is available.

### Default-off configuration validation (2026-11-05)

Both `STM32F103RET6_creality` builds passed with FT Motion and X/Y shaping
enabled and optional progress disabled:

| Configuration | Static RAM | Flash |
| --- | ---: | ---: |
| Default: resonance testing and host events disabled | 28,260 bytes | 245,964 bytes |
| Pinput workflow option enabled, including v2 host arming | 28,468 bytes | 254,652 bytes |

The enabled build used an isolated source copy and the real workflow helper,
including the conflicting FT Motion-off / legacy-menu-on selection. The helper
resolved it to FT Motion-on / legacy-menu-off. Six workflow configuration
checks and all six protocol harness variants passed; the profile check and
`git diff --check` also passed. Local build logs are
`.pio/pinput-default-off-build.log` and `.pio/pinput-workflow-enabled/build.log`.
No flashing or physical motion was performed.

## Version 2: host-arming barrier

Version 2 extends the instrumented lifecycle without changing the native sweep
math, FT Motion internals, v1 command behavior, or the build option. No dynamic
allocation or session history is added. The extra persistent state is one
arming flag and one `millis_t` deadline; phases share the existing byte enum.

`M495 Q` still emits exactly `echo:PIS:RT:READY:1`. The new read-only `M495 Q2`
emits `echo:PIS:RT:READY:2`, explicitly confirming the complete contract below.
Other Q values or extra query parameters are rejected without motion. A v1
firmware rejects Q2 with `ERROR:0:INVALID_PARAMETERS`; hosts must not infer v2
support from a firmware name, plain `ok`, or the existing READY:1 response.

```text
M495 X F20 T60 O20 A40 I12345678 S W
  echo:PIS:RT:HOMED:12345678:<firmware_millis>
  echo:PIS:RT:ARMED_WAIT:12345678
M495 I12345678 R
  echo:PIS:RT:ARM_ACK:12345678
  echo:PIS:RT:START:12345678:X:20.00:60.00
  ... existing progress / terminal events ...
```

W and R are bare flags, unused by the native handler in this checkout. W
requires a valid instrumented start; R requires only the canonical I token and
cannot be combined with S, W, axes, or configuration parameters. Invalid ARM
commands produce the nonterminal `ARM_REJECTED:<provided-id>:<reason>` event,
using ID 0 if no valid ID exists. Invalid I syntax retains the existing
`ERROR:0:INVALID_SESSION_ID` response. These command errors never authorize or
terminate a different active session.

HOMED is emitted after successful native G28 returns; its timestamp is the
firmware's wrapping uint32 millisecond uptime. ARMED_WAIT is emitted after
positioning and all fixed-point initialization, with the generator inactive.
The command then returns normally so the dispatcher can process ARM and M496.
The 30,000 ms deadline starts on entry to WaitingArm, not on M495 reception.
The deadline is checked in idle and again synchronously when ARM arrives, so
a late ARM cannot race a delayed idle check. Deadline arithmetic is wrap-safe.

Before ARM_ACK, firmware validates syntax, exact source-port mask, session ID,
WaitingArm state, deadline, cancellation flag, operational state, trusted axes,
unchanged prepared axis position, and empty planner/FT stepping buffers.
ARM_ACK means authorization was accepted; it is not a transport `ok`. The
phase changes before emission, preventing duplicate activation. Cancellation,
timeout, and prepared-state checks run again before publishing `active`, even
if emergency input arrives during ACK or START output. No serial waits or new
hooks run inside ISR or motion generation.

A repeated valid ARM during the same excitation may repeat ARM_ACK but never
START or motion initialization. ARM after termination, a mismatched ID, or a
wrong port cannot activate anything. Nonterminal rejection reasons are
INVALID_PARAMETERS, SESSION_MISMATCH, PORT_MISMATCH, and NOT_WAITING. A failed
pending session emits one existing terminal ERROR with ARM_TIMEOUT,
MOTION_FAILED, AXIS_NOT_HOMED, or PREPARED_STATE_CHANGED. Pending M496 produces
one ABORTED with no excitation. The existing preparation and sweep cancellation
rules below remain applicable.

A feature-gated dispatcher guard rejects commands while WaitingArm or
ArmAccepted unless they are M495/M496, M112, or the transport/status/reporting
allowlist M105/M110/M113/M114/M115/M118/M119/M154/M155/M400/M503. It returns an
ordinary `Error:PIS_ARM_WAIT` and normal queue acknowledgment without executing
the command or destroying the prepared session. This covers serial, SD, and
injected G-code before motion/configuration dispatch. Direct internal UI/HAL
actions are not a physical machine lock: position/axes/buffer checks prevent
arming an observably altered preparation, and operators must retain exclusive
control of the machine during calibration.

Hosts start acquisition only after the matching ARMED_WAIT, require live
acquisition with fresh samples and strictly increasing timestamps across
observations, then recheck health immediately before ARM. START merely marks
activation of the already running acquisition. If the sensor fails after ARM
is queued or sent, hosts must request M496 and await a terminal event; missing
START is never evidence that excitation has not begun. No automatic ARM/start
retry is permitted. COMPLETE still requires the existing real motion drain.

Without a valid ARM, missing communication can only leave an inactive pending
session which expires. A UART connection cannot identify instantaneous host
loss after accepting ARM: that motion may run and requires ordinary stop and
explicit recovery. Reset clears pending authorization, and a standalone stale
ARM cannot create a session. Hosts invalidate capabilities, pending commands,
and result applicability on connection changes, and use fresh session IDs.

Host monotonic times, firmware uptime, and device sample clocks are separate
domains. Log each with its domain; do not subtract timestamps across clocks or
claim exact sample boundaries from host event delivery.

## Version 2 offline validation (2026-11-05)

The production C++ harness passed all six existing feature/FTM/progress/port
combinations, extended with WaitingArm ordering, >30-second preparation,
normal completion, missing/late ARM, deadline rollover, command conflicts,
wrong ports/IDs, duplicate ARM, and emergency/direct-UI cancellation during
ACK and START output. No physical movement or flashing was performed.

Before the default-off configuration change, `pio run -e STM32F103RET6_creality`
succeeded with the local Belaya 8.c configuration, resonance events enabled,
and ARM GCC 12.3.1. A separately compiled baseline in /tmp uses
the same current configuration/version, reverting only the six v2 production
source/header files to their saved pre-change contents:

| Resource | Baseline v1 | Host-armed v2 | Delta |
| --- | ---: | ---: | ---: |
| Static RAM | 28,460 bytes | 28,468 bytes | +8 bytes |
| Flash | 253,268 bytes | 254,652 bytes | +1,384 bytes |

These are linker/PlatformIO static sizes, not measured peak stack usage.
The existing FTM_SHAPER_E recommendation warning remains. A dedicated
STM32F103RE_creality/config-08.ini CI configuration enables resonance, host
events and progress; that configuration runner was not executed here because
it replaces working configurations. The actual configured STM32F103RET6
firmware and the disabled/enabled C++ harness variants were built directly.

## Version 1 contract (unchanged)


## Inspection before the host-event extension

The command handler is `Marlin/src/gcode/feature/resonance/M495_M496.cpp`.
M495 reports settings without arguments, changes A/F/T/O/C and X/Y/Z settings,
and starts with S. The implementation accepts **G** for the timeline lookup
(the existing comment says H). I and Q are unused in this checkout. M496 calls
`rtg.abort()` when active. The emergency parser recognizes M496 and sets
`rt_stop_by_M496`, but this checkout has no consumer of that flag.

`Marlin/src/feature/resonance/resonance_generator.{h,cpp}` owns only `active`
and `done`, rather than a seven-state lifecycle. `start()` synchronously calls
G28 through `gcode.home_all_axes()`, then `blocking_move_xy()` to the center.
Its third argument is XY feedrate, despite the existing clearance constant
passed there; this extension must not change that upstream positioning choice.
The generator then initializes the fixed-point sweep. Native motion equations
and trajectories are outside the scope of this extension.

For standard motion, `Stepper::resonance_block_phase_isr()` generates the next
1 ms block after the previous block's pulses finish. At sweep exhaustion it
receives nullptr, then calls `rtg.abort()`. Resonance bypasses the ordinary
planner queue. Therefore `Planner::synchronize()` (which waits for `busy()`)
is not sufficient evidence of resonance completion.

For FT Motion, `FTMotion::loop()` calls `fill_stepper_plan_buffer()` from
`Marlin::idle()`. Reaching the end frequency sets `done`. On its next call the
loop calls `abort()`, whose `ftMotion.reset()` discards even unexecuted frames.
A truthful successful terminal event requires an instrumented-only drain guard
before this reset. `stepping.is_busy()` includes both queued frames and the
frame already being executed. At an exact frame-end boundary the ISR may also
have pending `step_bits` while frame ticks are zero; these must drain too.
Queue emptiness or `is_busy()` alone is insufficient in that corner case.

Natural exhaustion and cancellation both use `abort()` / `reset()`. Standard
motion may call these from an ISR. Serial output must instead happen in main
context. Existing idle tasks continue heater handling, host keepalive and
autoreporting; the extension will use one idle hook without altering them.

The protocol lifecycle maps to the existing code as follows:

| Protocol state | Native execution point |
| --- | --- |
| Idle | No instrumented session |
| Preparing | Validated session, before the synchronous G28 / positioning |
| Exciting | Sweep initialized, immediately before publishing `active` |
| Completing | Exhaustion observed; FT buffer drains, or ISR posts result |
| Completed | Last standard block finished, or FT buffer and current frame drained |
| Aborted | M496 requested; generator reset (or preparation returns without starting) |
| Failed | A validated request or observable preparation check fails |

The extension lives in the existing resonance directory so its source
is selected by the existing `RESONANCE_TEST` build filter. All hooks are gated
by `PINPUT_RESONANCE_EVENTS`; the default remains disabled. The v2 dispatcher
guard protects preparation while awaiting host authorization. No planner,
stepper, HAL, serial core or motion equations are changed.

## Build options and commands

Enable the complete configuration listed in [Enabling the Pinput_Shaping flow
on c13_octoprint](#enabling-the-pinput_shaping-flow-on-c13_octoprint).
`PINPUT_RESONANCE_EVENTS` is nested inside `RESONANCE_TEST`; both ship disabled,
as does the optional `PINPUT_RESONANCE_PROGRESS` sub-option. The existing
`RESONANCE_TEST` requirement for a 32-bit CPU and `EMERGENCY_PARSER` applies.
Sanity checks reject the extension without resonance testing, and progress
without the extension. No Conditionals, Warnings.cpp, config.ini, EEPROM layout,
or PlatformIO filter changes are needed.

This checkout dispatches M495/M496 only when **FT_MOTION is compiled in**.
It can run either FT Motion or standard motion (selected at runtime using
M493 S1 / S0). The extension does not change that existing dispatcher rule.

* `M495` retains the ordinary settings report.
* `M495 Q` is the capability query. It emits `echo:PIS:RT:READY:1` and returns
  before changing settings, homing, positioning, starting, or saving anything.
  Q with other parameters, including S, returns `ERROR:0:INVALID_PARAMETERS`
  without movement. With the feature disabled there is no READY response.
* `M495 X F20 T60 O20 A40 I12345678 S` runs the native X sweep with events.
  I is unused by the native handler in this checkout. It is an extension-local
  opt-in; no permanent upstream reservation of that letter can be guaranteed.
* I must be a separate, space-delimited token containing a **canonical decimal
  integer from 1 through 4294967295**. No leading zeroes, signs, decimals,
  exponents, quotes, duplicate I parameters, whitespace inside the token, or
  arbitrary strings are accepted. The stored ID is a fixed-size uint32_t.
  Accepted IDs are reproduced exactly in decimal in every session event.
* I requires S. Instrumented requests accept native X/Y/Z, A/F/T/O/C and S.
  The timeline lookup G (and the outdated documented H) is deliberately rejected
  in an instrumented start. Use ordinary M495 for native configuration/lookups.
* Existing M495 and M496 commands without I keep their native behavior when
  there is no instrumented session. A valid instrumented start rejects invalid
  parameters before mutating settings. This stricter validation is opt-in.
  F must be at least 5; T must exceed F and be at most 200; O is 20..60;
  C is an integer 1..8; A is positive and must fit the native Q16 amplitude
  calculation. Existing Z acceleration clamping remains in the native code.
* Concurrent M495 changes are blocked while an instrumented session is pending
  or active. Queries remain available. A different valid ID receives
  `ERROR:<new-id>:TEST_BUSY` without affecting the running session. Replaying
  the active ID receives the ordinary diagnostic `Error:TEST_BUSY`, so a retry
  cannot produce a false terminal event for the active session. Hosts should
  use a new ID for each request, and wait for terminal events before starting
  another test. IDs can be reused after a session terminates; firmware stores
  no session history and does not promise global uniqueness.

## Wire specification, version 1

Every event is an LF-terminated line. Marlin adds `echo:` through
`SERIAL_ECHO_START()`. Hosts must match the whole event line, including its
prefix and field count, rather than searching inside M118 text, `ok`, busy,
position or temperature reports. Ordinary native diagnostics may appear
between events. Do not use `ok` as an excitation boundary.

```text
echo:PIS:RT:READY:1
echo:PIS:RT:START:<id>:<axis>:<start_hz>:<end_hz>
echo:PIS:RT:PROGRESS:<id>:<current_hz>
echo:PIS:RT:COMPLETE:<id>
echo:PIS:RT:ABORTED:<id>
echo:PIS:RT:ERROR:<id>:<reason>
```

Axis is X, Y or Z. Frequencies are Hz with two decimal places and a period as
the decimal separator. All identifiers and reason codes have fixed syntax;
there are no free-form machine-readable fields.

READY is emitted only on an explicit query. START is emitted only for an
accepted instrumented session, after both blocking preparation calls and
fixed-point initialization. The extension enters its Exciting state, queues
START, then publishes the initialized generator as active. Serial output is
finished before generating the first sample, so it adds no gap inside the
first excitation cycle. For standard motion, subsequent samples are generated
in the existing ISR; for FT Motion, the next normal idle pass fills the buffer.

COMPLETE requires the last standard resonance block's pulses to finish, or all
FT frames (including the currently executing frame and any pending ISR step bits)
to drain. FT buffer draining
is the one intentional successful-motion difference for instrumented sessions:
it executes the tail of the programmed native trajectory that the old immediate
reset could discard. No samples, equations, acceleration settings, or stepping
frequencies are added or changed. Natural completion posts a small terminal
state; the next idle hook emits the event after the generator has reset.

M496 retains the native FT reset and buffer discard. For instrumented standard
motion it requests stopping at the next resonance block boundary: the current
block finishes, the generator returns nullptr without producing another block,
and the native ISR resets with no synthetic block still attached. Nominal
latency is up to one 1 ms block plus idle/serial latency. ABORTED is emitted
only after that reset. There is no successful COMPLETE after confirmed
cancellation. A cancellation arriving after successful motion has already
finished does not change the pending COMPLETE into ABORTED.

During preparation, M496 latches cancellation but lets the synchronous G28 or
positioning call finish. The next preparation hook emits ABORTED and returns
without starting excitation (and without positioning if cancellation occurred
during G28). Idle M496 flags are cleared so they cannot poison later sessions.
The queued copy of an emergency-parsed M496 is harmless once the session has
terminated. Hosts should wait for its normal `ok` as well before sending the
next start, to avoid a queued old M496 cancelling a new session.

Each accepted session has one terminal event while firmware remains operational
and can report it. Terminal state and ID are cleared before serial emission;
repeated M496 / idle calls cannot emit a second terminal. A START is not
required for an error or cancellation during preparation.

| Reason | Observable condition |
| --- | --- |
| INVALID_SESSION_ID | I fails the strict decimal-token validation; reserved ID 0 is returned because no valid ID exists |
| INVALID_PARAMETERS | Instrumented request fails parameter validation, or query has extra parameters (query errors use reserved ID 0) |
| TEST_BUSY | A different ID requests a test while resonance or an instrumented terminal result is pending |
| AXIS_NOT_HOMED | Axes are not all trusted after native G28 or positioning returns |
| MOTION_FAILED | Marlin is no longer running after preparation, or a recoverable stop is observed during excitation |

Other failure reasons are not fabricated. Open-loop steppers cannot confirm
physical position, missed steps or mechanical settling. ABORTED confirms
firmware stopped generating test motion / cleared FT frames; it does not prove
that all physical vibration has ceased, nor stop unrelated queued G-code.
No alternative trajectory, abrupt emergency stop, or planner purge is added.

## Progress and timing limits

`PINPUT_RESONANCE_PROGRESS` is disabled by default. When enabled, the main idle
hook samples the generator's actual Q16 frequency at most once per 1000 ms.
This is the current **generated nominal frequency**, ahead of physical execution
by the FT buffering horizon when applicable. It is not inferred from host time.
No progress is emitted before START or after a terminal event.

The hook requires at least 48 free TX bytes, sufficient for the bounded line.
If the selected serial wrapper has no `availableForWrite()` API or lacks
capacity, that update is skipped without waiting or retrying. In particular,
MultiSerial and the production configuration's MeatPack wrapper do not expose
that API, so their progress updates are skipped even if the sub-option is
compiled in. Do not disable transport features merely to get progress output;
the terminal events are sufficient for synchronization.

START / terminal messages use normal Marlin serial helpers and may wait for TX
capacity in main context. START is before activation; COMPLETE / ABORTED are
after test motion stops. They never print from an interrupt. The standard ISR
adds only a cancellation flag check at a block boundary and a terminal latch at
reset. Progress adds no generation-point hooks. Existing host keepalive,
heaters and autoreporting remain in the normal idle flow.

USB/UART buffering, other serial traffic and host scheduling delay delivery.
At the production 115200 baud, a roughly 45-byte START line itself takes about
4 ms on the wire, in addition to existing queued traffic. START reception may
precede or follow the first physical pulse. COMPLETE reception follows the
last commanded pulse; mechanical vibration can persist. There is no bound on
host receipt latency, microsecond synchronization claim, or synchronized clock
with the external accelerometer. V1 intentionally adds no timestamps or clock
correlation protocol. Hardware measurements of jitter and boundary latency
remain necessary; software tests do not establish measurement quality.

A reset, fatal kill (including M112), power loss, serial disconnection, or
non-returning failed homing may prevent a terminal event. Hosts must discard
such sessions as incomplete, never infer COMPLETE from timeouts, and explicitly
query capability again after reconnecting. M496 is the supported cancellation
path. Generic stops such as M410 are not resonance lifecycle notifications in
this checkout and should not be used as substitutes.

## Integration and maintenance

New implementation files are `Marlin/src/feature/resonance/resonance_host_events.h`
and `.cpp`, selected by the existing resonance source filter. They contain the
request validation, bounded session state, serial routing, cancellation,
completion guard and optional progress. There is no heap allocation or retained
command string. Raw token validation uses the existing bounded G-code buffer;
all session state is fixed-size.

Upstream-owned files changed specifically for this extension:

| File | Necessary change |
| --- | --- |
| `Marlin/Configuration_adv.h` | Default-off RESONANCE_TEST and nested PINPUT_RESONANCE_EVENTS / optional progress flags; existing user configuration edits are retained |
| `Marlin/src/inc/SanityCheck.h` | Validate option dependencies |
| `Marlin/src/gcode/feature/resonance/M495_M496.cpp` | Include extension and invoke the small M495 preflight / M496 cancellation hooks; refresh UI on instrumented cancellation |
| `Marlin/src/feature/resonance/resonance_generator.cpp` | Preparation, initialized START, reset/drain guard, and standard block-boundary cancellation hooks |
| `Marlin/src/feature/resonance/resonance_generator.h` | Optional read-only snapshot of current nominal frequency |
| `Marlin/src/MarlinCore.cpp` | Include extension and call its idle hook before FT Motion processing |
| `Marlin/src/gcode/gcode.cpp` | Reject conflicting commands while the v2 session is waiting for ARM or activation |

Hook comments consistently use `PINPUT_RESONANCE_EVENTS: custom host synchronization hook`.
The pre-existing `Marlin/src/inc/Version.h` edit is unrelated and was preserved.
No planner, stepper, HAL, serial core, OctoPrint plugin,
or accelerometer firmware files were changed.

Future merges should mostly leave the new files untouched. Conflicts are most
likely at the resonance `start` / `abort` boundaries, neighboring config options,
and the idle insertion point. Recheck whether upstream still calls abort from
the standard ISR and FT done path, whether `stepping.is_busy()` and pending `step_bits` still describe
the in-flight frame/pulse, and whether I/Q gain native meanings. If upstream changes
these semantics, update the small hooks rather than transplanting a copy of the
resonance algorithm. FT callback changes deserve particular review because the
drain guard relies on repeated abort attempts while done remains true.

## Automated and manual verification

Run the host tests without motors or PlatformIO:

```sh
python3 buildroot/tests/resonance_host_events/test_protocol.py
```

The runner copies the **real** handler, generator and extension into a temporary
build with mocked motion, parser and serial interfaces. It compiles with C++11,
`-Wall -Wextra -Werror`, exercises native calculations, and checks six variants:
extension disabled, standard motion without FT compiled, FT motion, progress,
MultiSerial routing/capacity fallback, and standard motion with FT compiled.
The mock consumers emulate the inspected ISR/FT loop call order; these tests
cannot validate physical stepping or replace an on-printer test.

Assertions cover ordinary commands, read-only capability queries, pre-START
preparation ordering, FT buffer, current-frame and final-pulse draining, deferred terminals,
emergency/direct/preparation cancellation, exactly one terminal, active-ID
retries, idle cancellation flags, strict ID/range validation, busy rejection,
repeated sessions, observable failures, serial routing, progress throttling and
backpressure, and absence of unsolicited protocol messages.

Build the configured production target from the repository root:

```sh
pio run -e STM32F103RET6_creality
```

After flashing an explicitly enabled test build, use the OctoPrint terminal:

1. Send `M495`, then `M496` while idle. Expect ordinary native output and no
   `PIS:RT` lines. Send `M495 Q`; expect exactly `echo:PIS:RT:READY:1`, without
   movement or settings changes. `M495 Q S` must reject without movement.
2. Send `M495 X F20 T21 O20 A40 I1.5 S`; expect
   `echo:PIS:RT:ERROR:0:INVALID_SESSION_ID` without movement. Send an invalid
   range with a valid ID; expect INVALID_PARAMETERS without homing.
3. With the printer ready for a sweep, send
   `M495 X F20 T21 O20 A40 I12345678 S`. Confirm homing/centering finishes before
   START and that COMPLETE occurs once after the sweep's final motion. The
   command's `ok` can arrive long before COMPLETE.
4. Start a longer test with `M495 Y F20 T60 O20 A40 I12345679 S`, then send M496
   during excitation. Expect one ABORTED and no COMPLETE for that ID. Wait for
   the terminal event and the queued M496's `ok`, then repeat with another ID.
   Also cancel during homing; expect no START, and ABORTED only once preparation
   returns. No new excitation should begin after that cancellation.
5. For standard-motion validation, select M493 S0 before the test; for FT Motion,
   select M493 S1. Compare the final frequency tail and cancellation boundaries.
   Restore the intended motion mode afterward. Do not queue unrelated movement
   while measuring the event boundaries.
6. Confirm ordinary non-instrumented M495 still works and emits no protocol
   events. A build with the extension disabled must give no READY response.
   Measure serial-versus-pulse boundaries and sweep quality with hardware before
   relying on them for accelerometer measurements.
7. For the plugin's v2 flow, require `echo:PIS:RT:READY:2` from `M495 Q2`.
   Send `M495 X F20 T21 O20 A40 I12345680 S W`. Confirm HOMED follows G28,
   ARMED_WAIT follows positioning, and no sweep begins while waiting. Once
   acquisition is healthy, send `M495 I12345680 R`; require ARM_ACK then START,
   and exactly one terminal event after completion or M496 cancellation.
8. Prepare a fresh v2 session and withhold ARM. Confirm ARM_TIMEOUT after
   30 seconds in ARMED_WAIT and no sweep. In another pending session, send
   M496 and confirm ABORTED without START. Verify the default-off firmware
   offers neither the v1 nor v2 READY response.


## Historical version 1 build and test results (2026-11-04)

Production target: `STM32F103RET6_creality`, STM32F103RET6, with this workspace's
then-current configuration (FT Motion and MeatPack enabled, before the
thumbnail-buffer optimization and v2 host arming). All six host-test
variants passed. Production baseline, protocol enabled, progress enabled, and
protocol disabled builds passed using `pio run -e STM32F103RET6_creality`.

| Configuration | Flash used / 495616 | Static RAM / 65536 | Binary bytes |
| --- | ---: | ---: | ---: |
| Before extension | 257252 | 34828 | Baseline artifact no longer retained by build cleanup |
| Extension disabled (final default) | 257252 | 34828 | 257872 |
| Events enabled, progress disabled | 259308 | 34836 | 259928 |
| Events and progress enabled | 259364 | 34844 | 259984 |

Events add **2056 flash bytes and 8 static RAM bytes**, compared with disabled
firmware; the binary grows by the same 2056 bytes. The progress-enabled build
adds 2112 flash bytes and 16 static RAM bytes in total. Both remain well within
the board's configured limits. These are linker/static-memory results, not a
measurement of peak runtime stack. The progress code is minimized by the
production wrapper's lack of capacity reporting.

The event-enabled, progress-disabled binary from this verification is
`.pio/build/STM32F103RET6_creality/firmware-20261104-171701.bin`; the optional
progress build is `firmware-20261104-171543.bin` in the same directory. Timestamped
artifacts are subject to the existing build cleanup policy. Both new options
are left disabled in the source after validation. No firmware was uploaded and
no real motors were exercised. Local build logs are `/tmp/m495-baseline-build.log`,
`/tmp/m495-enabled-build.log`, `/tmp/m495-progress-build.log`, and
`/tmp/m495-disabled-build.log`.

The builds retain the pre-existing FTM_SHAPER_E synchronization warning from
`Warnings.cpp`; no extension-specific compiler warnings were observed.
`git diff --check` passed. No push, merge, rebase, or pull request was performed.
