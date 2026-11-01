"""Benchmark naive vs. RLE/bucket-sorted thumbnail rendering on the real
panel, using the DWIN handshake as an on-device timing checkpoint (see
tjc_dwin.Panel.handshake and AGENTS.md / the plan for why that's a valid
proxy for "panel finished processing the queued drawing commands", not just
host send time).

Two subcommands:

  validate   Sanity-checks the checkpoint itself: sends increasing amounts of
             drawing work and confirms latency scales with it, plus reports
             the idle round-trip baseline to subtract. Run this FIRST -- do
             not trust `run`'s numbers until this passes.

  run        The actual benchmark: clears the screen, draws the naive
             algorithm into the top half, checkpoints, draws the chosen
             encoder (--mode rle|bucket) into the bottom half, checkpoints,
             reports both timings and the speedup. Leaves both halves on
             screen so you can eyeball them against the source image and
             check for streak/corruption artifacts before trusting the
             timing.

--delay sets tjc_dwin.Panel's per-wire-frame throttle. It is NOT passed to
the blit_* functions -- see dwin_blit.py's module docstring for why an
earlier per-call version of this produced a misleading, unfair naive-vs-rle
comparison.

SAFETY: an unthrottled (delay=0) flood of ~2000 commands wedged the panel
hard enough this session that even a Nextion `rest` reset could not recover
it -- only a physical power cycle did. Never run `validate` or `run` with
--delay 0 at anything beyond a couple hundred commands.

Usage:
  python3 dwin_bench.py validate --port /dev/ttyUSB0
  python3 dwin_bench.py run some_thumbnail.png --port /dev/ttyUSB0 --delay 0.003
  python3 dwin_bench.py run some_thumbnail.png --delay 0.003 --mode bucket
"""

import argparse
import sys
import time

from PIL import Image

import tjc_dwin


def validate_checkpoint(panel, batch_sizes=(0, 100, 500)):
    """Two numbers matter here, and they mean different things:

    - total_time: wall clock from the first byte of the batch being written
      to the checkpoint reply arriving. pyserial's flush() blocks until the
      OS has physically clocked all bytes out, so this necessarily includes
      wire transmission time -- it *will* scale with N almost by definition
      (more bytes take longer to transmit at a fixed baud). This is the
      number that matters for real image timings (what dwin_bench.py `run`
      reports as wall time).
    - post_flush_gap: time from *after* flush() returns (i.e. after
      transmission is confirmed complete) to the checkpoint reply. This
      isolates backlog inside the panel that persists *beyond* wire time --
      i.e. whether the panel's own drawing is a second bottleneck on top of
      the serial link, or whether it keeps up with bytes in real time as they
      arrive (in which case this should stay small and roughly flat).
    """
    print("Validating the handshake checkpoint against increasing batch sizes.")
    print("total_time must scale with N (that's just wire transmission time).")
    print("post_flush_gap staying small/flat means the panel keeps up with the")
    print("wire in real time; growing with N would mean the panel itself, not")
    print("just the link, is falling behind.")
    print()
    results = []
    for n in batch_sizes:
        panel.clear(0x0000)
        panel.flush()
        time.sleep(0.2)
        t0 = time.perf_counter()
        for i in range(n):
            panel.fill_rect(0xF800, i % 200, 10, i % 200, 10)
        panel.flush()
        gap = panel.handshake()
        t_total = time.perf_counter() - t0
        results.append((n, t_total, gap))
        print(f"  batch={n:5d}  total_time={t_total*1000:7.1f} ms  post_flush_gap={gap*1000:6.1f} ms")

    print()
    total_scales = all(b[1] >= a[1] * 0.9 for a, b in zip(results, results[1:]))
    if total_scales:
        print("OK: total_time scales with batch size, as expected for a wire-bound link.")
    else:
        print("WARNING: total_time did NOT scale monotonically with batch size.")
        print("This usually means commands were dropped/corrupted under load")
        print("(exactly the streaking the panel is known to do when overwhelmed)")
        print("rather than the checkpoint being unreliable -- inspect the screen")
        print("after the largest batch for garbage before trusting any timing here.")
    return total_scales


def run_benchmark(panel, image_path, mode="rle"):
    import dwin_blit

    img = Image.open(image_path).convert("RGB")
    img.thumbnail((96, 96))
    w, h = img.size
    print(f"image: {image_path} ({w}x{h} after thumbnailing)")

    panel.clear(0x0000)
    panel.flush()
    time.sleep(0.3)
    baseline = panel.handshake()
    print(f"idle baseline: {baseline*1000:.1f} ms")

    top_x, top_y = 8, 8
    t0 = time.perf_counter()
    n_naive = dwin_blit.blit_naive(panel, img, top_x, top_y)
    panel.flush()
    t_naive = panel.handshake()
    t_naive_wall = time.perf_counter() - t0
    print(f"naive:  {n_naive} frames, checkpoint={t_naive*1000:.1f} ms, wall={t_naive_wall:.2f}s")

    encoder = dwin_blit.blit_bucketed if mode == "bucket" else dwin_blit.blit_rle
    bot_x, bot_y = 8, 8 + h + 8
    t0 = time.perf_counter()
    n_second = encoder(panel, img, bot_x, bot_y)
    panel.flush()
    t_second = panel.handshake()
    t_second_wall = time.perf_counter() - t0
    print(f"{mode}: {n_second} frames, checkpoint={t_second*1000:.1f} ms, wall={t_second_wall:.2f}s")

    print(f"speedup (wall time): {t_naive_wall/t_second_wall:.2f}x")
    print()
    print("Now check the screen: top half should be the naive render, bottom")
    print(f"half the {mode} render, both matching the source image with no")
    print("streaks/garbage. If corruption appears, re-run with a larger --delay.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate", help="sanity-check the timing checkpoint")
    p_validate.add_argument("--port", default="/dev/ttyUSB0")
    p_validate.add_argument("--baud", type=int, default=115200)
    p_validate.add_argument("--delay", type=float, default=0.0, help="per-wire-frame delay in seconds")
    p_validate.add_argument(
        "--batch",
        type=int,
        action="append",
        dest="batches",
        help="add a batch size to test (repeatable); default 0,100,500. "
        "DO NOT go far above 500 with --delay 0: an unthrottled flood of "
        "~2000 commands wedged the panel hard enough this session that even "
        "a Nextion `rest` reset could not recover it -- only a physical "
        "power cycle did. If you need to test near/above that range, use a "
        "nonzero --delay.",
    )

    p_run = sub.add_parser("run", help="run the naive-vs-encoder benchmark")
    p_run.add_argument("image")
    p_run.add_argument("--port", default="/dev/ttyUSB0")
    p_run.add_argument("--baud", type=int, default=115200)
    p_run.add_argument("--delay", type=float, default=0.0, help="per-wire-frame delay in seconds")
    p_run.add_argument("--mode", choices=("rle", "bucket"), default="rle", help="encoder to compare against naive")

    args = ap.parse_args()
    panel = tjc_dwin.Panel(args.port, args.baud, delay=args.delay)
    try:
        panel.handshake()  # confirm connectivity before anything else
        if args.cmd == "validate":
            batches = tuple(args.batches) if args.batches else (0, 100, 500)
            ok = validate_checkpoint(panel, batch_sizes=batches)
            sys.exit(0 if ok else 1)
        elif args.cmd == "run":
            run_benchmark(panel, args.image, mode=args.mode)
    finally:
        panel.close()


if __name__ == "__main__":
    main()
