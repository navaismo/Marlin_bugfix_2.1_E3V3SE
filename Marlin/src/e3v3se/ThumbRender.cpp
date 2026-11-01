/**
 * E3V3SE thumbnail renderer: reads the E3V3SE_THUMB_RAW16 block from the
 * G-code on the SD card and blits it to the DWIN panel (RLE + vertical merge,
 * palette-bucketed, throttled). Moved out of dwin_lcd.cpp; behavior unchanged.
 */
#include "../inc/MarlinConfigPre.h"
#include "../inc/MarlinConfig.h"

#if ALL(DWIN_CREALITY_LCD, DWIN_RENDER_THUMBNAIL)

#include "../lcd/dwin/creality/dwin_lcd.h"
#include "../sd/cardreader.h"
#include "../HAL/shared/Delay.h"
#include <string.h>
#include <stdio.h>

// Thumbnail read/write routines
bool gcode_readline(char *buffer, const size_t bufsize) {
  size_t i = 0;
  while (!card.eof()) {
    int16_t c = card.get();
    if (c < 0) break;
    if (c == '\n' || c == '\r') {
      if (i == 0) continue;       // skip consecutive empty lines
      break;
    }
    if (i + 1 < bufsize)         // leave space for '\0'
      buffer[i++] = char(c);
  }
  buffer[i] = '\0';
  return i > 0;
}




static uint16_t parse_hex4(const char *p) {
  uint16_t v = 0;
  for (uint8_t i = 0; i < 4; i++) {
    const char c = p[i];
    uint8_t n;
    if      (c >= '0' && c <= '9') n = c - '0';
    else if (c >= 'A' && c <= 'F') n = c - 'A' + 10;
    else if (c >= 'a' && c <= 'f') n = c - 'a' + 10;
    else return 0;  // unexpected character -> black color
    v = (v << 4) | n;
  }
  return v;
}


bool find_thumb_raw16_header(uint16_t &w, uint16_t &h) {
  char line[96];

  // Always start from the beginning of the file
  card.setIndex(0);

  uint16_t line_count = 0;

  while (line_count < 50 && gcode_readline(line, sizeof(line))) {
    line_count++;

    if (line[0] != ';') continue;

    char *p = line + 1;
    while (*p == ' ') p++;

    // Buscamos: "; E3V3SE_THUMB_RAW16_BEGIN 96x96"
    if (strncmp(p, "E3V3SE_THUMB_RAW16_BEGIN", 24) == 0) {
      uint16_t tw = 0, th = 0;

      // Try to parse the "96x96" that comes right after
      if (sscanf(p + 24, "%hu%*c%hu", &tw, &th) == 2) {
        w = tw;
        h = th;
      }
      else {
        w = 96;
        h = 96;
      }

      return true;
    }
  }

  return false;
}


static constexpr uint16_t THUMB_X_START = 12;
static constexpr uint16_t THUMB_Y_START = 25;

// Bucketed, vertically-merged blit for DWIN_RenderThumb.
//
// DWIN_Draw_Rectangle re-sends the palette (0x40) before every fill (0x5B),
// so a naive per-pixel draw costs 2 wire frames per pixel. Instead: RLE
// each row, merge a run vertically into the matching run above it when the
// (x0,x1,color) span matches (one 0x5B fill then covers many rows), then
// group all runs by color so the palette is sent once per distinct color
// rather than once per run. See DWIN_OptimizationReference/
// BENCHMARK_RESULTS.md for the measurements this is based on.

struct ThumbRun {
  uint8_t x0, x1, y0, y1; // coordinates local to the thumbnail (0..95)
  uint16_t color;
};

// Sized from real quantized 96x96 thumbnails (worst measured: ~1420 runs).
// An image that overflows this just flushes (renders) early at the next
// row boundary and continues -- never drops pixels, only palette reuse.
static constexpr uint16_t MAX_THUMB_RUNS = 1536;
static ThumbRun thumb_runs[MAX_THUMB_RUNS];
static uint8_t thumb_run_emitted[(MAX_THUMB_RUNS + 7) / 8];

// A row can produce at most ceil(96/2)=48 runs (each run must be separated
// from the next by at least one skipped background pixel).
static constexpr uint8_t MAX_RUNS_PER_ROW = 48;
static uint16_t thumb_open_prev[MAX_RUNS_PER_ROW]; // indices into thumb_runs
static uint16_t thumb_open_cur[MAX_RUNS_PER_ROW];

// Delays every THUMB_BATCH_SIZE frames (SET+FILL counted together) instead
// of every single frame. Empirically bisected on real hardware -- a
// host-side test rig's numbers did NOT transfer to real firmware, so these
// values were found by flashing and watching an actual printer (see
// DWIN_OptimizationReference/dwin_stress.cpp for the tooling). Confirmed
// reliable on C13 (GD32F303) hardware; still needs its own validation pass
// on F401 boards before assuming it holds there too.
//
// An unthrottled flood of commands has separately been observed to overrun
// the panel's input buffer badly enough to need a PHYSICAL POWER CYCLE to
// recover -- never remove this throttle entirely.
#define THUMB_BATCH_SIZE 10
#define THUMB_BATCH_DELAY_MS 16

static void thumb_throttle() {
  // IMPORTANT: always plain delay(), never safe_delay(). safe_delay() calls
  // idle(), which can let other DWIN UI code send its own DWIN_Set_Color
  // mid-blit, corrupting the palette state a still-pending
  // DWIN_Fill_Rect_Raw call is relying on.
  static uint16_t s_batch_frame_count = 0; // not reset per render; harmless
  if (++s_batch_frame_count >= THUMB_BATCH_SIZE) {
    delay(THUMB_BATCH_DELAY_MS);
    s_batch_frame_count = 0;
  }

  // hal.watchdog_refresh() (STM32F1) is only fed from
  // Temperature::updateTemperaturesFromRawValues(), which runs cooperatively
  // from the main loop, not from any ISR. This function blocks well past
  // the 4s watchdog timeout while rendering, so it must feed the watchdog
  // itself (same pattern as Sd2Card.cpp's own long blocking SD init).
  hal.watchdog_refresh();
}

// Emit every accumulated run, grouped by color: one DWIN_Set_Color per
// distinct color, followed by all of that color's DWIN_Fill_Rect_Raw calls.
static void thumb_flush_runs(uint16_t run_count) {
  memset(thumb_run_emitted, 0, (run_count + 7) / 8);
  for (uint16_t i = 0; i < run_count; i++) {
    if (thumb_run_emitted[i >> 3] & (1 << (i & 7))) continue;
    const uint16_t color = thumb_runs[i].color;
    DWIN_Set_Color(color, 0xFFFF);
    thumb_throttle();
    for (uint16_t j = i; j < run_count; j++) {
      if (thumb_run_emitted[j >> 3] & (1 << (j & 7))) continue;
      if (thumb_runs[j].color != color) continue;
      thumb_run_emitted[j >> 3] |= (1 << (j & 7));
      const ThumbRun &r = thumb_runs[j];
      DWIN_Fill_Rect_Raw(THUMB_X_START + r.x0, THUMB_Y_START + r.y0,
                          THUMB_X_START + r.x1, THUMB_Y_START + r.y1);
      thumb_throttle();
    }
  }
}

 bool DWIN_RenderThumb(const char *filename) {
  hal.watchdog_refresh(); // this whole function blocks well past the 4s watchdog window; see thumb_throttle()

  card.openFileRead(filename);
  if (!card.isFileOpen())
    return false;

  uint16_t w = 0, h = 0;
  if (!find_thumb_raw16_header(w, h)) { // header not found, bail out
    card.closefile();
    return false;
  }

  // header found, limit to max size
  if (w > 96) w = 96;
  if (h > 96) h = 96;


  char line[4 * 96 + 8]; // 384 hex + '; ' + '\0'

  uint16_t y = 0;
  uint16_t run_count = 0;     // runs accumulated in thumb_runs so far
  uint8_t open_prev_count = 0, open_cur_count = 0; // vertical-merge state

  while (y < h && gcode_readline(line, sizeof(line))) {
    hal.watchdog_refresh(); // a run of all-background rows emits no frames, so thumb_throttle()'s refresh alone wouldn't cover it

    // Skip lines other than image data
    if (line[0] != ';') continue;

    const char *p = line + 1;
    while (*p == ' ') p++;

    // Have we reached the END?
    if (strncmp(p, "E3V3SE_THUMB_RAW16_END", 23) == 0)
      break;

    const size_t len = strlen(p);
    if (len < w * 4)
      break;

    // RLE this row, merging each run vertically into the matching
    // (x0,x1,color) run left open by the row above where possible.
    open_cur_count = 0;
    uint8_t prev_idx = 0; // two-pointer scan over thumb_open_prev
    uint16_t x = 0;
    while (x < w) {
      const uint16_t color = parse_hex4(p + x * 4);
      if (color == 0) { x++; continue; } // background: not drawn, matches previous behavior

      uint16_t x2 = x;
      while (x2 + 1 < w && parse_hex4(p + (x2 + 1) * 4) == color) x2++;

      // Runs within a row are x-sorted and disjoint, so this is a 1:1 match,
      // not a search: skip previous-row runs that already ended before x.
      while (prev_idx < open_prev_count && thumb_runs[thumb_open_prev[prev_idx]].x1 < x) prev_idx++;

      bool merged = false;
      if (prev_idx < open_prev_count) {
        ThumbRun &pr = thumb_runs[thumb_open_prev[prev_idx]];
        if (pr.x0 == x && pr.x1 == x2 && pr.color == color) {
          pr.y1 = uint8_t(y); // extend the existing run down; x0/x1/color never change
          if (open_cur_count < MAX_RUNS_PER_ROW)
            thumb_open_cur[open_cur_count++] = thumb_open_prev[prev_idx];
          prev_idx++;
          merged = true;
        }
      }
      if (!merged) {
        thumb_runs[run_count] = { uint8_t(x), uint8_t(x2), uint8_t(y), uint8_t(y), color };
        if (open_cur_count < MAX_RUNS_PER_ROW)
          thumb_open_cur[open_cur_count++] = run_count;
        run_count++;
      }
      x = x2 + 1;
    }

    memcpy(thumb_open_prev, thumb_open_cur, open_cur_count * sizeof(uint16_t));
    open_prev_count = open_cur_count;

    y++;

    // Flush at row boundaries only (never mid-row: that would leave a
    // half-built open_cur and buys nothing). A completed row needs at most
    // MAX_RUNS_PER_ROW new slots, so checking here guarantees the next row
    // always fits.
    if (MAX_THUMB_RUNS - run_count < MAX_RUNS_PER_ROW) {
      thumb_flush_runs(run_count);
      run_count = 0;
      open_prev_count = 0; // those runs are now drawn; nothing left to extend
    }
  }

  if (run_count > 0)
    thumb_flush_runs(run_count);

  card.closefile();
  return y > 0;
}

#endif // DWIN_CREALITY_LCD && DWIN_RENDER_THUMBNAIL
