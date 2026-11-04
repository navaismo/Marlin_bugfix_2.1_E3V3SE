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

The default C13 profile retains V93 after an ARM-compiler comparison with
`0cdabb7337`: 771 packed bytes, 60 fields with identical offsets, and 128 active
read/write operations including mandatory reads. FTConfig's upstream changes
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

Default, legacy Input Shaping and enhanced-PLR builds must be checked for each
release profile. Check the ELF vector address as well as flash/RAM: C13 starts
at 0x08007000 and C14 at 0x08010000. Host and SD variants retain separate workflow
defaults and their own active configuration profile. Bed Scale is integrated
separately and retains its plugin wire protocol.

Physical testing is still needed for the new SDK: cold boot/settings retention,
LCD/UART, probing, heating, ordinary prints, media insertion/removal, M600 and
runout, OctoPrint prompts/thumbnail transfer, and enabled PLR power-cut recovery.
