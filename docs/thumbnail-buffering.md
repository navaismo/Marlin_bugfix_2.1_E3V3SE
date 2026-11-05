# Thumbnail bounds correction and batching

The renderer accepts up to 96 pixels per row. Adjacent nonzero colors can each
start a run, so the maximum is 96 runs, rather than 48. Both arrays of open
vertical-merge indices must hold that many entries.

The correction reserves an entire worst-case row before its first write. If
the remaining batch cannot hold 96 new runs, it emits the completed batch and
clears its open-row indices. A compile-time assertion requires capacity for at
least one full row. Because the input width is clamped to 96, the reservation
bounds every run and merge-index write in that row. There is no mid-row flush
that could leave an index pointing to an emitted batch.

The first change keeps the 1536-run buffer. It changes neither pixel colors nor
the palette/fill commands: runs still merge vertically by matching span and
color, and each batch is emitted by color. Background pixels remain untouched.
Truncated input emits only complete rows already accepted, as before.

## Phase 1 measurements

Fresh `STM32F103RET6_creality` builds from one frozen development-workspace
snapshot, with identical configuration, flags and dependencies:

| Version | Static RAM (`.data + .bss`) | Flash (PlatformIO) |
| --- | ---: | ---: |
| Original 1536-run renderer | 34,540 B | 253,268 B |
| Bounds correction, still 1536 runs | 34,732 B | 253,260 B |
| Difference | +192 B | −8 B |

The RAM increase is exactly the two open-index arrays growing from 96 to 192 B
each. `.data` remains 1,084 B; `.bss` grows from 33,456 to 33,648 B. The four
thumbnail arrays total 9,600 B before and 9,792 B after the correction.
These builds use the snapshot taken for this implementation; they are separate
from the earlier audit's configuration and measurements.

Both clean builds succeeded. All 42 ASan/UBSan image cases passed with the
corrected renderer (257,518 captured commands), as did the original reproducer
and the disabled-renderer translation-unit compilation. The saved original
source still reproduces the historical ASan error when requested explicitly.

## Phase 2: 512-run batching

The second change lowers only `MAX_THUMB_RUNS`, from 1536 to 512, retaining the
pre-row reservation and 96-entry open arrays introduced by the bounds fix.
Worst-case rows have 96 runs: a checkerboard batch fits five such rows (480
runs), then flushes before the sixth. Partially filled batches can reach exactly
512 runs; a regression covers that boundary and the following row.

The four scratch arrays now occupy `512*6 + 64 + 2*96*2 = 3,520 B`. Relative to
the bounds-corrected renderer, this recovers 6,272 B; relative to the original
unsafe renderer, it recovers 6,080 B, including the larger open-index arrays.
Merging and palette grouping remain active within each batch. A flush ends
vertical merging at that boundary, as in the original batching design; a run
below the boundary is drawn in a separate rectangle, covering different pixels.
The total command count can therefore increase even when the image is identical.

The expanded suite checks 43 images against their expected source pixels, both
with the phase-1 renderer and the 512-run renderer. It checks every pixel and
its write count, rather than requiring identical rectangle streams across
different batch boundaries. The original 17-row ASan reproducer also passes.

The third clean PlatformIO build succeeded:

| Version | Static RAM | Flash (PlatformIO) |
| --- | ---: | ---: |
| Original renderer | 34,540 B | 253,268 B |
| Bounds-corrected, 1536 runs | 34,732 B | 253,260 B |
| Bounds-corrected, **512 runs** | **28,460 B** | **253,260 B** |
| Batching change versus bounds correction | **−6,272 B** | **0 B** |
| Final versus original renderer | **−6,080 B** | **−8 B** |

The final `.data` is 1,084 B and `.bss` is 27,376 B. ELF symbol differences
attribute the batching savings exactly to `thumb_runs` (−6,144 B) and
`thumb_run_emitted` (−128 B), with no residual padding delta. All other RAM
symbol sizes are unchanged. Configuration, version and PlatformIO settings
hashes match across all three builds; the only differing Marlin source is
`ThumbRender.cpp`. No audit-only compiler flags were added.

Build sizes, configuration/source/ELF/bin hashes and host-test summaries are
recorded in [thumbnail-buffering-measurements.json](thumbnail-buffering-measurements.json).
Local copied configurations, renderer sources, ELF/bin/map and symbol reports
are under `.pio/thumbnail-validation/{baseline,fixed,batched}-artifacts/`;
logs are `.pio/thumbnail-validation/{baseline,fixed,batched}.log`. The isolated
source directories have the corresponding case names. Each build used a new
object directory and the same installed dependencies, with
`pio run -d <isolated-case-directory> -e STM32F103RET6_creality -j 4`.

| Image | Phase 1 palette/fill commands | 512-run palette/fill commands |
| --- | ---: | ---: |
| Solid 96×96 | 1 / 1 | 1 / 1 |
| 96 vertical columns | 2 / 96 | 2 / 96 |
| Checkerboard 96×96 | 12 / 9,216 | 40 / 9,216 |
| 9,216 distinct colors | 9,216 / 9,216 | 9,216 / 9,216 |
| Background-separated merging | 2 / 1,344 | 8 / 1,632 |

Both versions render every expected foreground pixel exactly once and leave
backgrounds unchanged. More fills in the last case reflect shorter vertical
rectangles at batch boundaries. The host pacing model reports a maximum burst
of ten commands and maximum watchdog interval of 17,230 µs for both versions.
Pause counts for individual images can differ by one due to the preserved
throttle counter continuing across renders. These modeled values do not include
CPU processing, SD latency or actual panel behavior.

## Host regression tests

```sh
python3 buildroot/tests/thumbnail/test_thumbnail.py
python3 buildroot/tests/memory_audit/reproduce_thumbnail_overflow.py
```

The tests compile the actual `ThumbRender.cpp` with mocked card, HAL and DWIN
interfaces under AddressSanitizer and UndefinedBehaviorSanitizer. The complete
suite covers 43 images, including 96×96 checkerboards and unique colors,
96 vertically merged columns, solid images, backgrounds, original 1480+96-run
overflow input, truncated rows/EOF, open failures, narrow images and 24 seeded
random images. Each non-background pixel must be written exactly once with the
source color; every background pixel must remain untouched. Palette state is
applied to captured rectangles, rather than comparing two implementations of RLE.
Solid and vertical-stripe cases also assert rectangle counts to verify merging.

The original ASan reproducer now requires both its solid control and its original
overflow input to succeed. To confirm the historical defect against a saved
source, use `--source /path/to/original-ThumbRender.cpp --expect-overflow`.
It must report the original buffer error; this mode is not the default regression
expectation. No printer is involved in these tests.

The runner also compiles the renderer translation unit with thumbnail support
disabled. That is a local compilation check; it does not assert that unrelated
firmware callers support a full configuration with thumbnails disabled.

## Communication pacing

`thumb_throttle`, `thumb_flush_runs`, low-level DWIN serial functions and their
watchdog handling are unchanged. Every palette and rectangle command still
passes through the throttle, which pauses 16 ms after each ten commands and
refreshes the watchdog. Background-only rows also refresh it. Tests assert the
exact pauses, maximum ten-command burst, per-command refresh, and persistence
of the throttle counter across successive render calls.

The unchanged wire formats are 10 bytes for palette and 14 for a rectangle.
Thus a ten-command burst contains at most 140 bytes, with the same 16 ms pause
as before. At 115200 baud, 8N1, that payload alone takes at most about 12.16 ms
on the wire. The host test models serialized wire time plus the existing
1 µs/byte delay; its watchdog gap is a model, not a hardware timing measurement.

These checks establish preservation of the existing pacing policy. They cannot
establish the panel's actual receive/processing margins, UART buffering behavior,
or wall-clock render time. Hardware verification remains required before treating
a changed batching capacity as validated on a particular DWIN panel.

## Hardware validation still required

- From SD, render solid, checkerboard, 96-column stripes, many-color and
  background images repeatedly; inspect colors, row boundaries and full output.
- Exercise OctoPrint `M9000`/`M9001` transfers and print-screen transitions. Those
  handlers, the line buffer and their separate rendering path are unchanged.
- Capture LCD UART traffic to confirm frames, 16 ms pauses and absence of panel
  overruns. Measure total draw time, including images requiring repeated flushes.
- Confirm watchdog servicing, thermal-task behavior during the existing blocking
  render, and subsequent normal printer operation. Test the panel/board combination
  actually used; software timing checks do not validate every display model.

No changes to motion, Input Shaping, FT Motion, M495, Pinput or Auto Z are part
of this work. No hardware was flashed by the implementation or host tests.
