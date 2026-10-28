#!/usr/bin/env python3
"""Toggle Marlin feature defines in the checked-out configuration (used by the build workflow).

Usage: apply_marlin_options.py NAME=true|false [NAME=true|false ...]

The macro is searched in Configuration.h and Configuration_adv.h. Disabling a macro that does
not exist is a no-op; enabling one that does not exist is an error. OCTOPRINT_PLUGIN is present
only in the OctoPrint profiles.
"""
import re
import sys
from pathlib import Path

FILES = [Path("Marlin/Configuration.h"), Path("Marlin/Configuration_adv.h")]

# A feature can only be enabled if the feature it depends on is enabled too.
DEPENDS = {
    "DWIN_PLR_MENU": "POWER_LOSS_RECOVERY",
    "DWIN_SKEW_MENU": "SKEW_CORRECTION",
}


def to_bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


def set_define(macro: str, enabled: bool) -> bool:
    pattern = re.compile(r"^(\s*)(//\s*)?#define\s+" + re.escape(macro) + r"(\b.*)$", re.MULTILINE)
    for path in FILES:
        text = path.read_text()
        if not pattern.search(text):
            continue
        prefix = "" if enabled else "//"

        def replacement(match):
            tail = match.group(3)
            if enabled:
                # An explicit false value must not survive an enable request.
                tail = re.sub(r"^\s+(?:0|0x0|false)(?=\s*(?://|/\*|$))", "", tail)
            return f"{match.group(1)}{prefix}#define {macro}{tail}"

        text = pattern.sub(replacement, text, count=1)
        path.write_text(text)
        return True
    return False


def define_enabled(macro: str) -> bool:
    pattern = re.compile(r"^\s*#define\s+" + re.escape(macro) + r"\b([^\n]*)", re.MULTILINE)
    for path in FILES:
        match = pattern.search(path.read_text())
        if match:
            value = re.sub(r"/\*.*?\*/|//.*", "", match.group(1)).strip()
            return value in ("", "1", "0x1", "true")
    return False


def main() -> int:
    wanted = {}
    for arg in sys.argv[1:]:
        name, _, value = arg.partition("=")
        wanted[name] = to_bool(value)

    for macro, dep in DEPENDS.items():
        if wanted.get(macro) and not wanted.get(dep, False):
            print(f"{macro} requires {dep}; forcing {macro}=false")
            wanted[macro] = False

    # Respect FT_MOTION in the existing configuration when no override is given.
    # The legacy menu enables X/Y shaping in Configuration_adv.h when FTM is off.
    if wanted.get("FT_MOTION", define_enabled("FT_MOTION")):
        if wanted.get("DWIN_INPUT_SHAPING_MENU", define_enabled("DWIN_INPUT_SHAPING_MENU")):
            print("DWIN_INPUT_SHAPING_MENU is legacy-only; FT_MOTION forces it off")
        wanted["DWIN_INPUT_SHAPING_MENU"] = False

    status = 0
    for macro, enabled in wanted.items():
        found = set_define(macro, enabled)
        if not found and enabled:
            print(f"ERROR: {macro} not found in the configuration of this branch", file=sys.stderr)
            status = 1
        else:
            print(f"{macro} -> {'enabled' if enabled else 'disabled'}{'' if found else ' (not present, skipped)'}")
    return status


if __name__ == "__main__":
    sys.exit(main())
