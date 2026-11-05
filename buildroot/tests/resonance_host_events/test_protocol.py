#!/usr/bin/env python3
"""Compile the real M495 handler, generator and event extension against motion mocks.

Run from any directory: python3 buildroot/tests/resonance_host_events/test_protocol.py
No PlatformIO, hardware, motors, or external Python packages are needed.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCES = [
    "feature/resonance/resonance_generator.h",
    "feature/resonance/resonance_generator.cpp",
    "feature/resonance/resonance_host_events.h",
    "feature/resonance/resonance_host_events.cpp",
    "gcode/feature/resonance/M495_M496.cpp",
]
STUBS = ["inc/MarlinConfig.h", "inc/MarlinConfigPre.h", "core/types.h",
         "MarlinCore.h", "gcode/gcode.h", "lcd/marlinui.h",
         "module/planner.h", "module/stepper.h", "module/ft_motion.h"]


def main():
    dispatch = (ROOT / "Marlin/src/gcode/gcode.cpp").read_text()
    assert dispatch.index("resonance_host_events::reject_command()") < dispatch.index("switch (parser.command_letter)", dispatch.index("void GcodeSuite::process_parsed_command"))
    with tempfile.TemporaryDirectory(prefix="marlin-resonance-test-") as tmp:
        tmp = Path(tmp)
        for name in SOURCES:
            dest = tmp / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "Marlin/src" / name, dest)
        shutil.copyfile(HERE / "mock_marlin.h", tmp / "mock_marlin.h")
        shutil.copyfile(HERE / "test_protocol.cpp", tmp / "test_protocol.cpp")
        for name in STUBS:
            dest = tmp / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text('#pragma once\n#include "mock_marlin.h"\n')
        for enabled, ftm, progress, multi, standard in [
            (0, 1, 0, 0, 0), (1, 0, 0, 0, 0), (1, 1, 0, 0, 0),
            (1, 1, 1, 0, 0), (1, 1, 1, 1, 0), (1, 1, 0, 0, 1),
        ]:
            args = ["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I", str(tmp),
                    f"-DPINPUT_RESONANCE_EVENTS={enabled}", f"-DFT_MOTION={ftm}",
                    f"-DPINPUT_RESONANCE_PROGRESS={progress}", f"-DHAS_MULTI_SERIAL={multi}",
                    f"-DTEST_STANDARD={standard}",
                    str(tmp / "test_protocol.cpp"),
                    *(str(tmp / name) for name in SOURCES if name.endswith(".cpp")),
                    "-o", str(tmp / "test")]
            subprocess.run(args, check=True)
            subprocess.run([str(tmp / "test")], check=True)
            print(f"PASS: events={enabled}, ft_motion={ftm}, progress={progress}, multiserial={multi}, standard={standard}", flush=True)


if __name__ == "__main__":
    main()
