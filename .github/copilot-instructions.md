# Copilot instructions

For repository-wide agent rules and the branch/custom-feature history, also read the fork rules in [`AGENTS.E3V3SE.md`](../AGENTS.E3V3SE.md) (upstream's own `AGENTS.md` is the generic Marlin reference) and [`MEMORY.md`](../MEMORY.md).

## Project and target

This repository is a Marlin 2.1.x bugfix fork customized for the Creality Ender-3 V3 SE. It supports two board revisions and separate SD-card and serial-host feature sets:

| Hardware | Use | Branch |
| --- | --- | --- |
| C13 (`BOARD_CREALITY_V3_GD303`, STM32F103RE) | SD card | `c13_sd` |
| C14 (STM32F401RE) | SD card | `c14_sd` |
| C13 | OctoPrint / serial host | `c13_octoprint` |
| C14 | OctoPrint / serial host | `c14_octoprint` |

All four variants use the upstream-merge architecture and active configuration
profiles. The `legacy/` branches are historical references. `Bed_Scale_test`
adds the experimental scale and plugin protocol in its own `bed_scale` profile.
See `docs/upstream-integration-2026-11.md` before changing startup, pause/runout,
SD state or the EEPROM schema. STM32 uses STM32duino 2.6.0 / ststm32 17.1.0.

Check the active branch and target before changing board-specific configuration or host behavior. The SD-only and host branches do not have identical enabled features.

## Build, test, and validation

PlatformIO is the firmware build system. The default environment is the C13 target:

```sh
pio run -e STM32F103RET6_creality
pio run -e STM32F401RE_creality
make marlin
```

The manual GitHub Actions workflow `.github/workflows/build-marlin.yml` builds this branch (`c13_octoprint`) in CI: it starts from the committed configuration, applies the feature toggles chosen in the run dialog through `.github/scripts/apply_marlin_options.py`, and uploads `firmware*.bin` as an artifact. Keep the workflow inputs and defaults in sync with the branch profile.

`make marlin` invokes `buildroot/bin/mftest -a` and builds the configured environments. Environment definitions are in `ini/stm32f1.ini` and `ini/stm32f4.ini`; common configuration and source filters are in `platformio.ini`.

Tests are split between native unit tests and firmware build tests:

```sh
# All native unit-test configurations
make unit-test-all-local

# One unit-test configuration (omit the numeric prefix from test/*.ini)
make unit-test-single-local UNIT_TEST_CONFIG=default
make unit-test-single-local UNIT_TEST_CONFIG=extruders_1_runout

# All CI build-test targets
make tests-all-local

# One build-test target; optionally select one test by name or 1-based index
make tests-single-local TEST_TARGET=mega2560 ONLY_TEST=2
```

The unit tests live in `Marlin/tests/` and are compiled per configuration listed under `test/`. The build tests are under `buildroot/tests/`. The Makefile also provides Docker variants of the test commands.

Repository validation commands:

```sh
make validate-lines
make validate-pins
make validate-boards
make validate-urls
```

`validate-lines` checks text formatting with Prettier. `validate-pins` formats and checks pin files; scope it to a pin family when appropriate, e.g. `make validate-pins PINSPATH=stm32f1`. `validate-boards` checks board and pin definitions. `validate-urls` checks source URLs.

## Architecture and configuration flow

The build is configuration-driven. `Marlin/Configuration.h` selects the machine, board, geometry, sensors, display, and core features; `Marlin/Configuration_adv.h` controls advanced motion, thermal, host, and storage behavior. PlatformIO loads these settings with the per-environment board definitions and build scripts in `platformio.ini` and `ini/`. Pre-build scripts apply configuration checks and determine which code is compiled, so a feature can affect both configuration validity and source inclusion.

At runtime, G-code is parsed and queued through `Marlin/src/gcode/`; core motion, planning, step generation, thermal control, and settings are coordinated in `Marlin/src/module/`. Optional behavior is implemented in `Marlin/src/feature/`, while `Marlin/src/HAL/` supplies platform-specific hardware implementations behind shared interfaces. The Ender-3 V3 SE DWIN UI is in `Marlin/src/lcd/dwin/creality/` and uses shared display protocol code in `Marlin/src/lcd/e3v2/common/`.

Board wiring and board-specific capabilities are defined in `Marlin/src/pins/`, including `pins_CREALITY_V3_GD303.h` for C13. A pin change may require updating validation/build-test expectations as well as the board header.

## Repository-specific conventions

- Keep machine settings in `Marlin/Configuration.h` and `Marlin/Configuration_adv.h`; don't edit generated build output or `.pio/`.
- Guard optional code with the relevant feature macro and use Marlin conditionals such as `#if ENABLED(FEATURE)` / `#if DISABLED(FEATURE)` rather than raw `#ifdef` for configuration options.
- Follow the Marlin C++ coding standards referenced by [`.github/contributing.md`](./contributing.md). Reuse existing feature guards and Marlin helpers, including `TERN`/`TERN_`, where code around the change does so.
- Preserve portability across Marlin's supported architectures. Use `PROGMEM`/`PSTR()` where required for AVR-compatible strings; they are not needed for this STM32 target.
- Firmware memory is a hard design constraint: keep RAM below 40% of 64 KB and C13 flash below 46% of 512 KB. Check memory usage after builds, especially when enabling or adding features.
- Keep hardware-specific changes consistent with the intended branch and board. C13 uses an STM32F103RE, UART1 at 115200 baud, IIC BL24CXX EEPROM (2 KB at `0x800`), and a `0x7000` bootloader offset; C14 uses STM32F401.
- Custom features include DWIN thumbnail rendering (`DWIN_RENDER_THUMBNAIL`), one-click printing (`ONE_CLICK_PRINT`), Delta/X Z-offset routines, FT_Motion/input shaping, Linear Advance, the HX711 load cell (PA4 clock, PC6 data), CRTouch, LCD dimmer/brightness controls, filament runout handling, and the compact 6×6 leveling grid. Trace both configuration guards and runtime/UI call sites before changing one.
- The pull request branch and target-specific firmware behavior are documented in [`README.md`](../README.md); the test layout and unit-test model are described in [`test/README.md`](../test/README.md).
- Prebuilt C13 firmware images are under `FW_HWC13/`; serial debugging support is in `Serial_Debugger/serial_util.py`.
