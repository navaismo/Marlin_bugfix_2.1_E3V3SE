# C13 host-only cleanup: implementation and validation

Date: 2026-11-08. Marlin branch: `c13_octoprint_cleanup`, starting at
`244be9d8012cca3c4eb1efbfa084f1f9df0fa1d4`. Plugin branch: `main_cleanup`,
starting at `9d28be81958c37b8c2606e29e32648b208a0f537`. Both started clean.
No branches, commits, merges, pushes, PRs, plugin installations or hardware
flashes were performed. The deleted rendering architecture was not merged.

Current source note: the extra Progress caption draw call is now commented out
following reported host-print timeouts/checksum resends. This is an isolation
step; the cause is unconfirmed. The build, memory and caption test evidence
below predates that one-line change. No new physical stability result or
post-disable memory measurement is claimed. Current overviews are in README.md
and the paired plugin README.

## Architecture and scope

The native Creality MAIN artwork, encoder navigation, ThumbTune, pause/continue,
stop icons and confirmation dialogs remain. MAIN Print now opens a native
“Upload to Host / and start from there” screen with encoder Back. ThumbTune
still draws below the thumbnail. Native thermal status stays in Marlin.

`SDSUPPORT` is disabled. SD G-code handlers, CardReader, sector/file state,
file selection/preview, RAW16 decoder and the 512-run store are absent from the
linked firmware. SD-only code is conditionally excluded, so shared upstream
storage/driver sources remain usable by other configurations. The generic
native print fallback is retained: its Tune and progress routines also serve
non-thumbnail host/safety return paths and are not exclusively SD consumers.
PLR was already disabled and does not recover streamed host jobs. Its SD-only
workflow option and one-click-print option were removed on this branch.

The old 96-word OctoPrint line buffer and START/C/END per-pixel path are excluded
when M9001 v2 is active. No full framebuffer or image-sized MCU allocation is
introduced. The original TJC transmission functions are byte-for-byte unchanged;
the only change in dwin_lcd.cpp gates its SD metadata parser with HAS_MEDIA.

The pin map, IIC BL24CXX EEPROM and 0x7000 bootloader offset are unchanged. The
vector remains at **0x08007000**. Firmware SD updates are performed by the existing
bootloader, independently of Marlin SDSUPPORT. This remains a hardware-validation
item; no firmware update was attempted. Filament handling, probing, Auto Z,
resonance/Pinput and motion algorithms were not edited (39 protected source
files match their initial hashes).

The host performs resize/letterbox, alpha-over-black composition, RGB565
conversion, horizontal runs, vertical merging and disjoint color bucketing.
Black pixels are omitted after initialization. A STRIP fallback carries up to
19 RGB565 pixels for high-entropy images, only when it cannot increase LCD work
and reduces operation bytes. The host renders the green thumbnail frame and image
once, inside **x=10..109, y=25..122**, leaving native progress untouched. This small reserved region avoids global
screen ownership, MAIN replacement and recurring heartbeats.

M9001 v2 accepts a nonzero session, CRC32-protected batches of at most 42 payload
bytes, sequence numbers and a final stream CRC. COLOR/RECT/STRIP operations are
fully validated before copying/executing a batch. Immediately repeated DATA is
idempotent. Every batch earns one application credit after incremental execution;
there is no per-primitive acknowledgment. Ordinary G-code `ok` is not a render
completion notice. END requires a freshly drained TJC handshake response including
its tail and a 50 ms settle. Firmware-specific fence behavior on the physical
panel still needs validation.

The executor submits at most one frame per tick, only if UART space is available.
It observes a wire-time deadline including already queued native bytes and keeps
the proven 16 ms pause after each ten TJC frames across batches/sessions. There
are no blocking delays, flush waits or UART-buffer increases. Thermal, motion and
watchdog services continue through the existing main loop. Any encoder action,
other non-status G-code or lost UI context cancels drawing before further output.
Five-second progress and two-minute session deadlines bound failure recovery.
A preheated printer is accepted when stationary: thermal timer autostart alone
is not treated as active movement. Queued motion, pauses and user prompts still
reject drawing, and arriving movement commands preempt it.

The plugin negotiates once per connection. A single worker holds one counted
OctoPrint file-stream hold during preparation/rendering. The synchronous
beforePrintStarted hook reads the actual current job (FileSelected delivery is
asynchronous) and acquires the hold before job scripts/file commands. Plugin
commands use the ordinary connection. Success, failure, cancellation and disconnect
release only that worker's hold. Rendering never pauses/resumes the job, invokes
pause scripts, answers M876 or releases another plugin's hold. Native host-control
hooks and M600 prompt ownership remain intact. Resuming a physically disconnected
serial host job necessarily requires the host connection.

M9000 supplies filename, total layers, known layer height and the fixed total
estimated minutes (E). M73 L supplies current layers. M73 R continues to represent
live remaining minutes, independently of the fixed ETA row. Marlin's timer
supplies elapsed time; native thermal state supplies temperatures. HEIGHT is layer thickness,
not Z position or model height. No layer count is inferred from Z hops. Missing
data use placeholders; current layer progress requires actual slicer M73 L
output as in the stable firmware. Each dynamic field is checked once per roughly
five seconds, one field every 1.25 s, and drawn only when changed. Tune and safety
screens suppress these updates. Returning from Tune restores the four cyan row labels, native values
and controls below the thumbnail/progress, preserving the thumbnail and frame. No active-print full-screen image is sent.

Full protocol details and plugin instructions are in the paired plugin's
`docs/host-only-rendering.md`.

## LCD layout correction after hardware feedback

The supplied hardware photo showed the old right-hand metadata grid overlapping
native progress, and its top frame edge being erased by the scrolling filename.
The grid is removed. Host operations now touch only x=10..109, y=25..122:
96x96 image at (12,26), green frame drawn last, with all four edges below the
title's y=24 clear and above Tune's y=123 clear. Native progress stays at the
original right-hand position. The protocol validates y=25..122 on both peers.
Use the matching firmware and plugin sources together.

Marlin draws plain Layers, Layer Height, ETA and Elapsed rows at y=127/143/159/175.
The labels are cyan (0x07FF), values white and centered in x=124..233, with no surrounding table.
Periodic refresh still checks one field every 1250 ms and redraws only changes;
Tune and popups suppress it. Goto_ThumbPrint(false) restores every label/value
on return without resetting progress or transmitting the image again.

Confirmed native Stop sends the existing host cancellation actions, clears the
card and opens MAIN even for a selected file that is not printing yet. The
plugin cancels the preview worker, drops pending rendering and releases only
its own counted hold. It calls cancel_print only for a printing/paused host job.
Declining Stop restores the card. Local edits to icon outlines and the MAIN
connection indicator are preserved.

Verification: 14 ASan/UBSan decoder/executor tests, 4 Python/MCU integration tests,
native row-position/cyan/Tune-return/Stop tests, and the existing pause, runout,
thumbnail-progress, calibration, menu-exit and AutoOffset regressions pass.
All 43 distinct plugin tests pass across the local host Python (15 pass, 28 skip)
and real offline OctoPrint container (42 pass, 1 skip for Pillow); this includes
idle-preview Stop and retention of another plugin's job hold.
The integration replay checks all 9216 pixels and each frame edge, and confirms
that the title, progress area and lower rows are untouched by host operations.
See [current build evidence](c13-cleanup/card-layout.json) and
[current transport replay](c13-cleanup/card-layout-transport.json). Its
reference thumbnail plus frame uses 1000 TJC frames (previous grid: 1113),
with unchanged transport pacing. Physical display validation remains pending:
check the four labels, scrolling filename/frame, live progress, Tune return and
both idle-preview and active-print Stop on the printer.

Initial layout-correction STM32F103RET6_creality build: **22620 bytes RAM (34.5%), 211392 bytes
Flash (42.7%)**. RAM matches the initial cleanup below; current Flash is 120 bytes
higher, including the retained local UI edits. This is a source build, with no
flashing, plugin installation, commit or push. The next section preserves the
initial cleanup's measured phase comparison.

### Centered values and cached layer-height recovery

The second hardware photo showed that the old x=104 value clear erased the
end of Layer Height. Value clears now start at x=120 and cover the full 16-pixel
cell. Values are centered in x=124..233 using a conservative 8-pixel glyph width.
The widest supported layer counter, `65535 / 65535`, remains intact at x=127..230;
labels end before the clear area. Native tests also cover maximum elapsed/ETA,
layer height, shorter replacement values and restoration from Tune.

The height parser accepts the exact nominal layer-height key in Orca's trailing
settings after EXECUTABLE_BLOCK_END, with the last valid value taking priority.
First-layer, support and min/max height settings are excluded. The original
parser already accepted the simple trailing key; the missing behavior was
recovery from older cached JSON. Before drawing, the plugin now repairs missing
or unusable cached heights from the stored local file, preserving other fields
and caching successful recovery. It resolves subdirectory paths through the
OctoPrint file manager and reads at most 64 KiB of footer plus, when needed,
64 KiB of header. Valid cached heights require no file reads. Missing data
continue to use a placeholder, and a cancelled generation cannot save/send its
recovery. Existing files do not need to be uploaded again.

Eight added plugin regressions cover footer/header priority, exact keys and
invalid values, cached recovery/persistence, valid-cache reuse, unavailable
files, cancellation and upload-time parsing. The production reader also returned
0.2 mm on four existing local G-codes, including a 38,769,517-byte file.
Layer-height correction build: **22620 bytes RAM (34.5%), 211400 bytes Flash (42.7%)**,
8 more Flash bytes than the first layout correction, with static RAM unchanged.
See [current evidence](c13-cleanup/fields-height.json). Physical alignment and
layer-height display still need confirmation on the printer. No flashing,
plugin installation, commit or push was performed.

### Fixed ETA, two-color layers and cube caption

ETA now means the job's initial total estimated duration, formatted HH:MM and
colored yellow. The plugin sends M9000 E<minutes> once before S1, from the cached
initial M73 P0 R estimate. Later M73 R time-left changes do not affect that total.
Elapsed remains the live Marlin print timer in white. Unknown estimates send E0
and show --, and MAIN clears the previous job's total. Legacy M9000 T elapsed-time
handling is preserved independently. Tune and finish views keep the initial ETA.

The layer row draws its current count and slash in white and its total count in
yellow. The complete row remains centered, with both uint16_t counters fitting
as `65535 / 65535`; the yellow total begins after the white separator without
losing digits. Cyan labels and the white layer-height value remain unchanged.

A cyan Progress caption is drawn at (139,107), centered below the cube and ending
at y=122, above Tune and the first metadata row. The local 101 replacement cube
resources are 92x92; their visible colored artwork ends at screen y=105. Caption
position targets those cube assets. It is drawn after every native progress
resource refresh, including return/completion, because the resource background
would otherwise erase part of the caption. No asset or TJC driver was changed.

Native replay exercises the production M9000 parser, fixed ETA versus changing
remaining time, advancing elapsed time, split colors, maximum counters/times,
unknown/reset estimates, caption position/order, Tune/finish and Stop. Two added
plugin tests verify the initial E command precedes S1, time-left updates do not
resend it, and invalid/unknown estimates reset E0. Full regressions pass.
Current build: **22620 bytes RAM (34.5%), 211528 bytes Flash (42.7%)**: RAM unchanged,
Flash +128 bytes from the layer-height correction. See
[static ETA build evidence](c13-cleanup/static-eta.json). Confirm the colors,
fixed HH:MM ETA, advancing elapsed time and caption on the physical LCD.

## Compiled memory

Target: STM32F103RET6_creality, ststm32 17.1.0, STM32duino 2.6.0, GCC 12.3.1.
Final production build was cleaned and compiled from source. ELF/map/bin and
compiler stack evidence are retained under `.pio/c13-cleanup/`.

| Stage | RAM bytes | RAM % | Flash bytes | Flash % |
|---|---:|---:|---:|---:|
| Original baseline | 28260 | 43.1 | 245964 | 49.6 |
| SD printing removed | 22704 | 34.6 | 209204 | 42.2 |
| M9001 optimized | 22592 | 34.5 | 210660 | 42.5 |
| Final cleanup | 22620 | 34.5 | 211272 | 42.6 |

Phase C separately measured **22612 RAM / 210712 Flash** before final STRIP,
fence and context refinements. Relative to the original baseline the final
change saves **5640 RAM bytes and 34692 Flash bytes**. Relative to the historical
experimental 24628-byte target, it uses **2008 fewer RAM bytes**.

ELF .data/.bss: baseline **1084 / 27176**, phase A **704 / 22000**, phase B
**704 / 21888**, phase C **716 / 21896**, final **716 / 21904**. The persistent
executor symbol is **76 bytes**. No thumb_runs, row index stores, emission bitmap,
OctoImageLine or CardReader symbols remain. Detailed sections and symbols are in
[memory.json](c13-cleanup/memory.json).

Flash in the table uses PlatformIO's .text + .rodata + .data convention. Actual
allocated load sections also contain vector/init/fini/unwind data: baseline
246572 bytes, final 211872 bytes. This distinction explains the additional
608/600 bytes; it does not change the reported application-size definition.

Compiler stack frames, separately recompiled with -fno-lto -fstack-usage:
M9001 command **112 B**, tick **48 B**, UART send **24 B**, response **88 B**,
field draw **64 B**, field refresh **16 B**. These are individual frames, not
nested call-chain/interrupt maxima. The 1536-byte linker heap/stack reservation
is unchanged. **Peak runtime stack/heap usage has not been measured.**

EEPROM remains **V93, 787 bytes, 64 fields and 134 serialization operations**,
matching the starting revision. See [eeprom.json](c13-cleanup/eeprom.json).
The sole production compiler warning about FTM_SHAPER_E predates this work and
is intentionally unchanged.

## Initial transport measurements and limitations

The counts below record the initial cleanup layout. The current thumbnail/frame
layout replay is in [card-layout-transport.json](c13-cleanup/card-layout-transport.json).

The retained 96x96 thumbnail fixture is replayed through the actual Python
sender and C++ executor with ASan/UBSan. All **9216 output pixels match exactly**.
The comparison below includes START/END or BEGIN/END and uses numbered lines;
connection negotiation is excluded equally. MeatPack uses the real local encoder
in NSP mode. These byte counts are measurements, not baud-rate estimates.

| Metric, reference thumbnail | Original | Optimized |
|---|---:|---:|
| ASCII bytes, without line numbers | 48230 | 9508 |
| Numbered/checksummed bytes | 54362 | 10431 |
| Actual MeatPack encoded bytes | 36609 | 13203 |
| G-code commands / normal ok replies | 770 | 127 |
| Application replies | 99 | 127 |
| Drawing operations | 1907 pixels | 994 operations |
| TJC frames, including final new fence | 3814 | 995 |

The optimized application-reply count is deliberately higher for this fixture:
credits now bound queued work and enable retry/recovery. They are per batch,
not per pixel or rectangle. Solid colors need three total transfer commands
and five TJC frames, versus 770 commands and 18432 TJC frames in the old
per-pixel path. Baseline idle-mode transfers use 20-pixel chunks (482 commands);
numbered-print transfers use 12 (770). Both are recorded in
[transport.json](c13-cleanup/transport.json).

For the same reference drawing operations, 24-byte HEX batches need **242 DATA
commands / 18940 numbered bytes / 12939 MeatPack bytes**; the chosen 42-byte
encoding needs **125 / 10370 / 13131**. It approximately halves DATA command
and credit overhead at a 192-byte MeatPack cost on this fixture. HEX remains
slightly denser with MeatPack for some artwork. The chosen encoding is standard
Base64 with uppercase G replaced by underscore: the existing MeatPack encoder
otherwise mistakes an in-payload G followed by a digit for G-code, rewrites
characters/spaces and corrupts standard Base64. Both actual MeatPack modes are
round-trip tested; no MeatPack implementation or core parser changes were made.

**High-entropy limitation:** 9216 distinct colors require 18435 new TJC frames
versus 18432 old ones (initialization/fence overhead). STRIP reduces numbered
host bytes from **54295 to 46160**, but actual MeatPack bytes rise from **42730
to 58613**, and application replies rise from 99 to 579. Highly noisy images
therefore have a measured transport regression; they cannot gain rectangle
merging without changing pixels. This is not hidden by the representative
thumbnail improvement. An all-black image adds initialization/fence operations
compared with the old skipped-pixel path.

For the final reference run, the original sender needed **1.47 ms** to build
and submit commands to a local capture stub; the new host needed **1.14 ms**
for run/rectangle preparation plus **0.35 ms** for packet encoding. The complete
new Python/C++ local harness round trip took **4.33 ms**. These are different
CPU/IPC stages, not comparable physical transfer durations; individual runs vary.
Host preparation and Python/C++ IPC wall times are recorded per fixture in JSON.
They measure host computation and the local harness, **not serial throughput or
physical LCD completion**. The harness clock is simulated. No new physical render
time, print-quality improvement or absence of hardware planner stalls is claimed.
The actual printer-to-display wire bytes, ten-frame pacing and panel processing
can be the dominant cost; ASCII alone does not explain performance.

The [host-card preview](c13-cleanup/host-card.png) shows only the new host-owned
240x98 region. Native ROM icons/controls are deliberately not emulated in it.

## Reference analysis

Read-only Klipper evidence comes from the locally retained master snapshot
`7f6b9fd7e6d5f13e871cc73d842b0d0e0b8c5f69` (captured 2026-11-07), under
`.pio/m9001-tjc-audit/reference/`. No claim is made that it is today's remote
master. Its tjc_draw.c, tjc_lcd.c and lcd_draw.py establish small binary commands,
CRC/order checks, one cooperative task, palette reuse, filled rectangles,
ten-frame/16 ms pacing and a final handshake fence. Marlin can reuse those
concepts; Klipper's MCU scheduler, binary RPC and host reactor are not drop-in
Marlin transports. The reverse-engineering source was used only to cross-check
frame/resource formats; no project or TJC resources were changed.

The existing SD renderer provided the exact horizontal-run, vertical-merge,
background omission and color-bucketing algorithms. Their image analysis moved
to the host, rather than retaining its 512-run MCU allocation. Previous M9001
source and measurements were inspected in the retained evidence archive as design
evidence. No old ownership, MAIN registration, heartbeat or paused-start worker
architecture was restored.

## Tests and hardware checklist

Automated: **14** ASan/UBSan protocol tests; **4** host/production-executor integration
tests including actual MeatPack both modes; native MAIN/Print/Back/field/encoder
replay; preserved native control-function comparison; seven existing regressions
covering advanced pause, purge, thumbnail progress, runout ownership, calibration
failure, manual move and AutoOffset safety; EEPROM/profile checks; plugin raster,
client, lifecycle, API and frontend tests. Full command/results are in
[tests.json](c13-cleanup/tests.json), with logs under `.pio/c13-cleanup/logs/`.
The 43 distinct plugin cases pass across the two environments: 42 in the
OctoPrint container plus the actual Pillow raster case on host Python.
The OctoPrint container supplies the real plugin interfaces; its unavailable
Pillow import is stubbed only there. Actual Pillow resizing/alpha/RGB565 tests run
separately on host Python. Physical hardware remains untested.

Reproduce with matching plugin source available:

```sh
python3 buildroot/tests/c13_cleanup/validate.py --plugin-root /path/to/plugin
M9001_PLUGIN_ROOT=/path/to/plugin python3 buildroot/tests/c13_cleanup/benchmark.py
pio run -e STM32F103RET6_creality -t clean
pio run -e STM32F103RET6_creality
pio run -e STM32F103RET6_creality -t compiledb
python3 buildroot/tests/c13_cleanup/measure.py
```

Hardware validation still required:

1. Cold boot and the existing SD firmware-update procedure; Print/Back and every
   native menu on the physical display.
2. Start selected/direct jobs, missing/invalid thumbnails, layout readability,
   real M73 layer/ETA and local elapsed/thermal values.
3. Long prints and repeated batches: measure physical render time and UART/planner
   responsiveness; check print quality, heaters and emergency command handling.
4. Tune entry/scroll/exit without losing the thumbnail; native pause/resume and
   both stop-dialog selections; retain the existing pause scripts.
5. M600/runout/user prompts during transfer, another plugin's job hold, serial
   unplug/reconnect, retries, cancellation and unresponsive LCD. Resuming a
   disconnected serial job is a host operation.
6. Stack high-water/interrupt headroom under combined motion, thermal, menus and
   transfer activity. Static RAM savings alone do not establish runtime peak.

SD printing is inaccessible in both LCD and compiled G-code dispatch. GUI and
streaming cases above are automated at the stated harness/API level, not through
an attached USB printer or actual ROM display. No tests are presented as physical
validation.

## Modified files

Marlin workspace (all changes remain uncommitted):

| File | Purpose |
|---|---|
| `.github/workflows/build-marlin.yml` | Keep required host layout enabled; remove SD-only build choices. |
| `MEMORY.md` | Record branch-specific architecture, memory and validation state. |
| `Marlin/Configuration.h` | Disable firmware SD printing. |
| `Marlin/Configuration_adv.h` | Enable bounded host protocol; preserve encoder sound without SD. |
| `Marlin/src/MarlinCore.cpp` | Service one cooperative drawing tick from idle. |
| `Marlin/src/e3v3se/LcdDraw.cpp` | CRC, bounds, sequence, retry, timeout, execution and fence state machine. |
| `Marlin/src/e3v3se/LcdDraw.h` | Small protocol/IO interface. |
| `Marlin/src/e3v3se/LcdDrawIO.cpp` | UART-space-aware TJC frames and native context checks. |
| `Marlin/src/e3v3se/OctoHost.cpp` | Dispatch v2, metadata and staggered native values; guard print-card entry. |
| `Marlin/src/e3v3se/OctoHost.h` | Expose the native metadata refresh interface. |
| `Marlin/src/e3v3se/ThumbRender.cpp` | Exclude the SD RAW16/run renderer without media. |
| `Marlin/src/gcode/gcode.cpp` | Cancel drawing before unrelated commands can run. |
| `Marlin/src/inc/SanityCheck.h` | Allow host-only Creality UI; validate protocol configuration. |
| `Marlin/src/lcd/dwin/creality/dwin.cpp` | Gate SD consumers; Print/Back message; integrate native values and preemption. |
| `Marlin/src/lcd/dwin/creality/dwin_lcd.cpp` | Guard only SD metadata parser; transport functions unchanged. |
| `README.md` | Describe this host-only branch and supported build options. |
| `buildroot/share/e3v3se/baseline.json` | Record measured production build budget. |
| `buildroot/share/e3v3se/profiles/c13_octoprint/overrides.txt` | Derived disabled-SDSUPPORT profile state. |
| `buildroot/share/e3v3se/profiles/c13_octoprint/residual.Configuration_adv.h.patch` | Regenerated host-protocol and independent-beep profile. |
| `buildroot/tests/c13_cleanup/benchmark.py` | Actual sender/executor, baseline sender, wire counts and raster comparison. |
| `buildroot/tests/c13_cleanup/measure.py` | Linked sections/symbols and per-function compiler stack evidence. |
| `buildroot/tests/c13_cleanup/validate.py` | Focused reproducible regression runner. |
| `docs/c13-cleanup.md` | Architecture, measurements, full file list and hardware-validation record. |
| `docs/c13-cleanup/eeprom.json` | EEPROM layout and serialization evidence. |
| `docs/c13-cleanup/host-card.png` | Preview of only the host-owned print-card region. |
| `docs/c13-cleanup/memory.json` | Linked section/symbol and stack-frame measurements. |
| `docs/c13-cleanup/tests.json` | Exact focused test commands, return codes and log paths. |
| `docs/c13-cleanup/transport.json` | Per-fixture bytes, operations, replies, host timings and pixel results. |
| `platformio.ini` | Compile the fork-owned executor and IO adapter. |
| `test/c13_cleanup/harness.cpp` | Native clock, UART, frame and response harness. |
| `test/c13_cleanup/thumbnail.png` | Retained 96x96 exact-pixel reference fixture. |
| `test/test_c13_cleanup_integration.py` | Actual Python-to-C++ path and both actual MeatPack modes. |
| `test/test_c13_cleanup_protocol.py` | ASan/UBSan decoder, bounds, pacing, retry and fence cases. |
| `test/test_c13_cleanup_ui.py` | Production navigation, unchanged controls, field placement and context replay. |
| `test/test_dwin_runout_owner.py` | Explicitly retain media-enabled legacy fixture coverage after adding media guards. |

Paired plugin workspace (`main_cleanup`):

| File | Purpose |
|---|---|
| `README.md` | Replace obsolete pause-start instructions with the hold-based pipeline. |
| `MANIFEST.in` | Package renderer documentation and regression tests. |
| `octoprint_LCD_E3V3SE/__init__.py` | Single render worker, synchronous job hold, actual-job race handling and lifecycle integration. |
| `octoprint_LCD_E3V3SE/drawing.py` | Bounded G-free Base64/CRC transport, credit, retries, abort and completion. |
| `octoprint_LCD_E3V3SE/print_card.py` | Exact host raster optimization, green thumbnail frame and high-entropy fallback. |
| `tests/test_drawing.py` | Raster, background, resize, framing, retry and credit regressions. |
| `tests/test_print_lifecycle.py` | Start races, counted holds, prompts, disconnect, bad metadata and controls. |
| `docs/host-only-rendering.md` | Paired protocol, rendering, metadata, lifecycle and validation guide. |

The generated residual patch contains two new empty context lines whose literal
space is unified-diff syntax; git diff --check reports those context markers.
Source/doc whitespace checks and the exact profile round-trip check pass.
