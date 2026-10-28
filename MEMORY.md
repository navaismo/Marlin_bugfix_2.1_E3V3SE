# Repository memory

This is a point-in-time reference for future work, not a substitute for checking the active branch and current source. Branch refs, hardware configurations, and experiments may change. Facts below were inspected on **2026-10-09** in the working tree at `for_E3V3SE`, commit `4d0510d947` (also `origin/for_E3V3SE`).

## Repository identity and remotes

- `navaismo/Marlin_bugfix_2.1_E3V3SE` is an Ender-3 V3 SE customization of Marlin `bugfix-2.1.x`, not just a board config. It contains fork-specific DWIN UI work, automatic Z-offset routines, SD/host variants, and feature experiments.
- `origin` points to the navaismo firmware repository. `upstream` points to `MarlinFirmware/Marlin`; the upstream development line is `bugfix-2.1.x`.
- Branch state observed at inspection: `for_E3V3SE` was synchronized with its origin ref; local `for_Octoprint` was one commit ahead of `origin/for_Octoprint`; local `for_Octoprint_F401` was four commits behind `origin/for_Octoprint_F401`. Recheck this before branch integration or comparison.
- `git diff for_E3V3SE...for_Octoprint` warned that there are multiple merge bases. Do not treat a three-dot diff or cherry-pick between long-lived product branches as a clean representation of all semantic differences; inspect target configuration and exact changed files.

## Product branch map

> **Update 2026-10-10:** `c13_sd` is now the GitHub default branch. The branches below were renamed with a `legacy/` prefix on the remote (`legacy/for_E3V3SE`, `legacy/for_Octoprint`, `legacy/for_Octoprint_F401`, `legacy/for_STM32F401`). The table keeps the original names as inspected; read them as `legacy/<name>`. Active work: `c13_sd` and `c13_octoprint`.

| Branch | Hardware / purpose | Distinctive settings or state observed |
| --- | --- | --- |
| `for_E3V3SE` | C13, SD-first firmware | `BOARD_CREALITY_V3_GD303`; `DWIN_RENDER_THUMBNAIL`, `D_ROUTINE_AUTO_OFFSET`, `USE_AUTOZ_TOOL_2`, `ONE_CLICK_PRINT`; current custom DWIN location is `Marlin/src/lcd/dwin/creality/`. |
| `for_STM32F401` | C14, SD-first firmware | STM32F401; similar auto-offset and thumbnail feature settings, but DWIN lives under `Marlin/src/lcd/e3v2/creality/`; has `Marlin/src/pins/stm32f4/pins_CREALITY_F401.h`. |
| `for_Octoprint` | C13, serial-host firmware | Adds `FT_MOTION`, `MEATPACK_ON_SERIAL_PORT_1`, and host support; current ref uses the `lcd/dwin/creality` display path. |
| `for_Octoprint_F401` | C14, serial-host firmware | Host/FT_Motion/MeatPack config on F401; uses the `lcd/e3v2/creality` display path. |
| `for_OctoprintwRender` | Older C13 host/render development line | Historical host UI/rendering work; its source layout and feature state predate the current C13 DWIN path. Do not assume it is interchangeable with `for_Octoprint`. |
| `Bed_Scale_test` | Experimental bed-scale / host work | Adds `BED_SCALE` and `Marlin/src/module/bed_scale/` plus `Marlin/src/gcode/feature/bed_scale/`; history includes `Bed Scale V2` and several test/refactor commits. Treat as experimental, not a release baseline. |
| `e3v3se_changes` | Configuration/motion test branch | Its inspected tree had no content difference from `for_E3V3SE` at comparison time; its latest commit message was `Conf_Adv motion test`. Recheck refs before assuming it remains identical. |
| `bugfix-2.1.x` | Fork's upstream-tracking branch | Not one of the named printer product branches; do not use it as a C13/C14 configuration without verifying its content. |

The branch-to-printer/use mapping is also in [`README.md`](./README.md). Historical release tags include `Krasnaya_*` for SD-first firmware and `Belaya_*` for host-enabled firmware, with `_F401` variants. Treat binaries in `FW_HWC13/` or `FW_HWC14/` as release artifacts, not build inputs.

## Hardware and build identity

- C13's configured board is `BOARD_CREALITY_V3_GD303` (STM32F103RE-class target); the C14 product branches target STM32F401.
- Common C13 settings include serial port 1 at 115200 baud, IIC BL24CXX EEPROM (2 KB), and a `0x7000` flash/bootloader offset. Confirm the active environment and board pin header before relying on these values.
- PlatformIO default environment is `STM32F103RET6_creality`; the documented F401 environment is `STM32F401RC_creality`. Environment declarations and inherited build flags live in `ini/stm32f1.ini` and `ini/stm32f4.ini`, with shared processing in `platformio.ini`.
- The custom pin header `Marlin/src/pins/stm32f1/pins_CREALITY_V3_GD303.h` defines the board's motors, endstops/probe, runout, EEPROM, and HX711 connections. HX711 is wired to PA4 clock and PC6 data in the current C13 setup.
- Project memory targets documented in the project guidance are RAM below 40% of 64 KB and C13 flash below 46% of 512 KB. Compare results for the actual selected environment; these are design limits, not compiler-enforced assertions.

## Architecture and custom feature trails

### Configuration and compilation

`Marlin/Configuration.h` selects the machine/board, basic hardware, display, and core features. `Marlin/Configuration_adv.h` enables advanced motion, storage, host, and advanced feature behavior. `platformio.ini`, the architecture `.ini` files, and `buildroot/share/PlatformIO/scripts/` combine settings and filter sources, so adding an implementation alone may not put it in the build. Feature macros also participate in sanity checks under `Marlin/src/inc/`.

At runtime, G-code handlers under `Marlin/src/gcode/` call core motion/planner/probe/settings code under `Marlin/src/module/`; optional subsystems live under `Marlin/src/feature/`; the HAL maps portable interfaces to hardware. DWIN display workflows span UI code, G-code queueing, the card reader, and the shared DWIN protocol layer. Trace all affected layers before reorganizing code.

### Automatic Z-offset / load-cell path

- `D_ROUTINE_AUTO_OFFSET` is enabled in the inspected primary config; `X_ROUTINE_AUTO_OFFSET` is commented out there.
- `USE_AUTOZ_TOOL_2` gates much of `Marlin/src/module/AutoOffset.cpp` and `AutoOffset.h`. This custom subsystem reads an HX711 load cell and contains acquisition/filtering and multi-point offset-estimation logic; it is not simply standard Marlin probe-offset code.
- `Marlin/src/gcode/probe/M8015.cpp` is the one-key offset command path. The DWIN UI includes controls and calls into offset routines in `Marlin/src/lcd/dwin/creality/` on current C13. Keep probe state, bed-level data, planner synchronization, homing, UI flags, and EEPROM save behavior in view when modifying it.
- `CZ_AFTER_HOMING` is a DWIN Z-height value declared/initialized only for `DWIN_ZHOME_MENU`. Commit `4c1173a9f3` (2026-07-06) fixed its missing declaration/definition behavior: the Configuration option guard and the corresponding DWIN definition must remain paired. References also exist in `probe.h`, `motion.cpp`, `settings.cpp`, and the DWIN UI.

### DWIN, thumbnails, and serial host

- Current C13 moved/uses its Creality display driver under `Marlin/src/lcd/dwin/creality/`; older C14 product branches retain `Marlin/src/lcd/e3v2/creality/`. This path split is a migration/history boundary, not merely two equivalent directories.
- Thumbnail feature control is `DWIN_RENDER_THUMBNAIL`. Commit `b917c68194` (merged as PR #86 on 2026-09-08) changed the current C13 rendering path to row-run encoding, vertical merging, and color-bucketed rectangle blits, with host-side thumbnail quantization in `SlicerScripts/orca_parser.py`. Its commit notes describe static renderer buffers (~9.6 KB) and on-hardware testing; account for memory, watchdog servicing, panel frame throttling, and transparency sentinel behavior when changing this code. Benchmark notes and replay/stress tools are in `DWIN_OptimizationReference/`.
- `ONE_CLICK_PRINT` spans SD file selection/card-reader state, G-code handling (including `M1003`), and menu/UI behavior. Commit history includes one-click SD navigation and EEPROM-error handling fixes; a related remote topic branch `fix/53-one-click-print-start-wrong-file` changes `selectNewestFile()` bookkeeping. Check card state and work-directory synchronization before changing selection logic.
- Host-only behavior includes `HOST_ACTION_COMMANDS`, MeatPack on serial port 1, host G-code/UI commands, and FT_Motion. C13/C14 host branches share product intent but have separate configs and display implementation paths. Confirm host semantics and exact branch before moving code.

### Experimental bed-scale feature

The `Bed_Scale_test` branch added a dedicated `BED_SCALE` module and G-code handlers `M770`/`M772`, with history including calibration/readout test iterations. This is separate from the existing HX711-backed automatic offset code. Do not conflate the two sensor/feature paths or move experimental bed-scale code into a release branch unless requested.

## History milestones worth knowing

- The feature development history includes early automatic-offset integration (`9963554462`, `564cc0c58e`, 2025-era), five-point probing work (`a50d46b83a`), a later four-point `D_ROUTINE_AUTO_OFFSET` configuration, custom DWIN menu work, and one-click printing added in the Krasnaya V2 line (`3543fd5930` / F401 variant `5ee98c6a5b`).
- Host/OctoPrint development included plugin-support commits such as `ae0a7b2489`, with `M9000`/`M9001`, MeatPack and UI/host-command changes, then Belaya releases. Several related fixes affect host action commands (`M876`) and pause/stop/progress notifications.
- Upstream Marlin changes are regularly merged into product branches. The current primary branch history includes upstream integration `174fe65f34` (2026-06-11), custom fix `4c1173a9f3`, then the thumbnail optimization merge `4d0510d947`. When behavior differs from upstream, check whether the code is fork-specific before replacing it with upstream code.

## Commands and safe test habits

See [`.github/copilot-instructions.md`](./.github/copilot-instructions.md) for exact build, unit-test, build-test, and validation commands. Single unit tests use `UNIT_TEST_CONFIG` names from `test/*.ini`; single firmware build tests use `TEST_TARGET` and optional `ONLY_TEST`.

The Makefile/test runner supports `GIT_RESET_HARD`, which can run `git reset --hard HEAD` after test configurations. Never enable it when working with user changes unless explicitly approved. Always check git status before and after commands that may replace configuration files.

## Architecture branch progress (`architecture/e3v3se-upstream-seams`)

- Merged upstream bugfix-2.1.x (220 commits) with conflicts resolved in favor of upstream core + fork hooks.
- Step 1 guardrails: `buildroot/share/e3v3se/check_profile.py` (boundary/build/config).
- Step 2 one-click print: realigned with upstream; added `selectNewestFile()` depth-sync (from `origin/fix/53-one-click-print-start-wrong-file`). Not yet tested on a printer.
- Step 3: auto Z-offset moved to `Marlin/src/e3v3se/`. Thumbnail code is not separable (about 300 refs in dwin.cpp plus marlinui/M73 hooks); left in place.
- Step 4: C13 SD config profile `profiles/c13_sd` (242 define overrides + residual patches). Firmware verified identical to pre-change build except for the timestamp.
- Step 5 (done, branch `c13_octoprint`, see below): C13 host profile. Next: C14 (STM32F401).
- `Marlin/Config-export.h` is a tracked build artifact; consider untracking.

## First-boot wizard audit (post upstream merge)
- Wizard state lives in raw BL24CXX bytes 0x01-0x07 (below `EEPROM_OFFSET` 100), so it is independent of Marlin's settings block and survives settings resets/version bumps (same as pre-merge behavior).
- `EEPROM_VERSION` is V93 both before and after the merge; `SettingsData` layout is unchanged for this config (751 B). `HAS_LEVELING_TEMP_EDIT` is off (needs PROUI), `HAS_MESH_STORAGE` unchanged.
- Hooks intact: `HMI_Init/Read_Boot_Step_Value`, `HMI_Confirm` -> `M8015 S1`, `M8015.cpp` (`Need_boot_flag`), `G29.cpp` boot-leveling confirm popup.
- Wizard reruns only when the boot-step byte != `Boot_Step_Max` (blank EEPROM / fresh install). Not retriggered on settings reset (unchanged behavior). Not tested on device.

## FT_MOTION (C13 SD)
- Enabled via profile overrides (`FT_MOTION`, `FTM_IS_DEFAULT_MOTION`, X shaper NONE, Y 3HEI 42 Hz, X freq 37). Legacy `INPUT_SHAPING_X/Y` removed (replaced by FTM shapers). `LIN_ADVANCE` was later turned off (underextrusion after retractions; the K value had come from the slicer start G-code). `M900 K` still works at runtime. K calibration postponed. Rationale: issue #23 (SD print stalls fixed by FTM).
- Issue #23 comment also had LIN_ADV and STEALTHCHOP_E off; we kept them on per request. If stalls return, test with them off first.
- Issue #23 also saw broken Z-offset after FTM: `getZOffset()` (e3v3se/AutoOffset.cpp) now runs under `FTM_DISABLE_IN_SCOPE()`.
- Baseline: RAM 29,220 B, flash 234,668 B (47.3%, ~1.2 KB under the 46%-of-512KB cap).

## Bed MINTEMP (flaky/missing bed sensor)
- Origin: commit e10eec2d7b ("false positive thermal protection") used a function-local counter that reset every call, so bed MINTEMP effectively never fired. A later 10-sample debounce re-enabled it and halted printers with bad bed sensors.
- Now explicit: `E3V3SE_IGNORE_BED_MINTEMP` (Configuration.h, in profile residual) skips only the bed MINTEMP check in `updateTemperaturesFromRawValues()`. BED_MAXTEMP, thermal runaway and heating-failed (WATCH_BED) protections remain active.
- PATH `pio` (6.1.19) is stale and fails to fetch tool-scons; use `~/.platformio/penv/bin/pio` (6.2.0).

## Thumbnail renderer extraction
- `DWIN_RenderThumb` and its SD/RLE helpers moved from `lcd/dwin/creality/dwin_lcd.cpp` to `Marlin/src/e3v3se/ThumbRender.cpp` (built via `platformio.ini` filter, guarded by `DWIN_RENDER_THUMBNAIL`). Behavior unchanged; flash +56 B.
- The thumbnail UI hooks in `dwin.cpp` (ThumbTune menus, `Goto_ThumbPrint`, ~116 `hasThumbnail` branches inside HMI handlers) stay there: they share static state with the handlers and can't be split without a UI rewrite.

## C13 OctoPrint host profile (branch `c13_octoprint`)
- Profile `buildroot/share/e3v3se/profiles/c13_octoprint` is derived from `c13_sd`; the only differences are `OCTOPRINT_PLUGIN` (Configuration.h), `MEATPACK_ON_SERIAL_PORT_1` on and `ONE_CLICK_PRINT` off (Configuration_adv.h; not needed when printing from the host). `buildroot/share/e3v3se/active_profile` names the profile `config_profile.py` uses by default; override with `--profile <name>`.
- Docs are tracked in git, so every branch carries its own copy; this file describes the state of the branch it is on. Keep branch-specific notes in sections like this one so merges stay trivial.
- Host layer: `Marlin/src/e3v3se/OctoHost.{h,cpp}` owns `serial_connection_active`, `title`, `MarlinUI::print_time`, `M9000` (A/L/T/P/N plus S=print screen, F=finish screen) and `M9001` (START / `C line offset hex` / END thumbnail stream, RGB565 x 96 px). Dispatch cases are in `gcode.cpp` under `OCTOPRINT_PLUGIN`. Plugin: https://github.com/navaismo/Octoprint-LCD_E3V3SE.
- `M115` and `M9000 A1` set `serial_connection_active` (`gcode/host/M115.cpp` hook).
- `HOST_LINK_UP()` (OctoHost.h) gates pause/resume/load/reheat host prompts in `feature/pause.cpp`: always true without the plugin, only true after the plugin connected otherwise.
- MeatPack stays on for the host profile. `meatpack.{h,cpp}` are identical to `for_Octoprint`; the emergency-parser state is reset on pack/unpack commands so M876/M108/M410 work with MeatPack. M876 itself is stock upstream (`HOST_PROMPT_SUPPORT`).
- Remaining plugin DWIN code (`OCTOPRINT_PLUGIN` blocks in `lcd/dwin/creality/dwin.cpp`) is unchanged from `for_Octoprint`: `OctoRefresh`, print-time label, "OctoPrint Connected" title, `Goto_ThumbFinish`.
- Baseline: RAM 44.8%, flash 47.7% (236,196 B); over the 40%/46% targets, baseline raised on purpose.
- Verified on device: temperature, pause/stop/resume from host, command streaming, MeatPack, finish screen. Thumbnail stream and M876 with MeatPack also verified. Not yet verified: M600 host prompts, ONE_CLICK_PRINT-off build. Unresolved: OctoPrint handshake (`N0 M110` got no reply while miniterm worked).

## Enhanced PLR with LCD menu

- `POWER_LOSS_RECOVERY` and `DWIN_PLR_MENU` are commented out in the shipping config to save flash/RAM. The workflow's single `power_loss_recovery` boolean (default false) toggles both together. Config edits can enable them manually; M413/the LCD only control the runtime state of compiled-in recovery.
- Applies to SD jobs on both SD and OctoPrint firmware, not streamed host prints. Recovery takes priority over One Click Print and uses a nonblocking DWIN confirmation dialog. Advanced options live in fork-owned `src/e3v3se/PLRSettings.*`, gated by `DWIN_PLR_MENU`.
- BL24CXX bytes 0x20–0x2F hold the versioned/CRC-protected menu settings. M500/M501/M502 save/load/reset them without changing Marlin's V93 EEPROM block or calibration. Heating while awaiting confirmation is optional and Cancel turns those heaters off.
- Checkpoints accumulate small Z changes against the last durable save, use an immutable write snapshot, preserve the resumed SD offset, and distinguish the live segment from the start of its whole G-code command. Standard Stepper and FT_Motion share `capture_block`; this preserves IJ arc centers and M83 extrusion when replaying segmented commands. C13 `/PLR` records grew from 196 to 212 bytes; older checkpoints are rejected.
- Resume uses absolute recovery moves, restores saved modes/home/workspace offsets, reverses leveling modifiers once, preserves physical Z through M420 and purges at 3 mm/s. Serial logs distinguish command start, live segment, commanded return and counter-derived return. The LCD uses the standard print screen without a thumbnail after recovery.
- Native tests cover workflow toggles, UI and One Click Print, menu editing/EEPROM fault injection, checkpoint consistency, leveling/fade/offsets, and replay of a spiral hop from the reported cube. On-printer C13 feedback confirms substantially improved recovery; other geometries and the other board/host variants still require hardware coverage. See `docs/power-loss-recovery.md`.

## Legacy input shaping LCD menu (2026-10-28)

- `DWIN_INPUT_SHAPING_MENU` controls the legacy X/Y `M593` shapers. `FT_MOTION` disables it automatically in both configuration and the workflow helper; FT_Motion continues to use `M493`.
- With FTM off, selecting the LCD menu enables legacy `INPUT_SHAPING_X/Y` in `Configuration_adv.h`, so a workflow-only selection includes functioning shapers. Final conditionals also hide the menu if either legacy axis is unavailable.
- LCD edits use integer hundredths and the current Stepper frequency/damping setters. Frequency is 0 (off) or a timer-representable value up to 999.99 Hz; damping is bounded to 0..1. M593 and EEPROM save/load share these live values. Menu navigation no longer depends on the hotend count.
- Native regressions cover manual/workflow feature combinations, menu edits and bounds, Stepper delay/enabled/damping state, ISR restoration and synchronization. Physical resonance tuning still requires printer testing.
- The Stepper frequency setter now casts only the enabled delay calculation, preserving the integer off sentinel on 32-bit timers instead of converting it through float. Regression coverage includes 16-bit and 32-bit timer types.
- Visibility regression `test/test_dwin_input_shaping_visibility.py` enters via the real Control and Motion handlers, records the actual label/icon drawing calls, checks viewport bounds and post-draw visibility, and returns from the real submenu. It covers image/text labels, optional jerk/skew rows and menu disabled. The redundant Skew drawing call using a pixel Y as a row was removed. Skew menu measurement variables also have definitions initialized from the configured XY defaults, fixing the existing link failure when its menu is selected.
