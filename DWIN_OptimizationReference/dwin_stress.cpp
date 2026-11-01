// Continuous stress test for the TJC panel: repeatedly draws a randomly
// chosen real thumbnail (from dump_thumb_commands.py --relative output, one
// file per real thumbnail_N.gcode) at a random on-screen position, with NO
// clearing -- neither of the whole screen nor of the space behind the next
// draw. Thumbnails pile up and overlap indefinitely. Any timing/throttle
// bug shows up as an obvious visual glitch against a screen that is already
// visually busy, which is a harder test than a single clean render: it
// exercises long, varied, back-to-back command bursts exactly like a real
// print queue flipping through thumbnails would, without the "start from a
// clean screen" advantage every other tool here gives each attempt.
//
// Uses the same throttle strategies as dwin_replay.cpp (per-frame, batch-all,
// batch-fill), sharing the wire protocol code from dwin_wire.h.
//
// Build:   g++ -O2 -std=c++17 -o dwin_stress dwin_stress.cpp
// Usage:   ./dwin_stress --port /dev/ttyUSB0 --dir DWIN_OptimizationReference/stress_cmds \
//              --per:1:200
//          ./dwin_stress --port /dev/ttyUSB0 --batch:30:25 --iterations 500
//
// Stop with Ctrl+C; a summary (iteration count, elapsed, avg/min/max per
// iteration) prints once the in-flight draw finishes.
//
// SAFETY: same as dwin_replay.cpp -- never disable throttling entirely.

#include <algorithm>
#include <chrono>
#include <csignal>
#include <cstring>
#include <random>
#include <vector>
#include <dirent.h>

#include "dwin_wire.h"

namespace {

volatile sig_atomic_t g_stop = 0;
void handle_sigint(int) { g_stop = 1; }

struct StressCmd {
  bool is_set;
  uint16_t color;                     // valid when is_set
  uint16_t x0, y0, x1, y1;            // valid when !is_set; relative to thumbnail origin (0..95)
};

struct Thumbnail {
  std::string name;
  std::vector<StressCmd> cmds;
};

std::vector<StressCmd> parse_relative_commands(const std::string &path) {
  auto lines = load_commands(path);
  std::vector<StressCmd> cmds;
  cmds.reserve(lines.size());
  for (const auto &line : lines) {
    if (line.empty() || line[0] == '#') continue;
    char kind;
    unsigned a1, a2, a3, a4;
    if (line[0] == 'S') {
      sscanf(line.c_str(), "%c %x", &kind, &a1);
      cmds.push_back({true, uint16_t(a1), 0, 0, 0, 0});
    } else if (line[0] == 'F') {
      sscanf(line.c_str(), "%c %u %u %u %u", &kind, &a1, &a2, &a3, &a4);
      cmds.push_back({false, 0, uint16_t(a1), uint16_t(a2), uint16_t(a3), uint16_t(a4)});
    }
  }
  return cmds;
}

std::vector<Thumbnail> load_thumbnails_from_dir(const std::string &dir) {
  std::vector<Thumbnail> out;
  DIR *d = opendir(dir.c_str());
  if (!d) {
    perror(("opendir " + dir).c_str());
    exit(1);
  }
  std::vector<std::string> names;
  while (dirent *e = readdir(d)) {
    std::string name = e->d_name;
    if (name.size() > 4 && name.substr(name.size() - 4) == ".txt")
      names.push_back(name);
  }
  closedir(d);
  std::sort(names.begin(), names.end());
  for (auto &name : names) {
    Thumbnail t;
    t.name = name;
    t.cmds = parse_relative_commands(dir + "/" + name);
    if (!t.cmds.empty()) out.push_back(std::move(t));
  }
  return out;
}

void print_usage(const char *argv0) {
  fprintf(stderr,
    "usage: %s --port <dev> [--dir <dir>] [file1.txt file2.txt ...] [options]\n"
    "\n"
    "Loads one or more relative-coordinate command files (see\n"
    "dump_thumb_commands.py --relative), each a real thumbnail's bucketed\n"
    "draw sequence with coordinates in 0..95, local to its own origin.\n"
    "--dir scans a directory for *.txt (default: DWIN_OptimizationReference/stress_cmds).\n"
    "Explicit file arguments override --dir.\n"
    "\n"
    "Every iteration picks one thumbnail and one random position uniformly in\n"
    "x in [0, 240-96], y in [0, 320-96], and draws it there -- no clearing,\n"
    "ever, of the screen or of the space behind the new draw.\n"
    "\n"
    "Throttle strategy (same as dwin_replay.cpp; pick one):\n"
    "  --base-delay-ms <n> [--row-us <n>]      per-frame (default)\n"
    "  --batch-size <n> --batch-delay-ms <n>    batch-all (matches original firmware: 30, 25)\n"
    "  --fill-batch-size <n> --fill-batch-delay-ms <n>   batch-fill\n"
    "  --strategy-spec <kind:a:b>                shorthand, e.g. per:1:200 or batch:30:25\n"
    "\n"
    "  --interbyte-us <n>   delay between individual wire bytes, default 1\n"
    "  --iterations <n>     stop after n draws (default 0 = run until Ctrl+C)\n"
    "  --seed <n>           RNG seed (default: random, printed at startup for repro)\n"
    "\n"
    "Stop with Ctrl+C -- the current draw finishes, then a summary prints.\n",
    argv0);
}

} // namespace

int main(int argc, char **argv) {
  Options opt;
  std::string dir = "DWIN_OptimizationReference/stress_cmds";
  std::vector<std::string> explicit_files;
  long iterations = 0; // 0 = unbounded
  unsigned seed = std::random_device{}();
  bool seed_set = false;

  for (int i = 1; i < argc; i++) {
    std::string a = argv[i];
    auto next = [&]() -> std::string {
      if (i + 1 >= argc) { print_usage(argv[0]); exit(1); }
      return argv[++i];
    };
    if (a == "--port") opt.port = next();
    else if (a == "--dir") dir = next();
    else if (a == "--baud") opt.baud = std::stoi(next());
    else if (a == "--base-delay-ms") { opt.base_delay_ms = std::stod(next()); opt.strategy = Strategy::PerFrame; }
    else if (a == "--set-delay-ms") opt.set_delay_ms = std::stod(next());
    else if (a == "--row-us") opt.row_us = std::stoi(next());
    else if (a == "--batch-size") { opt.batch_size = std::stoi(next()); opt.strategy = Strategy::BatchAll; }
    else if (a == "--batch-delay-ms") opt.batch_delay_ms = std::stod(next());
    else if (a == "--fill-batch-size") { opt.fill_batch_size = std::stoi(next()); opt.strategy = Strategy::BatchFill; }
    else if (a == "--fill-batch-delay-ms") opt.fill_batch_delay_ms = std::stod(next());
    else if (a == "--strategy-spec") parse_throttle_spec(next(), opt);
    else if (a == "--interbyte-us") opt.interbyte_us = std::stoi(next());
    else if (a == "--iterations") iterations = std::stol(next());
    else if (a == "--seed") { seed = uint32_t(std::stoul(next())); seed_set = true; }
    else if (a == "-h" || a == "--help") { print_usage(argv[0]); return 0; }
    else if (!a.empty() && a[0] == '-') { fprintf(stderr, "unknown arg: %s\n", a.c_str()); print_usage(argv[0]); return 1; }
    else explicit_files.push_back(a);
  }
  if (opt.port.empty()) {
    print_usage(argv[0]);
    return 1;
  }

  std::vector<Thumbnail> thumbs;
  if (!explicit_files.empty()) {
    for (auto &f : explicit_files) {
      Thumbnail t;
      t.name = f;
      t.cmds = parse_relative_commands(f);
      if (!t.cmds.empty()) thumbs.push_back(std::move(t));
    }
  } else {
    thumbs = load_thumbnails_from_dir(dir);
  }
  if (thumbs.empty()) {
    fprintf(stderr, "no usable command files found (checked %s)\n",
            explicit_files.empty() ? dir.c_str() : "the given file list");
    return 1;
  }

  printf("Loaded %zu thumbnail(s):\n", thumbs.size());
  for (auto &t : thumbs) printf("  %-30s %zu commands\n", t.name.c_str(), t.cmds.size());
  printf("Throttle: %s interbyte_us=%d\n", describe_settings(opt).c_str(), opt.interbyte_us);
  printf("Seed: %u%s\n", seed, seed_set ? "" : " (random -- pass --seed to reproduce this run)");
  printf("Never clearing. Positions uniform in x[0,%d] y[0,%d]. Ctrl+C to stop.\n\n",
         SCREEN_X1 + 1 - THUMB_SIZE, SCREEN_Y1 + 1 - THUMB_SIZE);

  signal(SIGINT, handle_sigint);

  std::mt19937 rng(seed);
  std::uniform_int_distribution<size_t> dist_thumb(0, thumbs.size() - 1);
  std::uniform_int_distribution<int> dist_x(0, SCREEN_X1 + 1 - THUMB_SIZE);
  std::uniform_int_distribution<int> dist_y(0, SCREEN_Y1 + 1 - THUMB_SIZE);

  int fd = open_serial(opt.port, opt.baud);
  usleep(300000); // let the panel settle after DTR/RTS toggle on port open

  long count = 0;
  double total_secs = 0.0, min_secs = -1.0, max_secs = 0.0;
  const auto run_t0 = std::chrono::steady_clock::now();

  while (!g_stop && (iterations == 0 || count < iterations)) {
    const size_t idx = dist_thumb(rng);
    const int x = dist_x(rng), y = dist_y(rng);
    const Thumbnail &t = thumbs[idx];

    printf("[%ld] %s at (%d,%d)... ", count + 1, t.name.c_str(), x, y);
    fflush(stdout);

    // No output during the send loop itself -- see dwin_replay.cpp's
    // run_replay() for why (terminal I/O jitter inside the UART timing
    // loop is a candidate source of the exact flakiness this tool exists
    // to expose or rule out).
    ThrottleState st;
    const auto t0 = std::chrono::steady_clock::now();
    for (const auto &c : t.cmds) {
      if (c.is_set) set_color(fd, c.color, opt, st);
      else fill_rect(fd, uint16_t(x + c.x0), uint16_t(y + c.y0), uint16_t(x + c.x1), uint16_t(y + c.y1), opt, st);
    }
    const auto t1 = std::chrono::steady_clock::now();
    const double secs = std::chrono::duration<double>(t1 - t0).count();

    printf("%.2fs\n", secs);

    count++;
    total_secs += secs;
    if (min_secs < 0 || secs < min_secs) min_secs = secs;
    if (secs > max_secs) max_secs = secs;
  }

  const auto run_t1 = std::chrono::steady_clock::now();
  close(fd);

  printf("\n=== Stress test summary ===\n");
  printf("  Iterations: %ld\n", count);
  printf("  Wall time:  %.1fs\n", std::chrono::duration<double>(run_t1 - run_t0).count());
  if (count > 0) {
    printf("  Per-iteration: avg=%.2fs min=%.2fs max=%.2fs\n", total_secs / count, min_secs, max_secs);
  }
  return 0;
}
