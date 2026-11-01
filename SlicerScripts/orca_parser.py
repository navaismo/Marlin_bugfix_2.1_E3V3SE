#!/usr/bin/env python3
import sys
import os
import base64
import io

from PIL import Image


RAW_BEGIN_TAG = "; E3V3SE_THUMB_RAW16_BEGIN"
RAW_END_TAG   = "; E3V3SE_THUMB_RAW16_END"


def rgb888_to_565(r, g, b):
    """Convert 8-bit RGB to 16-bit RGB565."""
    r5 = (r * 31) // 255
    g6 = (g * 63) // 255
    b5 = (b * 31) // 255
    return (r5 << 11) | (g6 << 5) | b5


QUANTIZE_COLORS = 32  # cap on distinct colours after resize; see PHASE_1_2_HANDOFF.md


def quantize_foreground(img):
    """Median-cut quantize `img` (RGB) to <=QUANTIZE_COLORS colours, without
    touching which pixels are background.

    The firmware treats RGB565 0x0000 (pure black) as a transparent/skip
    sentinel (DWIN_RenderThumb: `if (color == 0) continue;`). Quantizing the
    whole image naively can (a) pull a black foreground pixel onto some other
    bucket's black-ish mean, silently un-skipping background-colored fill, or
    (b) pull a near-black foreground pixel onto exact (0,0,0), punching a
    hole in the model silhouette. Both are avoided by quantizing only the
    non-background pixels and leaving (0,0,0) pixels untouched, then, when
    converting to RGB565, clamping any accidental 0x0000 result on a
    foreground pixel back to 0x0001 (visually indistinguishable, never
    skipped).
    """
    w, h = img.size
    src = img.load()
    fg_mask = [[src[x, y] != (0, 0, 0) for x in range(w)] for y in range(h)]

    if not any(any(row) for row in fg_mask):
        return img  # all background, nothing to quantize

    quantized = img.quantize(colors=QUANTIZE_COLORS, method=Image.MEDIANCUT).convert("RGB")
    qpx = quantized.load()

    out = Image.new("RGB", (w, h))
    dst = out.load()
    for y in range(h):
        for x in range(w):
            dst[x, y] = qpx[x, y] if fg_mask[y][x] else (0, 0, 0)
    return out


def extract_thumbnail_b64(lines):
    """
    Supports:
      - Orca:  ; thumbnail_JPG begin 96x96 2924 ... ; thumbnail_JPG end
    Returns (b64_string, width, height) or (None, None, None)
    """
    inside_thumb = False
    b64_chunks   = []
    width = height = None

    for line in lines:
        stripped = line.strip()

        # Orca
        if stripped.startswith("; thumbnail begin"):
            # example: "; thumbnail begin 96x96 2924"
            parts = stripped.split()
            for p in parts:
                if "x" in p and p.replace("x", "").isdigit():
                    try:
                        w, h = p.split("x")
                        width  = int(w)
                        height = int(h)
                    except Exception:
                        pass
            inside_thumb = True
            continue

        if inside_thumb and stripped.startswith("; thumbnail end"):
            inside_thumb = False
            break

        # Base64 content (lines starting with '; ' followed by data)
        if inside_thumb and stripped.startswith(";"):
            # remove initial ';'
            content = stripped[1:].strip()
            if content:
                b64_chunks.append(content)

    if not b64_chunks or width is None or height is None:
        return None, None, None

    b64_string = "".join(b64_chunks)
    return b64_string, width, height


def decode_and_resize(b64_string, force_size=(96, 96)):
    """Decodes a base64 PNG/JPG thumbnail and resizes it to force_size,
    WITHOUT quantizing -- shared by build_raw16_block_from_b64 (which then
    quantizes for embedding) and any caller that wants the plain resized
    image (e.g. to re-derive a thumbnail directly from a .gcode file's
    embedded base64, matching what orca_parser would produce fresh)."""
    img_bytes = base64.b64decode(b64_string)
    img = Image.open(io.BytesIO(img_bytes))
    img = img.convert("RGB")

    target_w, target_h = force_size
    if img.size != (target_w, target_h):
        # LANCZOS interpolation blends edge pixels between the model's flat
        # shaded facets, which is what manufactures ~69 distinct colours out
        # of what should be a handful -- quantizing below undoes that.
        img = img.resize((target_w, target_h), Image.LANCZOS)
    return img


def build_raw16_block_from_b64(b64_string, width, height, force_size=(96, 96)):
    """
    Decodes the B64 (PNG/JPG), converts it to RGB565, and generates
    the RAW16 block as a list of G-code lines (comments).
    """
    target_w, target_h = force_size
    img = decode_and_resize(b64_string, force_size)
    img = quantize_foreground(img)

    rows = []
    for y in range(target_h):
        hex_row = []
        for x in range(target_w):
            r, g, b = img.getpixel((x, y))
            is_background = (r, g, b) == (0, 0, 0)
            c565 = rgb888_to_565(r, g, b)
            if not is_background and c565 == 0:
                c565 = 1  # never let a foreground pixel collide with the skip sentinel
            hex_row.append(f"{c565:04X}")
        rows.append("".join(hex_row))

    block = []
    block.append(f"{RAW_BEGIN_TAG} {target_w}x{target_h}")
    for row in rows:
        block.append(f"; {row}")
    block.append(RAW_END_TAG)

    return block


def insert_raw_block(lines, raw_block):
    """
    Inserts the RAW16 block into the G-code.
    Strategy:
      - If ; HEADER_BLOCK_END exists, insert right after it.
    """
    out_lines = []
    inserted = False

    for line in lines:
        stripped = line.strip()

        out_lines.append(line)

        if stripped.startswith("; HEADER_BLOCK_END") and not inserted:
            # Insert right after the Orca header block
            for raw_line in raw_block:
                out_lines.append(raw_line + "\n")
            inserted = True

    if not inserted and raw_block:
        # If for some reason we don't find a place, put it at the end
        out_lines.append("\n")
        for raw_line in raw_block:
            out_lines.append(raw_line + "\n")

    return out_lines


def insert_m73_layer_numbers(lines, start_layer=1):
    """
   Search for lines with:
      ;LAYER_CHANGE

    And replaces them with the block:
      ;LAYER_CHANGE
      M73 L(n)
    where (n) is the layer number starting from start_layer.
    """
    out_lines = []
    layer_num = start_layer

    for line in lines:
        stripped = line.strip()
        if stripped == ";LAYER_CHANGE":
            # Keep the original line
            out_lines.append(line)
            # Insert the M73 L(n)
            out_lines.append(f"M73 L{layer_num}\n")
            layer_num += 1
        else:
            out_lines.append(line)

    return out_lines


def main():
    if len(sys.argv) < 2:
        print("Usage: python OrcaSlicer_E3V3SE_Thumb.py input.gcode [output.gcode]")
        sys.exit(1)

    in_path = sys.argv[1]
    if not os.path.isfile(in_path):
        print(f"File not found: {in_path}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        out_path = sys.argv[2]
    else:
        out_path = in_path

    with open(in_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # 1) Process thumbnail (if exists)
    b64, w, h = extract_thumbnail_b64(lines)
    if b64:
        print(f"Thumbnail found: {w}x{h}")
        raw_block = build_raw16_block_from_b64(b64, w, h, force_size=(96, 96))
        new_lines = insert_raw_block(lines, raw_block)
    else:
        print("No thumbnail found in G-code. Skipping RAW16 insertion.")
        new_lines = list(lines)

    # 2) Insert M73 L(n) after each ;LAYER_CHANGE
    new_lines = insert_m73_layer_numbers(new_lines, start_layer=1)

    # 3) Save final file
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"File generated: {out_path}")


if __name__ == "__main__":
    main()
