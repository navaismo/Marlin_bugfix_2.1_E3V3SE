"""Decode the E3V3SE_THUMB_RAW16 hex-text thumbnail block that
Marlin/src/lcd/e3v2/creality/dwin_lcd.cpp's find_thumb_raw16_header /
DWIN_RenderThumb read out of G-code comments, into a PIL image -- so real
G-code thumbnails can be used as dwin_bench.py benchmark inputs instead of
synthetic stand-ins.
"""

from PIL import Image


def rgb565_to_rgb(v):
    r = (v >> 11) & 0x1F
    g = (v >> 5) & 0x3F
    b = v & 0x1F
    return ((r * 255) // 31, (g * 255) // 63, (b * 255) // 31)


def load_thumb_raw16(gcode_path):
    """Returns a PIL RGB Image, or None if no RAW16 block was found."""
    with open(gcode_path, "r", errors="replace") as f:
        lines = f.readlines()

    w = h = None
    start = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(";") and "E3V3SE_THUMB_RAW16_BEGIN" in s:
            dims = s.split("BEGIN", 1)[1].strip()
            w, h = (int(v) for v in dims.lower().split("x"))
            start = i + 1
            break
    if start is None:
        return None

    img = Image.new("RGB", (w, h), (0, 0, 0))
    px = img.load()
    y = 0
    for line in lines[start:]:
        s = line.strip()
        if not s.startswith(";"):
            continue
        p = s[1:].strip()
        if p.startswith("E3V3SE_THUMB_RAW16_END"):
            break
        if len(p) < w * 4:
            break
        for x in range(w):
            v = int(p[x * 4 : x * 4 + 4], 16)
            if v:
                px[x, y] = rgb565_to_rgb(v)
        y += 1
        if y >= h:
            break
    return img


if __name__ == "__main__":
    import sys

    for path in sys.argv[1:]:
        img = load_thumb_raw16(path)
        if img is None:
            print(f"{path}: no RAW16 thumbnail found")
            continue
        out = path.rsplit(".", 1)[0] + "_thumb.png"
        img.save(out)
        print(f"{path}: {img.size} -> {out}")
