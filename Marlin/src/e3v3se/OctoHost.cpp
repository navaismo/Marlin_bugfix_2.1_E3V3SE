#include "../inc/MarlinConfig.h"
#include "OctoHost.h"

bool serial_connection_active = false;

#if ENABLED(OCTOPRINT_PLUGIN)

#include "../gcode/gcode.h"
#include "../gcode/parser.h"
#include "../lcd/marlinui.h"
#include "../lcd/dwin/creality/dwin.h"

#include <string.h>

char title[50] = {};

#if ENABLED(DWIN_RENDER_THUMBNAIL)
  uint32_t MarlinUI::print_time = 0;
#endif

// Accepts N"My title", N=My title or N My title; unquoted values stop at ' ', ';' or '*'.
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
 *  S1        Open the print screen
 */
void GcodeSuite::M9000() {
  if (parser.seen('A')) {
    serial_connection_active = parser.value_bool();
    if (serial_connection_active) Goto_MainMenu();
  }

  #if ENABLED(DWIN_RENDER_THUMBNAIL)
    if (parser.seen('L')) ui.set_total_layers(parser.value_int());
  #endif

  #if ENABLED(DWIN_RENDER_THUMBNAIL)
    if (parser.seen('T')) ui.set_print_time(60UL * parser.value_ulong());
  #endif

  if (parser.seen('P'))
    ui.set_progress((PROGRESS_SCALE) > 1 ? parser.value_float() * (PROGRESS_SCALE) : parser.value_byte());

  if (parser.seen('N')) copy_title(title, sizeof(title), parser.string_arg);

  if (parser.boolval('S')) {
    Clear_Thumb_UpperArea();
    Clear_Title_Bar();
    Goto_ThumbPrint();
    if (title[0]) Draw_OctoTitle(title);
  }
  else if (parser.boolval('F'))
    Goto_ThumbFinish();
}

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

#endif // OCTOPRINT_PLUGIN
