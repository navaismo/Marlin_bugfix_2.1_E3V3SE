#!/usr/bin/env python3
"""
E3V3SE guardrails.

  check_profile.py boundary [--update]   fork edits to upstream-owned files must not grow
  check_profile.py build [--update]      firmware RAM/flash must not exceed the baseline
  check_profile.py config                Configuration*.h must match upstream + profiles/c13_sd (see config_profile.py)

State lives in baseline.json next to this script. "--update" rewrites the baseline,
and should only be used after a deliberate, reviewed change.
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASELINE = HERE / "baseline.json"

# Paths that are fork-owned, so edits there are not boundary violations.
FORK_OWNED = (
    "Marlin/src/e3v3se/", "Marlin/src/lcd/dwin/creality/", "Marlin/src/lcd/e3v2/creality/",
    "buildroot/share/e3v3se/", "DWIN_OptimizationReference/", "SlicerScripts/", "FW_HWC13/",
    "Serial_Debugger/", ".github/", "docs/", "AGENTS.E3V3SE.md", "MEMORY.md",
)

def sh(*a, **k):
    return subprocess.run(a, cwd=ROOT, text=True, capture_output=True, **k)

def load():
    return json.loads(BASELINE.read_text()) if BASELINE.exists() else {}

def save(d):
    BASELINE.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n")

def boundary(args):
    ref = args.upstream
    out = sh("git", "diff", "--name-status", ref, "HEAD").stdout.splitlines()
    touched = sorted(
        l.split("\t", 1)[1] for l in out
        if l[0] in "MD" and not l.split("\t", 1)[1].startswith(FORK_OWNED)
    )
    base = load()
    if args.update:
        base["boundary_files"] = touched
        save(base); print(f"boundary baseline updated: {len(touched)} files"); return 0
    allowed = set(base.get("boundary_files", []))
    new = [f for f in touched if f not in allowed]
    gone = [f for f in allowed if f not in touched]
    print(f"upstream-owned files modified: {len(touched)} (baseline {len(allowed)})")
    for f in gone: print(f"  reduced: {f}")
    for f in new: print(f"  NEW EDIT TO UPSTREAM FILE: {f}")
    return 1 if new else 0

def build(args):
    r = sh("pio", "run", "-e", args.env)
    text = r.stdout + r.stderr
    if r.returncode:
        print(text[-3000:]); print("build FAILED"); return 1
    ram = re.search(r"RAM:.*used (\d+) bytes", text)
    flash = re.search(r"Flash:.*used (\d+) bytes", text)
    if not (ram and flash):
        print("could not parse memory usage"); return 1
    cur = {"ram": int(ram.group(1)), "flash": int(flash.group(1))}
    base = load()
    if args.update:
        base.setdefault("build", {})[args.env] = cur
        save(base); print(f"build baseline updated: {cur}"); return 0
    ref = base.get("build", {}).get(args.env)
    print(f"{args.env}: RAM {cur['ram']} B, flash {cur['flash']} B")
    if not ref:
        print("no baseline recorded (run with --update)"); return 1
    bad = False
    for k, tol in (("ram", args.ram_tol), ("flash", args.flash_tol)):
        d = cur[k] - ref[k]
        print(f"  {k}: {d:+d} B vs baseline {ref[k]}")
        if d > tol: bad = True; print(f"  {k} exceeds baseline by more than {tol} B")
    return 1 if bad else 0

p = argparse.ArgumentParser()
s = p.add_subparsers(dest="cmd", required=True)
b = s.add_parser("boundary"); b.add_argument("--upstream", default="upstream/bugfix-2.1.x"); b.add_argument("--update", action="store_true")
c = s.add_parser("build"); c.add_argument("--env", default="STM32F103RET6_creality")
c.add_argument("--ram-tol", type=int, default=0); c.add_argument("--flash-tol", type=int, default=512); c.add_argument("--update", action="store_true")
s.add_parser("config")
a = p.parse_args()
if a.cmd == "config":
    sys.exit(subprocess.run([sys.executable, str(HERE / "config_profile.py"), "check"]).returncode)
sys.exit(boundary(a) if a.cmd == "boundary" else build(a))
