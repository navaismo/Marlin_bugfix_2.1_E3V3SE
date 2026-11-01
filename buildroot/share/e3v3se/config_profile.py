#!/usr/bin/env python3
"""
Config profile tool: keeps Configuration.h / Configuration_adv.h as
    <pristine upstream file> + overrides.txt + residual.patch

  derive  - (re)create the profile from the committed config files and a base ref
  apply   - regenerate the config files from a base ref (default: merge-base with upstream/bugfix-2.1.x)
  check   - verify the committed config files are semantically equal to apply(base ref); exit 1 otherwise
  stale   - list upstream options that are enabled upstream but disabled by the profile

overrides.txt: one line per changed define, "<file> <E|D> NAME[#n] [value]"
  E = enabled with value, D = disabled; "#n" selects the n-th occurrence (default 1).
residual.<file>.patch: unified diff for everything that is not a define state
  (fork-only options, extra #if blocks, extern declarations ...).
"""
import argparse, difflib, os, re, subprocess, sys, tempfile

ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
PROFILE_DIR = os.path.join(ROOT, "buildroot/share/e3v3se/profiles")
FILES = ("Configuration.h", "Configuration_adv.h")
_active = os.path.join(PROFILE_DIR, "..", "active_profile")
ACTIVE_PROFILE = open(_active).read().strip() if os.path.exists(_active) else "c13_sd"
DEFINE = re.compile(r'^(\s*)(//)?(\s*)#define(\s+)(\w+)(?:(\s+)(.*?))?(\s*//.*)?$')


def git_show(ref, name):
    return subprocess.check_output(["git", "show", f"{ref}:Marlin/{name}"], cwd=ROOT).decode("utf-8")


def parse(text):
    """Return (lines, {(name, occurrence): line index}) for single-line defines."""
    lines = text.split("\n")
    seen, idx = {}, {}
    for i, l in enumerate(lines):
        m = DEFINE.match(l)
        if not m or l.rstrip().endswith("\\"): continue
        n = seen.get(m[5], 0) + 1
        seen[m[5]] = n
        idx[(m[5], n)] = i
    return lines, idx


def state(line):
    m = DEFINE.match(line)
    return (m[2] is None, (m[7] or "").strip())


def rewrite(line, enabled, value):
    m = DEFINE.match(line)
    indent, _, sp1, sp2, name, sp3, _, tail = m.groups()
    val = (m[7] or "").strip() if value is None else value
    body = f"#define{sp2}{name}" + (f"{sp3 or ' '}{val}" if val != "" else "")
    return f"{indent}{'' if enabled else '//'}{sp1}{body}{tail or ''}"


def derive_overrides(up_text, cur_text, fname):
    ulines, uidx = parse(up_text)
    clines, cidx = parse(cur_text)
    out = []
    for (name, n), i in uidx.items():
        key = name if n == 1 else f"{name}#{n}"
        u_en, u_val = state(ulines[i])
        if (name, n) not in cidx:
            if u_en: out.append(f"{fname} D {key}")
            continue
        c_en, c_val = state(clines[cidx[(name, n)]])
        if (u_en, u_val if u_en else "") == (c_en, c_val if c_en else ""): continue
        out.append(f"{fname} {'E' if c_en else 'D'} {key}" + (f" {c_val}" if c_en and c_val else ""))
    return out


def apply_overrides(up_text, overrides, fname):
    lines, idx = parse(up_text)
    for o in overrides:
        f, st, key, *rest = o.split(" ", 3)
        if f != fname: continue
        name, _, n = key.partition("#")
        i = idx.get((name, int(n or 1)))
        if i is None:
            print(f"WARNING: {fname}: option {key} no longer exists upstream (dropped override)", file=sys.stderr)
            continue
        lines[i] = rewrite(lines[i], st == "E", rest[0] if rest else None)
    return "\n".join(lines)


def run_patch(text, patch_path, fname):
    if not os.path.exists(patch_path) or os.path.getsize(patch_path) == 0:
        return text, True
    with tempfile.TemporaryDirectory() as d:
        target = os.path.join(d, fname)
        open(target, "w", encoding="utf-8", newline="").write(text)
        r = subprocess.run(["patch", "-p0", "--no-backup-if-mismatch", "-F3", target, patch_path],
                           capture_output=True, text=True, cwd=d)
        if r.returncode:
            print(r.stdout + r.stderr, file=sys.stderr)
            rej = target + ".rej"
            if os.path.exists(rej): print(open(rej).read(), file=sys.stderr)
        return open(target, encoding="utf-8", newline="").read(), r.returncode == 0


def make_diff(a_text, b_text, fname):
    with tempfile.TemporaryDirectory() as d:
        pa, pb = os.path.join(d, "a", fname), os.path.join(d, "b", fname)
        os.makedirs(os.path.dirname(pa)); os.makedirs(os.path.dirname(pb))
        open(pa, "w", encoding="utf-8", newline="").write(a_text)
        open(pb, "w", encoding="utf-8", newline="").write(b_text)
        r = subprocess.run(["diff", "-u", "--label", fname, "--label", fname, pa, pb], capture_output=True, text=True)
        return r.stdout


def entries(lines):
    """Significant lines as (key, line index). Comments, blanks and disabled-define values are ignored."""
    out, in_block = [], False
    for i, l in enumerate(lines):
        s = l.strip()
        if in_block:
            if "*/" in s: in_block = False
            continue
        if s.startswith("/*"):
            in_block = "*/" not in s
            continue
        if not s: continue
        m = DEFINE.match(l)
        if m and not l.rstrip().endswith("\\"):
            out.append((("D", m[5], (m[7] or "").strip()) if m[2] is None else ("d", m[5]), i))
        elif not s.startswith("//"):
            out.append((("T", re.sub(r"\s*//.*$", "", s)), i))
    return out


def semantic(text):
    return [k for k, _ in entries(text.split("\n")) if k[0] != "d"]


def align(upo_text, cur_text):
    """upstream+overrides rewritten so it differs from cur only by semantic lines (fork code keeps upstream comments)."""
    ul, cl = upo_text.split("\n"), cur_text.split("\n")
    U, C = entries(ul), entries(cl)
    sm = difflib.SequenceMatcher(None, [k for k, _ in U], [k for k, _ in C], autojunk=False)
    delete, insert_after = set(), {}
    for t, i1, i2, j1, j2 in sm.get_opcodes():
        if t == "equal": continue
        for k, i in U[i1:i2]:
            if k[0] != "d": delete.add(i)
        if j2 > j1:
            block = cl[C[j1][1]:C[j2 - 1][1] + 1]
            anchor = U[i2 - 1][1] if i2 > i1 else (U[i1 - 1][1] if i1 else -1)
            insert_after.setdefault(anchor, []).extend(block)
    out = list(insert_after.get(-1, []))
    for i, l in enumerate(ul):
        if i not in delete: out.append(l)
        out.extend(insert_after.get(i, []))
    return "\n".join(out)


def profile_paths(profile):
    base = os.path.join(PROFILE_DIR, profile)
    return base, os.path.join(base, "overrides.txt"), {f: os.path.join(base, f"residual.{f}.patch") for f in FILES}


def load_overrides(path):
    return [l.rstrip("\n") for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")] if os.path.exists(path) else []


def generate(profile, ref):
    _, opath, patches = profile_paths(profile)
    ov, ok, res = load_overrides(opath), True, {}
    for f in FILES:
        text = apply_overrides(git_show(ref, f), ov, f)
        text, good = run_patch(text, patches[f], f)
        ok &= good
        res[f] = text
    return res, ok


def cmd_derive(a):
    base, opath, patches = profile_paths(a.profile)
    os.makedirs(base, exist_ok=True)
    ov = []
    for f in FILES:
        up = git_show(a.ref, f)
        cur = open(os.path.join(ROOT, "Marlin", f), encoding="utf-8", newline="").read()
        o = derive_overrides(up, cur, f)
        ov += o
        upo = apply_overrides(up, o, f)
        diff = make_diff(upo, align(upo, cur), f)
        open(patches[f], "w", encoding="utf-8", newline="").write(diff)
    open(opath, "w", encoding="utf-8").write(
        f"# Define-level overrides on top of {a.ref}. Regenerate with: config_profile.py derive\n" + "\n".join(ov) + "\n")
    print(f"profile '{a.profile}': {len(ov)} overrides, residual patches "
          + ", ".join(f"{f}={os.path.getsize(p)}B" for f, p in patches.items()))


def cmd_apply(a):
    res, ok = generate(a.profile, a.ref)
    if not ok:
        print("apply FAILED: residual patch does not apply cleanly; nothing written", file=sys.stderr)
        return 1
    for f, text in res.items():
        open(os.path.join(ROOT, "Marlin", f), "w", encoding="utf-8", newline="").write(text)
    print("config files regenerated from", a.ref)
    return 0


def cmd_check(a):
    res, ok = generate(a.profile, a.ref)
    bad = [f for f in FILES if not ok or semantic(res[f]) != semantic(open(os.path.join(ROOT, "Marlin", f), encoding="utf-8", newline="").read())]
    print("config profile OK" if not bad else f"config profile OUT OF SYNC: {', '.join(bad)} (run derive, or apply)")
    return 1 if bad else 0


def cmd_stale(a):
    for f in FILES:
        up = git_show(a.ref, f)
        ulines, uidx = parse(up)
        for o in load_overrides(profile_paths(a.profile)[1]):
            fn, st, key, *_ = o.split(" ", 3)
            if fn != f or st != "D": continue
            name, _, n = key.partition("#")
            i = uidx.get((name, int(n or 1)))
            if i is not None and state(ulines[i])[0]:
                print(f"{f}: {key} enabled upstream, disabled by profile")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("derive", "apply", "check", "stale"))
    p.add_argument("--profile", default=ACTIVE_PROFILE)
    p.add_argument("--ref", default=None, help="upstream commit to use as base (default: merge-base of HEAD and upstream/bugfix-2.1.x)")
    a = p.parse_args()
    a.ref = a.ref or subprocess.check_output(["git", "merge-base", "HEAD", "upstream/bugfix-2.1.x"], cwd=ROOT, text=True).strip()
    sys.exit({"derive": cmd_derive, "apply": cmd_apply, "check": cmd_check, "stale": cmd_stale}[a.command](a) or 0)
