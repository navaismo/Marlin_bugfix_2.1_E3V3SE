// Standalone serial replay tool for tuning DWIN_RenderThumb's inter-command
// delay against the real TJC panel, and for benchmarking the original
// per-pixel algorithm against the new bucketed one, without recompiling or
// reflashing Marlin for every experiment.
//
// Wire protocol and throttle strategies live in dwin_wire.h, shared with
// dwin_stress.cpp.
//
// Command list format (see dump_thumb_commands.py --mode bucketed|naive,
// which generates one from a real thumbnail using the exact same algorithm
// as the corresponding DWIN_RenderThumb version):
//   S <RRGGBB-as-565-hex>          -- DWIN_Set_Color(color, 0xFFFF)
//   F <x0> <y0> <x1> <y1>          -- DWIN_Fill_Rect_Raw(x0, y0, x1, y1)
//
// Build:   g++ -O2 -std=c++17 -o dwin_replay dwin_replay.cpp
//
// Single-file usage (tune one side):
//   ./dwin_replay --port /dev/ttyUSB0 --file thumb1_bucketed.txt \
//       --base-delay-ms 3 --row-us 500 --clear
//
// Benchmark original vs new on real hardware in one run:
//   ./dwin_replay --port /dev/ttyUSB0 \
//       --compare thumb1_naive.txt thumb1_bucketed.txt
//
// SAFETY: an unthrottled flood of DWIN commands has previously overrun this
// panel's input buffer badly enough to require a PHYSICAL POWER CYCLE to
// recover (see tjc_dwin.py). Never run with all throttling disabled. Start
// conservative and reduce delays gradually.

#include <cctype>
#include <chrono>
#include <cstring>
#include <vector>

#include "dwin_wire.h"

namespace {

// Replays one command file over an already-open port, returns elapsed
// wall-clock seconds for the drawing phase (excludes the optional clear).
double run_replay(int fd, const std::vector<std::string> &lines, const Options &opt) {
  if (opt.clear_first) {
    ThrottleState clear_st;
    printf("  Clearing screen...\n");
    set_color(fd, 0x0000, opt, clear_st);
    fill_rect(fd, SCREEN_X0, SCREEN_Y0, SCREEN_X1, SCREEN_Y1, opt, clear_st);
    usleep(50000);
  }

  // No output at all during the loop below: an interleaved printf/fflush
  // to the terminal on every command (or even every Nth) was a candidate
  // source of scheduling jitter right inside the UART timing loop, which
  // would confound exactly the delay-tuning this tool exists to do. Only
  // the caller's before/after prints (name, then elapsed time) bracket it.
  ThrottleState st;
  const size_t n = lines.size();
  const auto t0 = std::chrono::steady_clock::now();
  for (size_t i = 0; i < n; i++) {
    const std::string &line = lines[i];
    if (line.empty() || line[0] == '#') continue;
    char kind;
    unsigned a1, a2, a3, a4;
    if (line[0] == 'S') {
      sscanf(line.c_str(), "%c %x", &kind, &a1);
      set_color(fd, uint16_t(a1), opt, st);
    } else if (line[0] == 'F') {
      sscanf(line.c_str(), "%c %u %u %u %u", &kind, &a1, &a2, &a3, &a4);
      fill_rect(fd, uint16_t(a1), uint16_t(a2), uint16_t(a3), uint16_t(a4), opt, st);
    }
  }
  const auto t1 = std::chrono::steady_clock::now();
  return std::chrono::duration<double>(t1 - t0).count();
}

// Clears the WHOLE screen using the historically-proven-safe per-frame
// preset, regardless of whatever throttle the sweep is currently testing.
// Used only for the post-failure recovery clear between sweep configs --
// never for measurement, so it must not use a config that might itself be
// the thing under test. Whole-screen (not just the thumbnail box) so any
// glitched pixels that spilled past the intended bounds are wiped too.
void safe_clear(int fd, const Options &base_opt) {
  Options safe_opt = base_opt;
  safe_opt.strategy = Strategy::PerFrame;
  safe_opt.base_delay_ms = NEW_BASE_DELAY_MS;
  safe_opt.row_us = NEW_ROW_US;
  safe_opt.set_delay_ms = -1.0;
  ThrottleState st;
  set_color(fd, 0x0000, safe_opt, st);
  fill_rect(fd, SCREEN_X0, SCREEN_Y0, SCREEN_X1, SCREEN_Y1, safe_opt, st);
  usleep(50000);
}

void print_usage(const char *argv0) {
  fprintf(stderr,
    "usage: %s --port <dev> --file <commands.txt> [options]\n"
    "   or: %s --port <dev> --compare <naive.txt> <bucketed.txt>\n"
    "   or: %s --port <dev> --file <commands.txt> --sweep <spec1,spec2,...>\n"
    "\n"
    "Throttle strategies (pick one; the last-set one wins if flags for\n"
    "more than one are given):\n"
    "  --base-delay-ms <n> [--row-us <n>]   per-frame: delay after every frame\n"
    "                                        (default), plus optional extra\n"
    "                                        delay per row of a tall FILL.\n"
    "  --batch-size <n> --batch-delay-ms <n>   batch-all: delay every N frames,\n"
    "                                        counting SET and FILL together\n"
    "                                        (matches the ORIGINAL firmware:\n"
    "                                        --batch-size 30 --batch-delay-ms 25).\n"
    "  --fill-batch-size <n> --fill-batch-delay-ms <n>   batch-fill: delay only\n"
    "                                        every N rect-FILL commands; SET\n"
    "                                        (palette) frames never delay.\n"
    "\n"
    "  --set-delay-ms <n>    per-frame strategy only: override delay after SET frames\n"
    "  --interbyte-us <n>    delay between individual wire bytes, default 1\n"
    "  --clear               fill the whole screen black before replaying\n"
    "\n"
    "Delay values (--base-delay-ms, --set-delay-ms, --batch-delay-ms,\n"
    "--fill-batch-delay-ms) accept fractional milliseconds, e.g. 0.5.\n"
    "\n"
    "--compare runs <naive.txt> with the original firmware's proven batch-all\n"
    "throttle (batch-size %d, batch-delay-ms %g) and <bucketed.txt> with the\n"
    "new firmware's proven per-frame throttle (base-delay-ms %g, row-us %d),\n"
    "pausing between the two so you can inspect the panel, and prints a\n"
    "timing comparison. Any explicit throttle flags given override the\n"
    "matching preset for that run.\n"
    "\n"
    "--sweep runs <commands.txt> once per comma-separated spec, each of the form\n"
    "  per:<base_delay_ms>:<row_us>\n"
    "  batch:<batch_size>:<batch_delay_ms>\n"
    "  fillbatch:<fill_batch_size>:<delay_ms>\n"
    "pausing after each to ask for a verdict (o=ok, f=fail, or a free note).\n"
    "Any verdict other than exactly 'o' clears the panel with the proven-safe\n"
    "preset and pauses again before the next config, so a glitch never bleeds\n"
    "into the next config's own leading clear -- this recovery step is not\n"
    "timed or counted in the results. Prints a table of every config's timing\n"
    "and verdict at the end. Example:\n"
    "  --sweep per:3:500,per:2:300,per:1:200,fillbatch:5:15,fillbatch:10:20\n",
    argv0, argv0, argv0, ORIGINAL_BATCH_SIZE, ORIGINAL_BATCH_DELAY_MS, NEW_BASE_DELAY_MS, NEW_ROW_US);
}

} // namespace

int main(int argc, char **argv) {
  Options opt;
  std::string compare_naive, compare_bucketed;
  std::vector<std::string> sweep_specs;
  bool do_compare = false;
  bool batch_size_set = false, base_delay_set = false, row_us_set = false;

  for (int i = 1; i < argc; i++) {
    std::string a = argv[i];
    auto next = [&]() -> std::string {
      if (i + 1 >= argc) { print_usage(argv[0]); exit(1); }
      return argv[++i];
    };
    if (a == "--port") opt.port = next();
    else if (a == "--file") opt.file = next();
    else if (a == "--compare") { do_compare = true; compare_naive = next(); compare_bucketed = next(); }
    else if (a == "--sweep") sweep_specs = split_commas(next());
    else if (a == "--baud") opt.baud = std::stoi(next());
    else if (a == "--base-delay-ms") { opt.base_delay_ms = std::stod(next()); opt.strategy = Strategy::PerFrame; base_delay_set = true; }
    else if (a == "--set-delay-ms") opt.set_delay_ms = std::stod(next());
    else if (a == "--row-us") { opt.row_us = std::stoi(next()); row_us_set = true; }
    else if (a == "--batch-size") { opt.batch_size = std::stoi(next()); opt.strategy = Strategy::BatchAll; batch_size_set = true; }
    else if (a == "--batch-delay-ms") opt.batch_delay_ms = std::stod(next());
    else if (a == "--fill-batch-size") { opt.fill_batch_size = std::stoi(next()); opt.strategy = Strategy::BatchFill; }
    else if (a == "--fill-batch-delay-ms") opt.fill_batch_delay_ms = std::stod(next());
    else if (a == "--interbyte-us") opt.interbyte_us = std::stoi(next());
    else if (a == "--clear") opt.clear_first = true;
    else if (a == "-h" || a == "--help") { print_usage(argv[0]); return 0; }
    else { fprintf(stderr, "unknown arg: %s\n", a.c_str()); print_usage(argv[0]); return 1; }
  }
  if (opt.port.empty() || (!do_compare && sweep_specs.empty() && opt.file.empty())) {
    print_usage(argv[0]);
    return 1;
  }
  if (!sweep_specs.empty() && opt.file.empty()) {
    fprintf(stderr, "--sweep requires --file\n");
    return 1;
  }

  int fd = open_serial(opt.port, opt.baud);
  usleep(300000); // let the panel settle after DTR/RTS toggle on port open, matches tjc_dwin.py

  if (!do_compare && sweep_specs.empty()) {
    auto lines = load_commands(opt.file);
    printf("Loaded %zu commands from %s\n", lines.size(), opt.file.c_str());
    printf("Settings: %s interbyte_us=%d\n", describe_settings(opt).c_str(), opt.interbyte_us);
    opt.clear_first = true;
    const double secs = run_replay(fd, lines, opt);
    printf("Done in %.2fs.\n", secs);
    close(fd);
    return 0;
  }

  if (!sweep_specs.empty()) {
    // Human-in-the-loop sweep: run each config in turn, pause for the
    // operator to inspect the panel and type a verdict, then print a full
    // summary table at the end. There is no automatic corruption
    // detection -- only the operator watching the physical screen can
    // tell a glitch from a clean render.
    auto lines = load_commands(opt.file);
    printf("Loaded %zu commands from %s\n", lines.size(), opt.file.c_str());
    printf("Sweeping %zu configuration(s).\n\n", sweep_specs.size());

    struct Result { std::string desc; double secs; std::string verdict; };
    std::vector<Result> results;

    for (size_t i = 0; i < sweep_specs.size(); i++) {
      Options run_opt = opt;
      parse_throttle_spec(sweep_specs[i], run_opt);
      run_opt.clear_first = true;

      printf("=== [%zu/%zu] %s ===\n", i + 1, sweep_specs.size(), describe_settings(run_opt).c_str());
      const double secs = run_replay(fd, lines, run_opt);
      printf("Done in %.2fs.\n", secs);

      printf("Verdict? (o=ok, f=fail/glitched, anything else = note it verbatim): ");
      fflush(stdout);
      char verdict_buf[128] = {0};
      if (fgets(verdict_buf, sizeof(verdict_buf), stdin)) {
        size_t vlen = strlen(verdict_buf);
        if (vlen && verdict_buf[vlen - 1] == '\n') verdict_buf[vlen - 1] = '\0';
      }
      results.push_back({describe_settings(run_opt), secs, verdict_buf});

      // A failed config can leave the panel mid-corruption, which would
      // taint the *next* config's own leading clear (drawn with that next
      // config's own, possibly still-risky throttle) and make it hard to
      // tell a fresh glitch from leftover garbage. Recover with a clear at
      // the proven-safe preset instead, and pause for the operator to
      // confirm the panel is clean before continuing. Neither step is
      // timed or otherwise counted in the results above.
      if (tolower(verdict_buf[0]) != 'o') {
        printf("Previous config failed -- clearing with the safe preset before continuing.\n");
        safe_clear(fd, opt);
        printf("Confirm the panel is clear, then press Enter to continue to the next config...\n");
        getchar();
      }
      printf("\n");
    }

    printf("=== Sweep summary ===\n");
    for (auto &r : results)
      printf("  %-55s %7.2fs  %s\n", r.desc.c_str(), r.secs, r.verdict.c_str());

    close(fd);
    return 0;
  }

  // --compare: run the original algorithm's command list with its
  // historically-correct batched throttle, then the new algorithm's list
  // with its historically-correct per-frame throttle, pausing between so
  // the operator can inspect the panel before it's overwritten.
  Options naive_opt = opt;
  naive_opt.file = compare_naive;
  naive_opt.clear_first = true;
  naive_opt.strategy = Strategy::BatchAll;
  if (!batch_size_set) naive_opt.batch_size = ORIGINAL_BATCH_SIZE;
  naive_opt.batch_delay_ms = opt.batch_delay_ms; // already defaults to 25

  Options bucketed_opt = opt;
  bucketed_opt.file = compare_bucketed;
  bucketed_opt.clear_first = true;
  bucketed_opt.strategy = Strategy::PerFrame; // force per-frame model regardless of naive_opt above
  if (!base_delay_set) bucketed_opt.base_delay_ms = NEW_BASE_DELAY_MS;
  if (!row_us_set) bucketed_opt.row_us = NEW_ROW_US;

  auto naive_lines = load_commands(compare_naive);
  auto bucketed_lines = load_commands(compare_bucketed);

  printf("=== Original algorithm: %s ===\n", compare_naive.c_str());
  printf("Loaded %zu commands. Settings: %s\n", naive_lines.size(), describe_settings(naive_opt).c_str());
  const double naive_secs = run_replay(fd, naive_lines, naive_opt);
  printf("Original algorithm done in %.2fs.\n\n", naive_secs);

  printf("Inspect the panel now. Press Enter to continue to the new algorithm...\n");
  getchar();

  printf("=== New (bucketed) algorithm: %s ===\n", compare_bucketed.c_str());
  printf("Loaded %zu commands. Settings: %s\n", bucketed_lines.size(), describe_settings(bucketed_opt).c_str());
  const double bucketed_secs = run_replay(fd, bucketed_lines, bucketed_opt);
  printf("New algorithm done in %.2fs.\n\n", bucketed_secs);

  printf("=== Summary ===\n");
  printf("  Original: %8.2fs  (%zu commands)\n", naive_secs, naive_lines.size());
  printf("  New:      %8.2fs  (%zu commands)\n", bucketed_secs, bucketed_lines.size());
  if (bucketed_secs > 0)
    printf("  Speedup:  %.2fx\n", naive_secs / bucketed_secs);

  close(fd);
  return 0;
}
