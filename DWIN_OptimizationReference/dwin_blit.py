"""Encode a PIL image into DWIN drawing commands, three ways, so they can be
timed against each other on real hardware (see dwin_bench.py):

- blit_naive: one fill-rect (1x1) per pixel, palette re-sent every time.
  This mirrors Marlin's current DWIN_RenderThumb / DWIN_Draw_Rectangle
  behaviour (dwin_lcd.cpp) byte for byte -- it is the "before" baseline.
- blit_rle: palette sent only when the color changes, each row's runs of
  equal-color pixels collapsed into a single fill-rect.
- blit_bucketed (Phase 2): groups runs by color across the WHOLE image so the
  palette is set once per distinct color rather than once per run. Real
  decoded G-code thumbnails (thumb_raw16.py) measured ~69 distinct colors
  with a palette switch on almost every run (69 colors but 1200-1500 runs) --
  plain per-row RLE only won ~1.4-1.6x there, while bucket-sorting nearly
  doubled that to ~2.7-3x. It costs real RAM on an embedded target (see
  AGENTS.md / the plan, ~6KB for a 96x96 thumbnail) because it must hold
  every run for the whole image before emitting anything, unlike the
  streaming row-by-row RLE.

Background pixels (matching `skip_color`, black by default -- the model
thumbnails this targets are a flat-shaded silhouette on solid black) are
skipped entirely in all three, matching the existing `color == 0` skip in
DWIN_RenderThumb.

None of these functions sleep or take a `delay` parameter: throttling lives
in tjc_dwin.Panel(delay=...), applied once per wire frame inside send(). Do
NOT re-add per-call delays here -- that was tried and produced a silently
unfair naive-vs-rle comparison (blit_naive delayed once per pixel while its
underlying fill_rect() call emits two frames per pixel; blit_rle/blit_bucketed
delayed once per frame), inflating naive's wall time and understating the
real speedup. Confirmed on hardware this session.
"""


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def _rows(img, skip_color=(0, 0, 0)):
    """Yield (y, [(x0, x1, color565), ...]) for each row, background-skipped
    pixels simply absent from the run list."""
    w, h = img.size
    px = img.load()
    for y in range(h):
        runs = []
        x = 0
        while x < w:
            c = px[x, y]
            if c[:3] == skip_color:
                x += 1
                continue
            x2 = x
            while x2 + 1 < w and px[x2 + 1, y][:3] == c[:3]:
                x2 += 1
            runs.append((x, x2, rgb565(*c[:3])))
            x = x2 + 1
        yield y, runs


def blit_naive(panel, img, x_off=0, y_off=0, skip_color=(0, 0, 0)):
    """One command pair (palette + 1x1 fill) per foreground pixel. Baseline
    matching Marlin's current per-pixel DWIN_Draw_Rectangle loop."""
    n = 0
    for y, runs in _rows(img, skip_color):
        for x0, x1, color in runs:
            for x in range(x0, x1 + 1):
                px = x_off + x
                py = y_off + y
                panel.fill_rect(color, px, py, px, py)  # 2 frames: palette + rect
                n += 2
    return n


def blit_rle(panel, img, x_off=0, y_off=0, skip_color=(0, 0, 0)):
    """Palette sent only on color change; each run collapsed to one fill-rect."""
    n = 0
    last_color = None
    for y, runs in _rows(img, skip_color):
        for x0, x1, color in runs:
            if color != last_color:
                panel.set_palette(color)
                last_color = color
                n += 1
            panel.send(
                0x5B,
                _word(x_off + x0) + _word(y_off + y) + _word(x_off + x1) + _word(y_off + y),
            )
            n += 1
    return n


def blit_bucketed(panel, img, x_off=0, y_off=0, skip_color=(0, 0, 0)):
    """Phase 2: collect every run across the whole image first, group by
    color, then emit one palette-set per distinct color followed by all its
    runs. Same visual result as blit_rle, fewer palette switches.

    Costs O(runs) memory to hold the whole run list before emitting anything
    -- fine on the host, a real budget item on the embedded target (see
    AGENTS.md). Not a streaming encoder.
    """
    n = 0
    buckets = {}  # color -> list of (x0, x1, y)
    for y, runs in _rows(img, skip_color):
        for x0, x1, color in runs:
            buckets.setdefault(color, []).append((x0, x1, y))

    for color, run_list in buckets.items():
        panel.set_palette(color)
        n += 1
        for x0, x1, y in run_list:
            panel.send(
                0x5B,
                _word(x_off + x0) + _word(y_off + y) + _word(x_off + x1) + _word(y_off + y),
            )
            n += 1
    return n


def _word(v):
    return bytes(((v >> 8) & 0xFF, v & 0xFF))
