# Real menu screenshots

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

The website **automatically** uses a local PNG when present. If missing and a historical,
authentic GIF exists in the project's `media/` folder, it displays that GIF. Otherwise
it displays an explicitly labeled screenshot placeholder. It never fabricates LCD UI.

Paths in `app.js` → `screenGuides` are based on `Marlin/src/lcd/dwin/creality/dwin.cpp`
in the `c13_sd` branch as of 2026-11-12. Check changed menus against the build in hand.

For best results, capture screens straight-on, crop to the display area, and avoid glare.
