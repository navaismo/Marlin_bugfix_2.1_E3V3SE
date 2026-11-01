# Experimental bed scale (C13)

`Bed_Scale_test` merges `c13_sd` at `0cdabb7337` and retains the Bed Scale experiment
from `e088c7d195`. It uses the current C13 OctoPrint integration (`OctoHost.*`),
MeatPack and FT_Motion. One Click Print is disabled. The four release branches
do not acquire Bed Scale through this migration.

## Configuration and layout

- `BED_SCALE` in `Configuration_adv.h` is enabled on this experimental branch.
  It requires `USE_AUTOZ_TOOL_2` (HX711 / filtering) and `SET_PROGRESS_MANUALLY`.
- The workflow offers `BED_SCALE` independently of the plugin option. With
  `OCTOPRINT_PLUGIN` enabled, a detected drop emits `M9000 pause-job-bs`; with it
  disabled, the original SD fallback injects `M25`.
- Implementation and command handlers live in `Marlin/src/e3v3se/bed_scale/`.
  The upstream dispatcher and `M73` contain only guarded entry points.
- `buildroot/share/e3v3se/active_profile` selects `bed_scale`. After configuration
  changes, run `config_profile.py derive` and `config_profile.py check`.
- Pin assignment is unchanged: HX711 clock PA4, data PC6. Calibration and tare
  remain RAM-only and must be repeated after restarting; `M500` does not save them.

## Existing command protocol

| Command | Behavior |
| --- | --- |
| `M770 A16` | Read; reports `BS raw=… offset=… delta=… g_est=…` |
| `M771 A32` | Tare; reports `BS TARE ok offset_raw=…` |
| `M772 I1 S640 A32` | Set calibration point 1, measured with 640 g |
| `M772 I2 S1250 A32` | Set calibration point 2, measured with 1250 g |
| `M772 I3 S2000 A32` | Optional third point |
| `M73 L10` | Sample at layer 10 and report `BedScale L10 delta=… g_est=…` |

`A` repeats the filtered acquisition batch, rather than selecting individual ADC
samples. The legacy batch discards 16 samples and filters another 16 at 80 Hz.
Layer sampling therefore takes roughly 0.4 s under normal conditions; a large
`A` can take several seconds. The HX711 wait services `idle()`. This migration
retains the sampling policy rather than introducing a new continuous reader.

The original three-point interpolation, negative-count load polarity, clamps,
20 g drop threshold, two consecutive *decreases between readings*, and initial
three-layer exclusion are preserved. Two hits do not mean two readings below a
fixed baseline. Duplicate layer messages update the previous weight. The old
`enabled` field is not a runtime gate; monitoring follows `M73 L…`. A fresh tare
resets detection history. No automatic per-job tare or EEPROM calibration is added.

Scale acquisitions now propagate an HX711 timeout as invalid instead of feeding
the sentinel into the filters. Ordinary AutoOffset calls retain their original
timeout policy through default arguments. `M73 L…` sampling also works with
thumbnail rendering disabled.

## OctoPrint compatibility

The local plugin at `OctoPrint-LCD_E3V3SE`, branch `main_bed_scale`, recognizes
the retained `BedScale` log prefix, `M9000 pause-job-bs`, and the existing
`M9000` / `M9001` LCD protocol. The plugin repository is not modified here.

There is an existing plugin ordering bug in `gcode_received_handler`: its
`"pause-job" in line` case returns before `"pause-job-bs" in line` can run.
Thus the request pauses an active print, but does not set `bedscale_warn` or show
the specific weight-change message. Handle the more specific token first when
resuming plugin development.

## Verification

Run `python3 test/test_bed_scale.py` for command, calibration, layer reporting,
host / SD pause routing, the production HX711 timeout/filter path, and invalid-acquisition checks. The optional argument
`--plugin /path/to/octoprint_LCD_E3V3SE/__init__.py` exercises the real Python
receive handler without starting OctoPrint and reports the known warning issue.

Build C13 with `pio run -e STM32F103RET6_creality`. The migration needs physical
validation with the HX711, LCD and plugin before treating weight/drop detection
as reliable. No new calibration constants or thermal compensation were inferred.

Migration builds (`STM32F103RET6_creality`):

| Configuration | RAM (bytes) | Flash (bytes) |
| --- | ---: | ---: |
| Default: Bed Scale + plugin + thumbnails | 29,992 | 235,448 |
| Bed Scale disabled, host enabled | 28,708 | 232,436 |
| Bed Scale enabled, plugin and thumbnails disabled | 20,088 | 225,600 |

Default RAM grows by 1,284 bytes and flash by 3,148 bytes compared with the current
C13 host baseline (28,708 / 232,300). These builds fit the target. The existing
40%-of-64-KB RAM guideline is exceeded by the host baseline and this experiment;
the reviewed size baseline records the actual experimental build rather than
disabling unrelated features to reach that guideline.
