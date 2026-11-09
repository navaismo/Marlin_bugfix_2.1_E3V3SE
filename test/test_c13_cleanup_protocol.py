"""Compile and exercise the production M9001 decoder/executor with ASan/UBSan."""
import base64
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


def packet(kind, sid=1, body=b""):
    data = struct.pack(">BI", 2, sid) + body
    data += struct.pack(">I", zlib.crc32(kind.encode() + data))
    return "C " + kind + base64.b64encode(data).decode().replace("G", "_")


def transfer(ops, sid=1):
    batches, chunk = [], b""
    for op in ops:
        if len(chunk) + len(op) > 42:
            batches.append(chunk)
            chunk = b""
        chunk += op
    if chunk:
        batches.append(chunk)
    script = [packet("B", sid)]
    checksum = 0
    for i, chunk in enumerate(batches):
        script += [packet("D", sid, struct.pack(">H", i) + chunk), "T 60"]
        checksum = zlib.crc32(chunk, checksum)
    script += [packet("E", sid, struct.pack(">HI", len(batches), checksum)), "T 150"]
    return script


def framebuffer(output):
    pixels, color = [0x1234] * (240 * 320), 0
    frames = []
    for line in output.splitlines():
        if not line.startswith("F "):
            continue
        _, encoded, clock = line.split()
        frame = bytes.fromhex(encoded)
        frames.append((frame, int(clock)))
        if frame[1] == 0x40:
            color = int.from_bytes(frame[2:4], "big")
        elif frame[1] == 0x5B:
            x0, y0, x1, y1 = struct.unpack(">HHHH", frame[2:10])
            for y in range(y0, y1 + 1):
                pixels[y*240+x0:y*240+x1+1] = [color] * (x1-x0+1)
    return pixels, frames


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="c13-draw-")
        cls.exe = Path(cls.temp.name) / "draw"
        subprocess.run(["clang++", "-std=c++17", "-g", "-O1", "-fsanitize=address,undefined",
                        "-fno-omit-frame-pointer", "-DLCD_DRAW_NATIVE_TEST", str(ROOT/"test/c13_cleanup/harness.cpp"),
                        str(ROOT/"Marlin/src/e3v3se/LcdDraw.cpp"), "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_script(self, lines):
        result = subprocess.run([str(self.exe)], input="\n".join(lines)+"\n", text=True, capture_output=True,
                                env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0"), check=True)
        self.assertNotIn("runtime error:", result.stderr)
        return result.stdout

    def test_strip_bounds_truncation_and_palette_order(self):
        for strip in (bytes((2,239,24,2,1,2,3,4)),bytes((2,12,25,0,0,0)),
                      bytes((2,12,25,20))+bytes(40),bytes((2,12,25,2,0,1))):
            output=self.run_script([packet("B"),packet("D",body=b"\0\0\0\0\0"+strip),"T 200"])
            self.assertNotIn("F ",output)
        strip=bytes((2,12,25,2,0xF8,0,0x07,0xE0))
        script=transfer([b"\0\0\0",strip,bytes((1,14,25,14,25))])
        output=self.run_script(script)
        pixels,_=framebuffer(output)
        self.assertEqual(pixels[25*240+12:25*240+15],[0xF800,0x07E0,0x07E0])
        self.assertIn("DONE",output)

    def test_color_rect_and_final_lcd_fence(self):
        output = self.run_script(transfer([bytes((0, 7, 224)), bytes((1, 12, 25, 107, 120))]))
        self.assertIn("DONE 00000001 0001", output)
        pixels, frames = framebuffer(output)
        self.assertEqual(pixels[25*240+12], 0x07E0)
        self.assertEqual(pixels[24*240+12], 0x1234)
        self.assertEqual(len(frames), 3)

    def test_worst_case_96_by_96_and_repeated_batches(self):
        ops = []
        for y in range(96):
            for x in range(96):
                value = (x + y * 96) % 65535 + 1
                ops += [bytes((0, value >> 8, value & 255)), bytes((1, 12+x, 25+y, 12+x, 25+y))]
        output = self.run_script(transfer(ops))
        pixels, frames = framebuffer(output)
        self.assertIn("DONE", output)
        for y in range(96):
            self.assertEqual(pixels[(25+y)*240+12:(25+y)*240+108], list(range(y*96+1, y*96+97)))
        self.assertEqual(pixels[122*240], 0x1234)
        self.assertEqual(len(frames), 18433)
        for i in range(10, len(frames)-1, 10):
            self.assertGreaterEqual(frames[i][1]-frames[i-1][1], 17)

    def test_empty_commands_and_stale_begin_after_abort(self):
        output = self.run_script(["C ",packet("B"),packet("A"),packet("B"),"T 100"])
        self.assertIn("FORMAT",output)
        self.assertEqual(output.count("ABORTED"),2)
        self.assertNotIn("F ",output)

    def test_crc_and_canonical_base64(self):
        good = packet("D", body=b"\0\0\x07\xe0")
        bad = good[:-4] + "AAAA"
        output = self.run_script([packet("B"), bad, "C D!!!!", "C DA===", "T 100"])
        self.assertIn("CRC", output)
        self.assertIn("FORMAT", output)
        self.assertNotIn("F ", output)

    def test_bounds_are_validated_before_any_operation_executes(self):
        for rect in ((1, 0, 24, 1, 25), (1, 0, 24, 240, 25), (1, 0, 25, 1, 123), (1, 5, 25, 4, 26)):
            with self.subTest(rect=rect):
                body = b"\0\0\0\xf8\x00" + bytes(rect)
                output = self.run_script([packet("B"), packet("D", body=body), "T 100"])
                self.assertIn("BOUNDS", output)
                self.assertNotIn("F ", output)

    def test_missing_palette_truncated_and_unknown_opcodes(self):
        for data in (b"\x01\x00\x18\x01\x19", b"\0\0", b"\x03\x00\x00"):
            output = self.run_script([packet("B"), packet("D", body=b"\0\0"+data), "T 100"])
            self.assertNotIn("F ", output)
            self.assertTrue("FORMAT" in output or "BOUNDS" in output)

    def test_duplicate_retry_does_not_redraw(self):
        data = b"\0\0\0\x07\xe0\x01\x0c\x19\x6b\x78"
        cmd = packet("D", body=data)
        output = self.run_script([packet("B"), cmd, cmd, "T 100", cmd, "T 100"])
        self.assertEqual(len(framebuffer(output)[1]), 2)
        self.assertEqual(output.count("ACK 00000001 0001"), 2)

    def test_sequence_session_and_concurrent_begin(self):
        output = self.run_script([packet("B"), packet("B",2),
                                 packet("D",body=b"\0\x01\0\0\0"), packet("D",2,b"\0\0\0\0\0")])
        self.assertIn("BUSY",output)
        self.assertIn("ORDER",output)
        self.assertIn("SESSION",output)
        self.assertNotIn("F ",output)

    def test_abort_motion_encoder_disconnect_and_timeouts(self):
        for action in ("X", "G G 1", "G M 600", "A 0", "T 5001"):
            script = transfer([b"\0\x07\xe0", b"\x01\x0c\x19\x6b\x78"])
            output = self.run_script(script[:2]+[action,"T 100"])
            self.assertIn("ABORTED",output)
            self.assertNotIn("DONE",output)

    def test_no_completion_without_full_current_fence(self):
        script=transfer([b"\0\0\0"])
        output=self.run_script(["H 0","R "+"55"*40+"AA004F4BCC33C33C"]+script+["T 1200"])
        self.assertNotIn("DONE",output)
        self.assertIn("ABORTED",output)

    def test_complete_reply_with_optional_version_and_end_retry(self):
        script=transfer([b"\0\0\0"])
        output=self.run_script(script+[script[-2],"T 100"])
        self.assertEqual(output.count("DONE"),2)
        self.assertEqual(sum(f[0][1]==0 for f in framebuffer(output)[1]),1)

    def test_stalled_uart_is_cooperative_and_expires(self):
        output=self.run_script(["B 1",packet("B"),packet("D",body=b"\0\0\0\0\0"),"T 5100"])
        self.assertIn("ABORTED",output)
        self.assertNotIn("F ",output)

    def test_numbered_maximum_line_fits_existing_buffer(self):
        data=b"\0\0" + b"\0\0\0"*14
        cmd=packet("D",body=data)[2:]
        command="N2147483647 M9001 "+cmd+"*255"
        self.assertLessEqual(len(command),95)

if __name__ == "__main__":
    unittest.main()
