#!/usr/bin/env python3
"""Check production thumbnail pixels, coverage, merging and pacing with ASan/UBSan."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "Marlin/src/e3v3se/ThumbRender.cpp")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    compiler = os.environ.get("CXX") or shutil.which("clang++") or "g++"
    with tempfile.TemporaryDirectory(prefix="marlin-thumbnail-") as directory:
        work = Path(directory)
        dest = work / "e3v3se/ThumbRender.cpp"
        dest.parent.mkdir()
        shutil.copyfile(args.source, dest)
        shutil.copyfile(HERE / "mock.h", work / "mock.h")
        for name in ["inc/MarlinConfigPre.h", "inc/MarlinConfig.h",
                     "lcd/dwin/creality/dwin_lcd.h", "sd/cardreader.h", "HAL/shared/Delay.h"]:
            stub = work / name
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text('#pragma once\n#include "mock.h"\n')
        flags = [compiler, "-std=c++11", "-O1", "-g", "-fsanitize=address,undefined",
                 "-fno-omit-frame-pointer", "-I", str(work)]
        subprocess.run(flags + [str(dest), str(HERE / "test_renderer.cpp"),
                                "-o", str(work / "test")], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        result = subprocess.run([str(work / "test")], env=env, capture_output=True, text=True)
        if args.output:
            args.output.write_text(result.stdout + result.stderr)
        print(result.stdout, end="")
        if result.returncode:
            raise RuntimeError(result.stderr)
        subprocess.run(flags + ["-DDWIN_RENDER_THUMBNAIL=0", "-c", str(dest),
                                "-o", str(work / "disabled.o")], check=True)
        print("PASS renderer translation unit with DWIN_RENDER_THUMBNAIL disabled")


if __name__ == "__main__":
    main()
