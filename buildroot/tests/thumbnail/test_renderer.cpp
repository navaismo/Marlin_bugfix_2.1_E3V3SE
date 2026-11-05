// Exercise the production renderer through its card, palette, rectangle and
// pacing interfaces. The reference is the input image, not another RLE encoder.
#include "mock.h"
#include <array>
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <vector>

bool DWIN_RenderThumb(const char*);
Card card;
HAL hal;

using Row = std::vector<uint16_t>;
using Image = std::vector<Row>;
static std::array<uint16_t, 96 * 96> canvas, expected;
static std::array<unsigned, 96 * 96> writes;
static uint16_t palette;
static bool palette_set;
static unsigned frames, palettes, rectangles, pauses, refreshes, pending_frames;
static unsigned cases, total_frames, max_burst;
static uint64_t clock_us, last_refresh_us, max_refresh_gap_us;
static std::string case_name;

static void require(bool ok, const char *message) {
  if (!ok) throw std::runtime_error(case_name + ": " + message);
}

static void frame(unsigned bytes) {
  ++frames;
  ++pending_frames;
  max_burst = std::max(max_burst, pending_frames);
  require(pending_frames <= 10, "more than ten commands without the existing pause");
  // Nominal 8N1 wire time at LCD_BAUDRATE=115200 plus the existing 1us/byte.
  // This is a model, not a measurement of panel processing or UART buffering.
  clock_us += (uint64_t(bytes) * 10000000 + 115199) / 115200 + bytes;
}

void delay(int ms) {
  require(ms == 16, "DWIN pause changed");
  require(pending_frames == 10, "pause is not after ten commands");
  pending_frames = 0;
  ++pauses;
  clock_us += uint64_t(ms) * 1000;
}

void HAL::watchdog_refresh() {
  max_refresh_gap_us = std::max(max_refresh_gap_us, clock_us - last_refresh_us);
  last_refresh_us = clock_us;
  ++refreshes;
}

void DWIN_Set_Color(uint16_t foreground, uint16_t background) {
  require(foreground != 0 && background == 0xFFFF, "invalid palette transition");
  palette = foreground;
  palette_set = true;
  ++palettes;
  frame(10);
}

void DWIN_Fill_Rect_Raw(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
  require(palette_set, "rectangle sent before palette");
  require(x0 >= 12 && y0 >= 25 && x1 < 12 + 96 && y1 < 25 + 96,
          "rectangle outside thumbnail");
  require(x0 <= x1 && y0 <= y1, "inverted rectangle");
  for (unsigned y = y0 - 25; y <= unsigned(y1 - 25); ++y)
    for (unsigned x = x0 - 12; x <= unsigned(x1 - 12); ++x) {
      const unsigned i = y * 96 + x;
      canvas[i] = palette;
      ++writes[i];
    }
  ++rectangles;
  frame(14);
}

static std::string encode(const Image &image, unsigned width, unsigned height) {
  std::string text = "; E3V3SE_THUMB_RAW16_BEGIN " + std::to_string(width)
                   + "x" + std::to_string(height) + "\n";
  for (const Row &row : image) {
    text += "; ";
    for (const uint16_t pixel : row) {
      char hex[5];
      std::snprintf(hex, sizeof(hex), "%04X", pixel);
      text += hex;
    }
    text += '\n';
  }
  return text;
}

static void check(const std::string &name, const std::string &input,
                  const Image &valid_rows, bool result, bool fail_open = false,
                  int expected_rectangles = -1) {
  case_name = name;
  for (unsigned i = 0; i < canvas.size(); ++i)
    canvas[i] = expected[i] = uint16_t(0x4000 + i);
  writes.fill(0);
  for (unsigned y = 0; y < valid_rows.size(); ++y)
    for (unsigned x = 0; x < valid_rows[y].size(); ++x)
      if (valid_rows[y][x]) expected[y * 96 + x] = valid_rows[y][x];
  frames = palettes = rectangles = pauses = refreshes = 0;
  palette_set = false;
  const unsigned previous_pending = pending_frames;
  card.contents = input;
  card.fail_open = fail_open;
  card.closes = 0;
  const uint64_t started_us = clock_us;
  require(DWIN_RenderThumb(name.c_str()) == result, "unexpected return value");
  require(!card.opened && card.closes == unsigned(!fail_open), "file not closed correctly");
  require(canvas == expected, "rendered pixels differ from source image");
  for (unsigned y = 0; y < 96; ++y)
    for (unsigned x = 0; x < 96; ++x) {
      const bool drawn = y < valid_rows.size() && x < valid_rows[y].size() && valid_rows[y][x];
      require(writes[y * 96 + x] == unsigned(drawn), "dropped, duplicated or background pixel");
    }
  require(pauses == (previous_pending + frames) / 10, "missing pacing delay");
  require(pending_frames == (previous_pending + frames) % 10, "pacing lost across renders");
  require(refreshes >= frames + 1, "missing per-frame watchdog refresh");
  if (expected_rectangles >= 0)
    require(rectangles == unsigned(expected_rectangles), "vertical merging changed");
  total_frames += frames;
  ++cases;
  std::cout << "PASS " << name << ": palette=" << palettes << " fill=" << rectangles
            << " pause16ms=" << pauses << " watchdog=" << refreshes
            << " nominal_us=" << clock_us - started_us << '\n';
}

static void complete(const std::string &name, const Image &image, int rectangles = -1) {
  check(name, encode(image, image.front().size(), image.size())
             + "; E3V3SE_THUMB_RAW16_END\n", image, true, false, rectangles);
}

int main() {
  try {
    Image image(96, Row(96, 0xF800));
    complete("solid-96x96", image, 1);
    for (unsigned y = 0; y < 96; ++y)
      for (unsigned x = 0; x < 96; ++x) image[y][x] = 1 + (x + y) % 2;
    complete("checkerboard-96x96-repeated-flushes", image, 96 * 96);
    for (unsigned y = 0; y < 96; ++y)
      for (unsigned x = 0; x < 96; ++x) image[y][x] = 1 + x % 2;
    complete("96-vertically-merged-columns", image, 96);
    for (unsigned y = 0; y < 96; ++y)
      for (unsigned x = 0; x < 96; ++x) image[y][x] = 1 + y;
    complete("horizontal-stripes", image, 96);
    for (unsigned y = 0; y < 96; ++y)
      for (unsigned x = 0; x < 96; ++x) image[y][x] = uint16_t(y * 96 + x + 1);
    complete("9216-distinct-colors", image, 96 * 96);
    for (Row &row : image) std::fill(row.begin(), row.end(), 0);
    complete("all-background", image, 0);
    require(refreshes >= 97, "background rows do not refresh watchdog");
    for (unsigned y = 0; y < 96; ++y)
      for (unsigned x = 0; x < 96; ++x) image[y][x] = (x + y) % 3 ? 0x07E0 : 0;
    complete("background-gaps", image);
    for (unsigned y = 0; y < 96; ++y)
      for (unsigned x = 0; x < 96; ++x) image[y][x] = y % 7 ? 1 + x % 2 : 0;
    complete("merging-separated-by-background-rows", image);

    Image overflow(17, Row(96));
    for (unsigned y = 0; y < 17; ++y)
      for (unsigned x = 0; x < 96; ++x)
        overflow[y][x] = y == 15 && x >= 40 ? 0 : 1 + (x + y) % 2;
    complete("original-overflow-1480-plus-96-runs", overflow);

    Image prefix(image.begin(), image.begin() + 23);
    check("truncated-mid-row", encode(prefix, 96, 96) + "; 1234ABCD\n", prefix, true);
    check("truncated-eof", encode(prefix, 96, 96), prefix, true);
    check("early-end-marker", encode(prefix, 96, 96) + "; E3V3SE_THUMB_RAW16_END\n",
          prefix, true);
    check("truncated-first-row", "; E3V3SE_THUMB_RAW16_BEGIN 96x96\n; 1234\n", {}, false);
    check("header-without-data", "; E3V3SE_THUMB_RAW16_BEGIN 96x96\n", {}, false);
    check("missing-header", "G28\n; unrelated comment\n", {}, false);
    check("open-failure", "", {}, false, true);
    complete("one-pixel", Image(1, Row(1, 0xFFFF)), 1);
    complete("narrow-image", Image(96, Row(13, 0x001F)), 1);

    uint32_t random = 0x495512;
    for (unsigned sample = 0; sample < 24; ++sample) {
      for (unsigned y = 0; y < 96; ++y)
        for (unsigned x = 0; x < 96; ++x) {
          random = random * 1664525u + 1013904223u;
          image[y][x] = sample % 2 ? uint16_t(random >> 16) : uint16_t((random >> 16) % 5);
          if (sample % 3 == 0 && y % 3 && y) image[y][x] = image[y - 1][x];
        }
      complete("random-" + std::to_string(sample), image);
    }
    require(max_refresh_gap_us < 20000, "nominal watchdog service gap changed");
    std::cout << "PASS " << cases << " images, " << total_frames
              << " commands; maximum burst=" << max_burst
              << ", nominal max watchdog gap=" << max_refresh_gap_us << "us\n";
  }
  catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
