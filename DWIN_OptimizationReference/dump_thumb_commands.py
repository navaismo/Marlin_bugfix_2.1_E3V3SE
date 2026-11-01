#!/usr/bin/env python3
"""Dump the exact DWIN_Set_Color/DWIN_Fill_Rect_Raw command sequence that
Marlin/src/lcd/dwin/creality/dwin_lcd.cpp's DWIN_RenderThumb would issue for
a given thumbnail, as a plain text command list dwin_replay.cpp can replay
over a real serial connection to the panel -- without recompiling/reflashing
Marlin for every delay-tuning experiment.

Two modes, so the new algorithm can be benchmarked against the original on
real hardware:
  --mode bucketed (default): host-side quantize_foreground() + the row-RLE
    + vertical-merge + bucketed-emission algorithm now in DWIN_RenderThumb
    (see verify_blit.py, which this reuses).
  --mode naive: the ORIGINAL DWIN_RenderThumb behavior it replaced -- one
    DWIN_Set_Color + one 1x1 DWIN_Fill_Rect_Raw per foreground pixel, in
    raster order, no quantization. Matches dwin_lcd.cpp before this branch's
    changes, and DWIN_OptimizationReference/dwin_blit.py's blit_naive.

Input can be either a thumbnail PNG (as before) or a real .gcode file --
in the latter case the base64 preview already embedded in the file (by a
slicer, or previously by this same script's RAW16 insertion pass) is
extracted and decoded exactly like orca_parser.py would when generating a
RAW16 block for it, via orca_parser.decode_and_resize().

--relative emits coordinates local to the thumbnail's own (0,0)..(95,95)
origin instead of adding the fixed on-screen THUMB_X_START/THUMB_Y_START
offset -- for a caller (e.g. dwin_stress.cpp) that wants to translate the
same command list to an arbitrary screen position at replay time.

Output format (one command per line):
  S <color_hex>              -- DWIN_Set_Color(color, 0xFFFF)
  F <x0> <y0> <x1> <y1>      -- DWIN_Fill_Rect_Raw(x0, y0, x1, y1)
"""
import sys
sys.path.insert(0, "SlicerScripts")
from orca_parser import quantize_foreground, rgb888_to_565, decode_and_resize, extract_thumbnail_b64
from PIL import Image

THUMB_X_START = 12
THUMB_Y_START = 25
MAX_RUNS_PER_ROW = 48


def load_image(path, force_size=(96, 96)):
    """Loads a thumbnail from either an image file or a .gcode file with an
    embedded base64 preview (any of the tags orca_parser.extract_thumbnail_b64
    recognizes)."""
    if path.lower().endswith(".gcode"):
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
        b64_string, _w, _h = extract_thumbnail_b64(lines)
        if b64_string is None:
            raise ValueError(f"no embedded thumbnail preview found in {path}")
        return decode_and_resize(b64_string, force_size)
    return Image.open(path).convert("RGB")


class Run:
    __slots__ = ("x0", "x1", "y0", "y1", "color")
    def __init__(self, x0, x1, y0, y1, color):
        self.x0, self.x1, self.y0, self.y1, self.color = x0, x1, y0, y1, color


def simulate(img, max_thumb_runs=1536, x_off=THUMB_X_START, y_off=THUMB_Y_START):
    """Identical algorithm to DWIN_RenderThumb / verify_blit.py's simulate(),
    kept as a standalone copy here so this script has no dependency beyond
    orca_parser."""
    w, h = img.size
    px = img.load()

    def color_at(x, y):
        r, g, b = px[x, y]
        return rgb888_to_565(r, g, b)

    runs = []
    open_prev = []
    commands = []

    def flush():
        nonlocal runs
        n = len(runs)
        emitted = [False] * n
        for i in range(n):
            if emitted[i]:
                continue
            color = runs[i].color
            commands.append(("S", color))
            for j in range(i, n):
                if emitted[j] or runs[j].color != color:
                    continue
                emitted[j] = True
                r = runs[j]
                commands.append(("F", x_off + r.x0, y_off + r.y0,
                                  x_off + r.x1, y_off + r.y1))
        runs = []

    for y in range(h):
        open_cur = []
        prev_idx = 0
        x = 0
        while x < w:
            color = color_at(x, y)
            if color == 0:
                x += 1
                continue
            x2 = x
            while x2 + 1 < w and color_at(x2 + 1, y) == color:
                x2 += 1

            while prev_idx < len(open_prev) and runs[open_prev[prev_idx]].x1 < x:
                prev_idx += 1

            merged = False
            if prev_idx < len(open_prev):
                pr = runs[open_prev[prev_idx]]
                if pr.x0 == x and pr.x1 == x2 and pr.color == color:
                    pr.y1 = y
                    if len(open_cur) < MAX_RUNS_PER_ROW:
                        open_cur.append(open_prev[prev_idx])
                    prev_idx += 1
                    merged = True
            if not merged:
                runs.append(Run(x, x2, y, y, color))
                if len(open_cur) < MAX_RUNS_PER_ROW:
                    open_cur.append(len(runs) - 1)
            x = x2 + 1

        open_prev = open_cur

        if max_thumb_runs - len(runs) < MAX_RUNS_PER_ROW:
            flush()
            open_prev = []

    if runs:
        flush()

    return commands


def simulate_naive(img, x_off=THUMB_X_START, y_off=THUMB_Y_START):
    """The ORIGINAL DWIN_RenderThumb algorithm: one DWIN_Set_Color + one 1x1
    DWIN_Fill_Rect_Raw per foreground pixel, in raster order, on the
    UN-quantized image (the original never quantized). No merging, no
    bucketing -- this is the "before" baseline being benchmarked against."""
    w, h = img.size
    px = img.load()
    commands = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            color = rgb888_to_565(r, g, b)
            if color == 0:
                continue
            sx, sy = x_off + x, y_off + y
            commands.append(("S", color))
            commands.append(("F", sx, sy, sx, sy))
    return commands


def main():
    args = sys.argv[1:]
    mode = "bucketed"
    if "--mode" in args:
        i = args.index("--mode")
        mode = args[i + 1]
        del args[i:i + 2]

    relative = "--relative" in args
    if relative:
        args.remove("--relative")

    if len(args) != 2 or mode not in ("bucketed", "naive"):
        print(f"usage: {sys.argv[0]} [--mode bucketed|naive] [--relative] <thumbnail.png|thumbnail.gcode> <out_commands.txt>", file=sys.stderr)
        sys.exit(1)

    x_off, y_off = (0, 0) if relative else (THUMB_X_START, THUMB_Y_START)

    img = load_image(args[0])
    if mode == "bucketed":
        img = quantize_foreground(img)
        commands = simulate(img, x_off=x_off, y_off=y_off)
    else:
        commands = simulate_naive(img, x_off=x_off, y_off=y_off)

    with open(args[1], "w") as f:
        for c in commands:
            if c[0] == "S":
                f.write(f"S {c[1]:04X}\n")
            else:
                f.write(f"F {c[1]} {c[2]} {c[3]} {c[4]}\n")

    n_set = sum(1 for c in commands if c[0] == "S")
    n_fill = sum(1 for c in commands if c[0] == "F")
    print(f"[{mode}] wrote {len(commands)} commands ({n_set} palette sets, {n_fill} fills) to {args[1]}")


if __name__ == "__main__":
    main()
