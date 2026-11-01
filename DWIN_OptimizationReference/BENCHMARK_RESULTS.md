# DWIN Thumbnail Rendering Benchmark Results

**Status:** Measured on real hardware, current as of this branch's committed firmware.
**Hardware:** GD32F303RET6 (`BOARD_CREALITY_V3_GD303` / `STM32F103RET6_creality`), TJC panel
via UART @ 115200, connected directly to `/dev/ttyUSB0`.
**Throttle:** batch-all, `batch_size=10` frames, `batch_delay=16ms` -- the value committed in
`Marlin/src/lcd/dwin/creality/dwin_lcd.cpp` (`THUMB_BATCH_SIZE`/`THUMB_BATCH_DELAY_MS`), applied
identically to every run below, old algorithm included. Confirmed reliable on this C13/GD32F303
hardware; F401 boards are untested (see the throttle comment in `dwin_lcd.cpp`).

This supersedes all previous numbers in this file. Earlier results used a different (looser)
per-frame throttle and a different, smaller set of thumbnails, and are not comparable to the
numbers below.

## What's being compared

Two independent variables, tested in combination:

- **Algorithm**: `naive` (the original `DWIN_RenderThumb` -- one `DWIN_Set_Color` +
  one 1x1 `DWIN_Fill_Rect_Raw` per foreground pixel, in raster order) vs. `bucketed` (the
  algorithm in this branch -- row-RLE, vertical run merging across rows, emission bucketed by
  color so each palette is sent once).
- **Slicer post-processing**: `full` (thumbnail embedded by the *previous* version of
  `SlicerScripts/orca_parser.py`, no color quantization) vs. `q32` (embedded by the *current*
  version, median-cut quantized to <=32 colors, background-masked).

Both variables act on the same 9 real G-code files (`test_1`..`test_9`, one renamed `test_5m`),
each re-sliced twice to produce a `_full` and a `_q32` variant -- 18 source files, each rendered
with both algorithms, so **36 real-hardware renders** in total.

Command lists were generated directly from each file's `E3V3SE_THUMB_RAW16` block (the actual
pixel data the firmware parses), not from the slicer's separate cosmetic base64 PNG preview
comment -- the latter is unaffected by `orca_parser.py`'s quantization and is identical between
`_full`/`_q32` pairs, which would have silently defeated this comparison.

## Results

| File | Algorithm | Commands | Palette sets | Fills | Time |
|---|---|---:|---:|---:|---:|
| test_1_full | naive | 3814 | 1907 | 1907 | 9.73s |
| test_1_full | bucketed | 1030 | 58 | 972 | 2.75s |
| test_1_q32 | naive | 3814 | 1907 | 1907 | 9.61s |
| test_1_q32 | bucketed | 992 | 26 | 966 | 2.66s |
| test_2_full | naive | 4446 | 2223 | 2223 | 11.14s |
| test_2_full | bucketed | 1226 | 54 | 1172 | 3.18s |
| test_2_q32 | naive | 4434 | 2217 | 2217 | 11.16s |
| test_2_q32 | bucketed | 1162 | 15 | 1147 | 3.07s |
| test_3_full | naive | 6346 | 3173 | 3173 | 16.12s |
| test_3_full | bucketed | 1865 | 115 | 1750 | 5.02s |
| test_3_q32 | naive | 6346 | 3173 | 3173 | 15.89s |
| test_3_q32 | bucketed | 1764 | 59 | 1705 | 4.66s |
| test_4_full | naive | 3760 | 1880 | 1880 | 9.51s |
| test_4_full | bucketed | 1018 | 42 | 976 | 2.69s |
| test_4_q32 | naive | 3792 | 1896 | 1896 | 9.55s |
| test_4_q32 | bucketed | 937 | 17 | 920 | 2.50s |
| test_5m_full | naive | 4020 | 2010 | 2010 | 10.08s |
| test_5m_full | bucketed | 908 | 51 | 857 | 2.40s |
| test_5m_q32 | naive | 3992 | 1996 | 1996 | 10.15s |
| test_5m_q32 | bucketed | 791 | 19 | 772 | 2.05s |
| test_6_full | naive | 4078 | 2039 | 2039 | 10.17s |
| test_6_full | bucketed | 1169 | 34 | 1135 | 3.07s |
| test_6_q32 | naive | 4126 | 2063 | 2063 | 10.44s |
| test_6_q32 | bucketed | 1118 | 15 | 1103 | 3.05s |
| test_7_full | naive | 4084 | 2042 | 2042 | 10.38s |
| test_7_full | bucketed | 1292 | 69 | 1223 | 3.44s |
| test_7_q32 | naive | 4072 | 2036 | 2036 | 10.25s |
| test_7_q32 | bucketed | 1169 | 23 | 1146 | 3.11s |
| test_8_full | naive | 3904 | 1952 | 1952 | 9.69s |
| test_8_full | bucketed | 1474 | 73 | 1401 | 3.96s |
| test_8_q32 | naive | 3904 | 1952 | 1952 | 9.82s |
| test_8_q32 | bucketed | 1353 | 25 | 1328 | 3.62s |
| test_9_full | naive | 4546 | 2273 | 2273 | 11.46s |
| test_9_full | bucketed | 1681 | 121 | 1560 | 4.46s |
| test_9_q32 | naive | 4538 | 2269 | 2269 | 11.49s |
| test_9_q32 | bucketed | 1429 | 27 | 1402 | 3.64s |

All 36 renders completed with no visible corruption and no watchdog resets under the
`batch:10:16` throttle -- including the naive algorithm, which the previous firmware never ran
at this throttle value (it used its own, looser, per-pixel-counted delay).

## Speedups

### Algorithm alone (naive -> bucketed), same input file

| Pair | Naive | Bucketed | Speedup |
|---|---:|---:|---:|
| test_1_full | 9.73s | 2.75s | 3.54x |
| test_1_q32 | 9.61s | 2.66s | 3.61x |
| test_2_full | 11.14s | 3.18s | 3.50x |
| test_2_q32 | 11.16s | 3.07s | 3.64x |
| test_3_full | 16.12s | 5.02s | 3.21x |
| test_3_q32 | 15.89s | 4.66s | 3.41x |
| test_4_full | 9.51s | 2.69s | 3.54x |
| test_4_q32 | 9.55s | 2.50s | 3.82x |
| test_5m_full | 10.08s | 2.40s | 4.20x |
| test_5m_q32 | 10.15s | 2.05s | 4.95x |
| test_6_full | 10.17s | 3.07s | 3.31x |
| test_6_q32 | 10.44s | 3.05s | 3.42x |
| test_7_full | 10.38s | 3.44s | 3.02x |
| test_7_q32 | 10.25s | 3.11s | 3.30x |
| test_8_full | 9.69s | 3.96s | 2.45x |
| test_8_q32 | 9.82s | 3.62s | 2.71x |
| test_9_full | 11.46s | 4.46s | 2.57x |
| test_9_q32 | 11.49s | 3.64s | 3.16x |
| **Average** | | | **3.41x** |

Average is 3.26x on `_full` inputs and 3.56x on `_q32` inputs -- the bucketed algorithm benefits
from quantized input too (fewer distinct colors means fewer, larger buckets), but it delivers a
solid 2.4-4.2x even on unquantized `_full` thumbnails with 34-121 colors, because vertical run
merging and RLE reduce the *fill* count regardless of color count.

### Quantization alone (bucketed algorithm, full input -> q32 input)

| Model | Bucketed on full | Bucketed on q32 | Gain |
|---|---:|---:|---:|
| test_1 | 2.75s | 2.66s | 1.03x |
| test_2 | 3.18s | 3.07s | 1.04x |
| test_3 | 5.02s | 4.66s | 1.08x |
| test_4 | 2.69s | 2.50s | 1.08x |
| test_5m | 2.40s | 2.05s | 1.17x |
| test_6 | 3.07s | 3.05s | 1.01x |
| test_7 | 3.44s | 3.11s | 1.11x |
| test_8 | 3.96s | 3.62s | 1.09x |
| test_9 | 4.46s | 3.64s | 1.23x |
| **Average** | | | **1.09x** |

Isolated from the algorithm change, quantization alone is a modest ~9% win on top of the
bucketed algorithm -- palette sets are already down to double digits after bucketing even on
`_full` input, so there's less headroom left for quantization to reclaim there. This does **not**
mean quantization is unimportant: see the end-to-end numbers below, and note `_full` palette-set
counts (34-121) are themselves the *result* of `SLIC3R`/`OrcaSlicer`'s `LANCZOS` resize
manufacturing spurious near-duplicate colors that the bucketing algorithm still has to treat as
distinct -- quantization's real payoff is realized jointly with bucketing, not independently of it.

### End-to-end (old script + old algorithm -> new script + new algorithm)

The number that matters for a user upgrading both the slicer post-processing script and the
firmware together:

| Model | Old (naive, full) | New (bucketed, q32) | Speedup |
|---|---:|---:|---:|
| test_1 | 9.73s | 2.66s | 3.66x |
| test_2 | 11.14s | 3.07s | 3.63x |
| test_3 | 16.12s | 4.66s | 3.46x |
| test_4 | 9.51s | 2.50s | 3.80x |
| test_5m | 10.08s | 2.05s | 4.92x |
| test_6 | 10.17s | 3.05s | 3.33x |
| test_7 | 10.38s | 3.11s | 3.34x |
| test_8 | 9.69s | 3.62s | 2.68x |
| test_9 | 11.46s | 3.64s | 3.15x |
| **Average** | | | **3.55x** |

## Interpretation

- The **bucketed rendering algorithm is the dominant contributor** (~3.4x on its own), and it
  helps regardless of whether the embedded thumbnail was quantized -- run merging and RLE reduce
  fill-command count independent of color count.
- **Quantization's contribution measured in isolation is smaller than expected from earlier
  (unvalidated) estimates** -- about 9% on top of an already-bucketed render, not the dominant
  lever previously claimed in this document. It still matters: it reduces `_full`'s 34-121
  spurious colors down to <=32 real ones, which is why `_q32` bucketed runs consistently beat
  `_full` bucketed runs, and it costs nothing to keep (no MCU-side cost, pure slicer-side
  preprocessing).
- Combined, upgrading both the slicer script and the firmware turns an 8-20s block into
  2.0-5.0s -- solidly inside the sub-10s target for One Click Print.

## Reproducing

```sh
# Rebuild the host-side tools from this branch's dwin_wire.h
g++ -O2 -std=c++17 -o dwin_replay dwin_replay.cpp
g++ -O2 -std=c++17 -o dwin_stress dwin_stress.cpp

# Generate command lists directly from a file's RAW16 block (not the
# cosmetic base64 preview -- see thumb_raw16.py)
python3 - <<'PYEOF'
import sys; sys.path.insert(0, ".")
from thumb_raw16 import load_thumb_raw16
import dump_thumb_commands as dtc
img = load_thumb_raw16("test_1_full.gcode")
# naive: dtc.simulate_naive(img)   bucketed: dtc.simulate(img)
PYEOF

# Replay against the panel with the committed throttle
./dwin_replay --port /dev/ttyUSB0 --file <commands.txt> \
    --batch-size 10 --batch-delay-ms 16 --clear
```
