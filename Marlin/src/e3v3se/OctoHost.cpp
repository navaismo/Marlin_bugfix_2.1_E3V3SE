#include "../inc/MarlinConfig.h"
#include "OctoHost.h"
#if ENABLED(M9001_DRAW_PROTOCOL)
  #include "LcdDraw.h"
#endif

bool serial_connection_active = false;

#if ENABLED(OCTOPRINT_PLUGIN)

#include "../gcode/gcode.h"
#include "../gcode/parser.h"
#include "../lcd/marlinui.h"
#include "../lcd/dwin/creality/dwin.h"
#include "../module/printcounter.h"
#include "../module/planner.h"
#include "../MarlinCore.h"

#include <string.h>

char title[50] = {};

#if ENABLED(DWIN_RENDER_THUMBNAIL)
  uint32_t MarlinUI::print_time = 0;
#endif

// Accepts N"My title", N=My title or N My title; unquoted values stop at ' ', ';' or '*'.
#if ENABLED(M9001_DRAW_PROTOCOL)
namespace HostPrint {
  uint16_t layer_height_um;
  uint32_t total_minutes;
  static uint32_t last[4] = {0xFFFFFFFFUL, 0xFFFFFFFFUL, 0xFFFFFFFFUL, 0xFFFFFFFFUL};
  static millis_t next_field;
  static uint8_t field;

  static void draw_field(const uint8_t i, const bool force) {
    const uint16_t current = ui.get_current_layer(), total = ui.get_total_layer_count();
    const uint32_t value = i == 0 ? uint32_t(total) << 16 | current
                         : i == 1 ? layer_height_um
                         : i == 2 ? total_minutes
                                  : uint32_t(print_job_timer.duration()) / 60;
    if (!force && last[i] == value) return;
    last[i] = value;
    char text[14]; // Longest value: "65535 / 65535" (both uint16_t layer counters).
    if (i == 0) {
      if (total) snprintf(text, sizeof(text), "%u / %u", current, total);
      else strcpy(text, "-- / --");
    }
    else if (i == 1) {
      if (value) snprintf(text, sizeof(text), "%lu.%03lu mm", (unsigned long)(value / 1000), (unsigned long)(value % 1000));
      else strcpy(text, "--");
    }
    else if (i == 2 && !value)
      strcpy(text, "--");
    else
      snprintf(text, sizeof(text), "%02lu:%02lu", (unsigned long)(value / 60), (unsigned long)(value % 60));
    // Four plain rows below the thumbnail/progress, above the native controls.
    const uint8_t y = 127 + 16 * i;
    if (force) {
      const auto label = i == 0 ? F("Layers:") : i == 1 ? F("Layer Height:") : i == 2 ? F("ETA:") : F("Elapsed:");
      DWIN_Draw_String(false, false, font6x12, 0x07FF, Color_Bg_Black, 12, y, label);
    }
    // Reserve 8 pixels per character for the panel font. Even 13-character
    // layer text fits without touching "Layer Height:" or the screen edge.
    constexpr uint8_t value_left = 124, value_right = 233, glyph_width = 8;
    const uint8_t x = value_left + (value_right - value_left + 1 - strlen(text) * glyph_width) / 2;
    DWIN_Draw_Rectangle(1, Color_Bg_Black, 120, y, value_right, y + 15);
    if (i == 0) {
      char *total_text = strchr(text, '/') + 2;
      const uint8_t total_x = x + (total_text - text) * glyph_width;
      total_text[-1] = '\0'; // Keep the separator white, and the total yellow.
      DWIN_Draw_String(false, false, font6x12, Color_White, Color_Bg_Black, x, y, text);
      DWIN_Draw_String(false, false, font6x12, Color_Yellow, Color_Bg_Black, total_x, y, total_text);
    }
    else
      DWIN_Draw_String(false, false, font6x12, i == 2 ? Color_Yellow : Color_White, Color_Bg_Black, x, y, text);
  }
  void progress_caption() {
    // The cube's visible artwork ends at y=105. Keep the caption above Tune.
    DWIN_Draw_String(false, false, font6x12, 0x07FF, Color_Bg_Black, 139, 107, F("Progress"));
  }
  void finish_fields() {
    for (uint8_t i = 0; i < 4; ++i) draw_field(i, true);
  }
  void refresh(const bool force) {
    if (checkkey != ThumbPrint) return;
    if (LcdDraw::active()) return;
    if (force) {
      for (uint8_t i = 0; i < 4; ++i) draw_field(i, true);
      next_field = millis() + 1250;
    }
    else if (ELAPSED(millis(), next_field)) {
      next_field = millis() + 1250;
      draw_field(field, false);
      field = (field + 1) % 4;
    }
  }
}
#endif

static void copy_title(char *dst, const size_t dstlen, const char *src) {
  dst[0] = '\0';
  if (!src) return;

  while (*src == ' ' || *src == '\t') ++src;
  if (*src == 'N' || *src == 'n') {
    ++src;
    if (*src == '=' || *src == ':') ++src;
  }

  const bool quoted = (*src == '"');
  if (quoted) ++src;

  size_t i = 0;
  for (; *src && i < dstlen - 1; ++src) {
    if (quoted) {
      if (*src == '"') break;
      if (*src == '\\' && src[1] == '"') ++src;
    }
    else if (*src == ' ' || *src == '\t' || *src == ';' || *src == '*') break;
    dst[i++] = *src;
  }
  dst[i] = '\0';
}

/**
 * M9000: Plugin connection state and print details
 *  A1        Plugin connected (A0 disconnected)
 *  L<n>      Total layers
 *  T<min>    Elapsed print time in minutes
 *  P<0-100>  Progress
 *  N<title>  Job title
 *  H<um>     Known layer height in micrometers (0 = unavailable)
 *  E<min>    Fixed total estimated duration, shown as HH:MM (0 = unavailable)
 *  D1        Refresh values after the host card finishes
 *  S1        Open the print screen
 */
void GcodeSuite::M9000() {
  if (parser.seen('A')) {
    serial_connection_active = parser.value_bool();
    if (serial_connection_active && !marlin.printJobOngoing()) Goto_MainMenu();
  }

  #if ENABLED(DWIN_RENDER_THUMBNAIL)
    if (parser.seen('L')) ui.set_total_layers(parser.value_int());
  #endif

  #if ENABLED(DWIN_RENDER_THUMBNAIL)
    if (parser.seen('T')) ui.set_print_time(60UL * parser.value_ulong());
  #endif

  #if ENABLED(M9001_DRAW_PROTOCOL)
    if (parser.seenval('H')) HostPrint::layer_height_um = parser.value_ushort();
    if (parser.seenval('E')) HostPrint::total_minutes = parser.value_ulong();
    if (parser.boolval('D')) HostPrint::refresh(true);
  #endif

  if (parser.seen('P'))
    ui.set_progress((PROGRESS_SCALE) > 1 ? parser.value_float() * (PROGRESS_SCALE) : parser.value_byte());

  if (parser.seen('N')) copy_title(title, sizeof(title), parser.string_arg);

  if (parser.boolval('S')) {
    #if ENABLED(M9001_DRAW_PROTOCOL)
      if (marlin.printingIsPaused() || planner.has_blocks_queued() || marlin.wait_for_user
          || (checkkey != MainMenu && checkkey != SelectFile && checkkey != ThumbPrint && checkkey != M117Info)) return;
    #endif
    Clear_Thumb_UpperArea();
    Clear_Title_Bar();
    Goto_ThumbPrint();
    if (title[0]) Draw_OctoTitle(title);
  }
  else if (parser.boolval('F'))
    Goto_ThumbFinish();
}

#if DISABLED(M9001_DRAW_PROTOCOL)
static uint8_t hex2val(const char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return 0;
}

static void skip_spaces(const char *&p) { while (*p == ' ' || *p == '\t') ++p; }

static uint16_t parse_u16(const char *&p) {
  uint16_t v = 0;
  while (*p >= '0' && *p <= '9') v = v * 10 + (*p++ - '0');
  return v;
}

/**
 * M9001: Plugin thumbnail transfer
 *  START                    Reset the line buffer
 *  C <line> <offset> <hex>  RGB565 pixels (4 hex digits each); the line renders once all 96 pixels are in
 *  END                      Finish and acknowledge
 */
void GcodeSuite::M9001() {
  const char *p = parser.command_ptr;
  if (!p) return;

  while (*p && *p != ' ') ++p;
  skip_spaces(p);
  if (!*p) return;

  if (!strncmp(p, "START", 5)) {
    initializeImageMap();
    SERIAL_ECHOLNPGM("M9001 START");
    Clear_Title_Bar();
    Draw_OctoTitle(" Receiving thumbnail, wait...");
  }
  else if (!strncmp(p, "END", 3)) {
    SERIAL_ECHOLNPGM("M9001 END");
    SERIAL_ECHOLNPGM("M9001 thumbnail-rendered");
    Clear_Title_Bar();
    Draw_OctoTitle(title);
  }
  else if (*p == 'C') {
    ++p; skip_spaces(p);
    const uint16_t line_number = parse_u16(p);
    skip_spaces(p);
    uint16_t pixel_offset = parse_u16(p);
    skip_spaces(p);

    const uint16_t start_offset = pixel_offset;
    uint16_t decoded = 0;
    while (pixel_offset < OctoIMAGE_WIDTH && p[0] && p[1] && p[2] && p[3]) {
      OctoImageLine[pixel_offset++] = (uint16_t(hex2val(p[0])) << 12) | (uint16_t(hex2val(p[1])) << 8)
                                    | (uint16_t(hex2val(p[2])) << 4)  |  uint16_t(hex2val(p[3]));
      ++decoded;
      p += 4;
    }

    if (start_offset + decoded >= OctoIMAGE_WIDTH) DWIN_RenderOctoLine(line_number);
  }
}

#else
void GcodeSuite::M9001() {
  const char *p = parser.command_ptr;
  while (*p && *p != ' ') ++p;
  LcdDraw::command(p);
}
#endif // M9001_DRAW_PROTOCOL

#endif // OCTOPRINT_PLUGIN
