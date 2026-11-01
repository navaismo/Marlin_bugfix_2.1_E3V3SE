"""Client for the DWIN-family binary protocol confirmed live on the
TJC3224T132_011N panel (opcodes matching odwdinc/DWIN_T5UIC1_LCD, NOT the
generic T5UIC1.Kernel.Application.Guide set -- 0x01/0x02/0x22 etc from that
guide were tested live and do nothing on this panel).

Frame: 0xAA <instr> <data...> 0xCC 0x33 0xC3 0x3C, multi-byte fields
big-endian. See AGENTS.md for the full verified/rejected opcode table.
"""

import struct
import time

import serial

HEAD = b"\xaa"
TAIL = b"\xcc\x33\xc3\x3c"

# Opcodes confirmed live on hardware this session.
CMD_HANDSHAKE = 0x00
CMD_SET_PALETTE = 0x40
CMD_CLEAR = 0x52
CMD_FRAME_RECT = 0x59
CMD_FILL_RECT = 0x5B
CMD_BACKLIGHT = 0x5F
CMD_ICON_SHOW = 0x97
CMD_TEXT = 0x98

HANDSHAKE_REPLY_PREFIX = b"\xaa\x00\x4f\x4b"  # "AA 00 OK..."

# IMPORTANT, confirmed live this session: the binary DWIN parser and the
# Nextion/TJC text-command parser are mutually exclusive, not concurrent.
# Sending the Nextion `connect` handshake (as tjc_serial_upload.py does, and
# as used for page/get/wepo testing earlier this session) switches the panel
# into a mode where it stops answering 0xAA-framed binary commands entirely
# -- not just the handshake reply, drawing commands do nothing either. The
# only recovery found is a Nextion `rest` (reset) command, which reboots the
# panel back into a state that answers DWIN binary frames again. See
# recover_from_nextion_mode() below. Do not mix Panel (this module) use with
# tjc_serial_upload.py / any Nextion `connect` in the same test session
# without expecting to need that recovery step afterward.
#
# SAFETY, confirmed live this session: flooding the panel with ~2000
# 0x40+0x5B command pairs with NO per-command delay overran its input
# buffer -- it emitted a `0x24 0xFF 0xFF 0xFF` error frame, then stopped
# answering the DWIN handshake entirely, AND a Nextion `rest` reset did NOT
# recover it. Only a physical power cycle did. So: never send more than a
# couple hundred commands back-to-back with zero delay, and treat any
# unthrottled-batch experiment above that as something that may require the
# user to physically power-cycle the printer afterward. This is the concrete
# basis for keeping a per-command delay rather than dropping it for speed.


def frame(instr, data=b""):
    return HEAD + bytes([instr]) + data + TAIL


def word(v):
    return struct.pack(">H", v & 0xFFFF)


class Panel:
    """Thin serial wrapper. No side effects beyond what you tell it to send."""

    def __init__(self, port="/dev/ttyUSB0", baud=115200, timeout=0.01, delay=0.0):
        # `delay` is applied once per wire frame, inside send() -- not in the
        # calling code. This matters: fill_rect()/clear()/etc. each emit more
        # than one frame (a palette-set plus the draw itself), so throttling
        # at any higher level silently under-delays relative to a caller that
        # emits one frame per call, which produced a misleading comparison
        # between blit_naive and blit_rle/blit_bucketed earlier this session.
        self.delay = delay
        # NOTE: this is the per-call blocking-read timeout, not an overall
        # deadline. Keep it small -- handshake()/checkpoint timing polls in a
        # loop with its own deadline, and a large per-call timeout here would
        # cap the loop's resolution at that value regardless of how fast the
        # panel actually replies (measured: a 1.0s per-call timeout produced
        # a flat ~1007ms "latency" for every batch size, which was purely the
        # read() timeout floor, not real device latency).
        self.ser = serial.Serial(port, baud, timeout=timeout)
        # Empirically needed: opening the port (DTR/RTS toggle) leaves the
        # panel briefly unresponsive; 0.05s was not enough and produced
        # spurious handshake timeouts immediately after construction.
        time.sleep(0.3)
        self.ser.reset_input_buffer()

    def close(self):
        self.ser.close()

    def send(self, instr, data=b""):
        """Fire-and-forget: write a frame, no read. Applies self.delay here,
        at the single wire-frame level, so every higher-level helper (which
        may emit more than one frame per call) is throttled consistently."""
        self.ser.write(frame(instr, data))
        if self.delay:
            time.sleep(self.delay)

    def flush(self):
        self.ser.flush()

    def handshake(self, timeout=2.0):
        """Send the handshake and block until the OK_V1.5... reply arrives.

        Used both as a real handshake and, mid-stream, as a same-protocol
        timing checkpoint: because it shares the 0xAA-framed input path with
        the drawing opcodes, the time between sending it and receiving its
        reply approximates how long the panel took to drain everything queued
        ahead of it. See dwin_bench.py for the validation that this is true
        (checkpoint latency must scale with preceding batch size) before
        trusting it as a measurement.
        """
        self.ser.reset_input_buffer()
        t0 = time.perf_counter()
        self.ser.write(frame(CMD_HANDSHAKE))
        self.ser.flush()
        deadline = time.perf_counter() + timeout
        buf = b""
        while time.perf_counter() < deadline:
            chunk = self.ser.read(64)
            if chunk:
                buf += chunk
                if buf.startswith(HANDSHAKE_REPLY_PREFIX) and TAIL in buf:
                    return time.perf_counter() - t0
        raise TimeoutError(f"no handshake reply within {timeout}s (got {buf!r})")

    # -- drawing primitives, opcodes verified live this session --

    def set_palette(self, foreground, background=0x0000):
        self.send(CMD_SET_PALETTE, word(foreground) + word(background))

    def clear(self, color=0x0000):
        """Clears to `color`: sets it as background then sends bare 0x52,
        matching the confirmed-working sequence (0x40 fg=white bg=color, 0x52
        with no data)."""
        self.set_palette(0xFFFF, color)
        self.send(CMD_CLEAR)

    def fill_rect(self, color, x0, y0, x1, y1):
        self.set_palette(color)
        self.send(CMD_FILL_RECT, word(x0) + word(y0) + word(x1) + word(y1))

    def frame_rect(self, color, x0, y0, x1, y1):
        self.set_palette(color)
        self.send(CMD_FRAME_RECT, word(x0) + word(y0) + word(x1) + word(y1))

    def show_icon(self, pic_id, x, y, lib_id=0):
        self.send(
            CMD_ICON_SHOW,
            word(x) + word(y) + bytes([lib_id, 0x00]) + word(pic_id),
        )

    def backlight(self, level):
        self.send(CMD_BACKLIGHT, bytes([level & 0xFF]))


def recover_from_nextion_mode(port, baud=115200):
    """If the panel has stopped answering binary DWIN frames after Nextion
    text-protocol use, this reboots it back to a DWIN-capable state via the
    Nextion `connect` + `rest` sequence (confirmed live: the only recovery
    that worked). Safe to call speculatively -- if the panel is already in
    DWIN mode this just reboots it, same as power-cycling.
    """
    ser = serial.Serial(port, baud, timeout=1.0)
    time.sleep(0.2)
    ser.reset_input_buffer()
    NX = b"\xff\xff\xff"
    ser.write(b"DRAKJHSUYDGBNCJHGJKSHBDN" + NX + b"connect" + NX + b"\xff\xff" + b"connect" + NX)
    ser.flush()
    time.sleep(0.5)
    ser.reset_input_buffer()
    # The first command after `connect` is always silently dropped (same
    # quirk tjc_serial_upload.py works around) -- burn it, or `rest` itself
    # gets eaten and nothing happens. Confirmed live: omitting this line
    # made the whole function a silent no-op.
    ser.write(b"bs=42" + NX)
    ser.flush()
    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.write(b"rest" + NX)
    ser.flush()
    time.sleep(2.5)  # panel reboot time, confirmed sufficient this session
    ser.close()
