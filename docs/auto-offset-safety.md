# Automatic Z-offset failure handling

The C13/C14 SD and OctoPrint profiles share this protection. It changes the
automatic calibration and optional LCD bed-check paths, without changing probe
pins, voltages, HS mode, EEPROM layout or feature defaults.

## Calibration behavior

- A failed CRTouch measurement, non-finite result, failed stow, stopped firmware
  or lost homing state cancels the calibration before pressure probing that point.
- A pressure search without contact returns `NAN`, not a valid zero. It stops
  the current calibration instead of trying more points or wiping the nozzle.
  Pressure searches retain the existing 3 mm maximum descent and restore the
  actual Marlin software-endstop setting on exit. Raw `G212 K` searches also
  require homed axes and respect this depth limit.
- A sensor failure aborts the complete run even if earlier points were valid.
  Finite offset outliers still use the existing filtering and robust estimator.
- Failure restores the previous Z-offset, preserves the existing mesh and makes
  Z untrusted. It does not save settings or schedule the subsequent `G29`.
- Success establishes Z with the measured offset before saving. Calibration
  assigns the offset without queuing a physical babystep. `M8015` saves the
  offset and cleared mesh together, then optionally schedules normal leveling.
- `G212 C... P T` stops repetitions on the first failure. Both sensors are
  required to calculate an offset; incomplete selections do not move or save.
  The read-only `G212 H` load-cell diagnostic remains available.

Calibration homing uses Marlin's immediate subcommand API, preserving the caller's
parser and pending commands. The LCD bed check runs before queuing an SD print;
if its homing or probe fails, it shows the calibration-failure screen and does not
start that print or automatically launch another probe attempt.
The normal `G29` finish path also aborts on probe/stow failure before its automatic
Z clearance, EEPROM save, post-leveling homing or completion screen.

Per-point diagnostic logging accepts scalar measurements. It no longer reads
three entries from one-element arrays. The shared log formatter is bounded to
its 128-byte buffer; long messages may be truncated.

## LCD error and recovery button

Calibration failures use a dedicated LCD state instead of the wizard's generic
confirmation popup. The screen says "Could not calculate calibration data." and
provides a "Home / Main menu" button. Spanish uses "Fallo al calcular la
calibracion." and "Homing y menu". Other UI languages use the English text.

The button explicitly runs homing and returns to the main menu only if Marlin is
running and all axes are trusted afterward. A probe-stopped Marlin instance is
returned to its running state for this user-requested homing attempt; heaters
that were turned off by the stop are not restarted. Fatal/initializing states
are not restarted. The handler does not flush/replay the host queue, resume a
print, retry M8015, save calibration settings or mark the boot wizard complete.

If homing fails, the LCD stays on the error screen, adds "Homing failed. Check."
and allows another explicit button press. Encoder rotation does nothing; clicks
during an active homing attempt cannot start nested homing. Host progress
updates are disabled while the error screen is shown.

## Validation

`python3 test/test_autooffset_safety.py` executes the production acquisition,
calibration, `M8015`, `G212`, LCD bed check and SD preflight with mocked hardware.
It covers NaN/infinity, stow failure, stopped firmware, lost homing, absent
pressure contact, homing failure before and after acquisition, calibration
rollback, EEPROM save gating, mesh preservation and successful calibration.
The matrix includes Delta/X patterns, FT_Motion enabled/disabled and one/two/three
repeated samples. It uses the production bounded log formatter.

The test does not establish the physical root cause of CRTouch startup issue
[#42](https://github.com/navaismo/Marlin_bugfix_2.1_E3V3SE/issues/42). C14 cold-start
checks with/without SD and FT_Motion, plus calibration on actual C13/C14 printers,
remain necessary. Firmware builds and simulated fault handling cannot establish
that an electrically failed probe will signal contact during normal `G28`.

## Local validation results (2026-11-04)

All four default firmware builds, configuration-profile checks and five
regression scripts passed: calibration error UI, auto-offset safety, advanced
pause, LCD purge and thumbnail progress. The safety test has twelve Delta/X,
FT on/off and sample-count combinations per branch. The UI test runs the real
renderer, handler and screen dispatch for SD/host, both displayed languages,
all boot steps, stopped firmware, failed homing and clicks during homing.
Physical printer validation remains pending.

| Branch | PlatformIO environment | RAM (bytes) | Flash (bytes) |
| --- | --- | ---: | ---: |
| `c13_sd` | `STM32F103RET6_creality` | 28908 | 241204 |
| `c13_octoprint` | `STM32F103RET6_creality` | 29236 | 243308 |
| `c14_sd` | `STM32F401RE_creality` | 28892 | 236312 |
| `c14_octoprint` | `STM32F401RE_creality` | 29220 | 238408 |

The error screen and recovery button add 8 bytes of RAM and 632–656 bytes of flash
per profile compared with the preceding safety fix. Build baselines record the
verified sizes. Existing memory-target limitations are documented in
`upstream-integration-2026-11.md`.
