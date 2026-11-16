# Real menu screenshots and videos

`filament-change-collage.svg` embeds the four supplied M600 photographs as a
numbered 2 × 2 collage. The original JPEG data is preserved inside the SVG;
the layout crops the lower printer bezel while keeping the LCD screens visible.
Read left to right, then top to bottom, in capture-time order:

1. `20261115_195648.jpg`: unloading filament.
2. `20261115_195655.jpg`: insert filament and press the knob.
3. `20261115_195710.jpg`: purging filament.
4. `20261115_195722.jpg`: purge more or resume.

The M600 card follows Display Settings in every guide variant and language.
Click the collage or enlarge button to view it in the page dialog.
The command explanation follows the photographed prompts and the
[official Marlin M600 documentation](https://marlinfw.org/docs/gcode/M600.html).

The supplied menu videos are included as local MP4 files:

- `bed-map.mp4`: `bedlevel.mp4`, visual bed map.
- `e-steps.mp4`: `esteps.mp4`, extruder steps per millimeter.
- `motion.mp4`: `speed.mp4`, motion speed settings.
- `power-loss.mp4`: `plr.mp4`, power-loss recovery.

These four cards play their videos automatically, muted, inline, and in a loop.
Click the preview or enlarge button to watch the video in the page dialog.
The enlarged player includes playback controls and stops when closed.
The original files were copied unchanged from the supplied `DL_Local` folder.

Drop **actual screenshots/photos** here. Name them exactly as follows.

First steps:
- `auto-z.png`
- `bed-leveling.png`
- `e-steps.png`
- `motion.png`

Optional or extended menus:
- `display-settings.png`
- `bed-map.png`
- `custom-extrude.png`
- `homing-height.png`
- `preheat-labels.png`
- `skew-correction.png`
- `legacy-shaping.png`
- `power-loss.png`

For cards without an assigned video, the website **automatically** uses a local PNG when present. If missing and a historical,
authentic GIF exists in the project's `media/` folder, it displays that GIF. Otherwise
it displays an explicitly labeled screenshot placeholder. It never fabricates LCD UI.

Paths in `app.js` → `screenGuides` are based on `Marlin/src/lcd/dwin/creality/dwin.cpp`
in the `c13_sd` branch as of 2026-11-12. Check changed menus against the build in hand.

For best results, capture screens straight-on, crop to the display area, and avoid glare.
