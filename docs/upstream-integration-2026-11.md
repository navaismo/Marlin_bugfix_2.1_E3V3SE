# Upstream integration, November 2026

The shared firmware integrates upstream `1c204b77c916bb16b59aeb765bdca4e0fd180efa`
on top of the October C13/C14 release branches. STM32 builds use ststm32 17.1.0,
STM32duino 2.6.0 and GCC 12.3. Configuration profiles are regenerated against
that upstream revision; obsolete `MINIMUM_PLANNER_SPEED` is removed.

## Adaptations

- DWIN implements the upstream `dwinInitScreen()` startup interface while keeping
  the V3 SE handshake, encoder initialization and first-boot wizard.
- The fork uses the current filename-byte constants and workspace-offset guards.
- `pause.cpp` follows upstream, including `paused_for_filament_change`, configurable
  purge length and refreshed host prompts when runout state changes. The former
  fixed 40-mm purge and separate host-only wait loop are removed.
- The Creality LCD implements `pause_show_message`: parking, heating, unload,
  insertion, loading, purge and resume use the upstream state machine. The knob
  selects Purge More or Resume. A latched sensor changes Resume to Disable Sensor,
  matching the host's explicit disable-and-resume operation. Temperature handling
  continues through the core idle loop. Thumbnail resumes preserve progress.
- With `HAS_FILAMENT_SENSOR`, only Marlin's detector triggers the filament change.
  The legacy LCD M25 detector is compiled only without the core sensor. Thus it
  cannot overwrite pending M600, bypass M412 S0 or ignore M412 H1. The definition
  of an active print remains upstream's timer/SD policy; thermal timer autostart
  can still make a manual heating session count as an active job.
- SD uses upstream's asynchronous insertion/retry behavior and mounted-only PLR
  file access. The fork's newest-file working-directory synchronization remains.
  Enhanced PLR keeps its checkpoint, extrusion-mode and coordinate restoration.

## EEPROM compatibility

All four default profiles retain V93 after ARM-compiler comparisons with their
own pre-merge revisions: 771 packed bytes, 60 fields with identical offsets, and
128 active read/write operations including mandatory reads.

| Profile | Previous revision |
| --- | --- |
| c13_sd | `0cdabb7337` |
| c13_octoprint | `4829b53768` |
| c14_sd | `f37fed5275` |
| c14_octoprint | `67296fda7d` |

FTConfig's upstream changes
affect initialization syntax, not its stored fields. Optional features that
change the settings schema still require their normal configuration compatibility
checks. Wizard bytes 0x01–0x07 and PLR-menu bytes 0x20–0x2F are unchanged.

Reproduce the comparison after a matching default build:

```sh
pio run -e STM32F103RET6_creality -t compiledb
python3 buildroot/share/e3v3se/check_eeprom_upgrade.py --ref 0cdabb7337
```

The comparison requires `pyelftools`, reads the previous source from Git, and
compiles a temporary object. It does not flash firmware or touch printer EEPROM.
Run PlatformIO build/compiledb operations sequentially for a given build directory.

## Verification

Native regression scripts exercise the production functions with simulated
hardware. In addition to the existing extruder, Input Shaping and PLR suites:

```sh
python3 test/test_dwin_advanced_pause.py
python3 test/test_dwin_runout_owner.py
python3 test/test_upstream_media.py
```

These cover configurable/repeated purge, knob and host confirmation, explicit
sensor disable, progress preservation, event-driven drawing, core runout ownership,
asynchronous SD insertion/removal, mount retry failure, recovery precedence and
mounted-only recovery-file access.

Default, legacy Input Shaping and enhanced-PLR builds passed for all four
release profiles. Each profile also passed the twelve focused native regression
scripts (48 script runs across the four profiles). Check the ELF vector address
as well as flash/RAM: C13 starts
at 0x08007000 and C14 at 0x08010000. Host and SD variants retain separate workflow
defaults and their own active configuration profile. Bed Scale is deferred:
`Bed_Scale_test` remains at `47f612a866`, and its
OctoPrint plugin is unchanged.

### Measured builds

`legacy` enables the LCD Input Shaping menu with FT_MOTION disabled. `plr`
enables POWER_LOSS_RECOVERY and its advanced LCD menu. The committed defaults
keep PLR, BED_LEVEL_VISUALIZER and E3V3SE_IGNORE_BED_MINTEMP disabled.

| Profile | Configuration | RAM (bytes) | Flash (bytes) | Vector address |
| --- | --- | ---: | ---: | --- |
| c13_sd | default | 28916 | 239580 | `0x8007000` |
| c13_sd | legacy | 29872 | 228480 | `0x8007000` |
| c13_sd | plr | 29576 | 246424 | `0x8007000` |
| c13_octoprint | default | 29228 | 241668 | `0x8007000` |
| c13_octoprint | legacy | 30200 | 230520 | `0x8007000` |
| c13_octoprint | plr | 29904 | 248432 | `0x8007000` |
| c14_sd | default | 28884 | 234928 | `0x8010000` |
| c14_sd | legacy | 29856 | 225132 | `0x8010000` |
| c14_sd | plr | 29560 | 241908 | `0x8010000` |
| c14_octoprint | default | 29212 | 237000 | `0x8010000` |
| c14_octoprint | legacy | 30184 | 227188 | `0x8010000` |
| c14_octoprint | plr | 29888 | 243932 | `0x8010000` |

The updated default-build baselines record this integration's measured growth;
updating them does not mean the separate memory design targets were met. All
default builds exceed the documented 40%-of-64-KiB RAM target (the pre-merge
defaults already did). C13 OctoPrint default flash is 241668 bytes, about 496
bytes above the 46%-of-512-KiB target; C13 PLR builds also exceed that target.
All twelve builds fit their configured hardware/linker limits. These figures
exclude runtime stack/heap peaks and physical validation is still required.

`make validate-boards` still reports the two pre-existing errors for the fork's
`BOARD_CREALITY_V3_GD303` ID 4050 and its position in `pins.h`. Running the
pre-merge validator on `0cdabb7337` reproduces both errors. This integration
preserves the board ID and wiring; board registration cleanup remains separate.

Physical testing is still needed for the new SDK: cold boot/settings retention,
LCD/UART, probing, heating, ordinary prints, media insertion/removal, M600 and
runout, OctoPrint prompts/thumbnail transfer, and enabled PLR power-cut recovery.
