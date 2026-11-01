/**
 * Marlin 3D Printer Firmware
 * Copyright (c) 2026 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Projection, assessment and help link ported from navaismo/Ender-3V3-SE,
 * v1.0.9.8_1f. Filled surface and paced, incremental LCD renderer.
 */
#include "../../../inc/MarlinConfig.h"

#if ENABLED(BED_LEVEL_VISUALIZER)

#include "bed_level_visualizer.h"
#include "bed_level_surface.h"
#include "bed_level_assessment.h"
#include "bed_level_help_qr.h"
#include "dwin.h"
#include "dwin_lcd.h"
#include "../../../feature/bedlevel/bedlevel.h"
#include <stdio.h>
#include <string.h>

namespace BedLevelVisualizer {
  using namespace BedLevelSurface;

  constexpr Bounds plot = { 20, 128, DWIN_WIDTH - 21, DWIN_HEIGHT - 74 };
  constexpr uint16_t GRID_COLOR = 0x3186, AXIS_COLOR = 0x7BEF;
  constexpr uint16_t QR_X = DWIN_WIDTH - BedLevelHelpQR::EXTENT - 12, QR_Y = 30;
  enum class Stage : uint8_t {
    Idle, Header, QrBackground, QrData, QrCaption, Legend, LegendLow, LegendZero,
    LegendHigh, Status, Axes, Surface, AxisLabels, FinishClear, Finish
  };
  static Stage stage = Stage::Idle;
  static millis_t next_draw_ms;
  static uint8_t header_part, qr_x, qr_y, legend_part, axis_part;
  static bool initialized, has_mesh, cell_missing;
  static BedLevelAssessment::Stats stats;
  static float mesh[GRID_MAX_POINTS_X][GRID_MAX_POINTS_Y];
  static float center_z, z_scale, color_range;
  static Point corner[4];
  static Triangle triangle;
  static int16_t diagonal, cell_x, cell_y;
  static uint8_t part;

  static void label(const uint16_t x, const uint16_t y, const __FlashStringHelper *text) {
    DWIN_Draw_String(false, false, font6x12, Color_White, Color_Bg_Black, x, y, text);
  }

  // A reference plane just below every possible mesh height. Use the same
  // projection as the surface, with X/Y extended into the side margins.
  static Point axis_origin() {
    Point origin = project(0, 0, 0, 0, 0, plot);
    origin.y = plot.bottom - 1;
    return origin;
  }

  static Point axis_end(const uint8_t axis) {
    const Point origin = axis_origin();
    if (axis == 2) return { origin.x, float(plot.top + 2), 0 };
    const float extent = 1 + 14.0f / (plot.right - plot.left);
    Point end = project(axis == 0 ? extent : 0, axis == 1 ? extent : 0, 0, 0, 0, plot);
    end.y += origin.y - project(0, 0, 0, 0, 0, plot).y;
    return end;
  }

  // The target's nano printf omits floating-point conversions. Format fixed
  // decimals with integers so values also appear in the actual firmware.
  static void format_mm(char *text, const size_t capacity, const float value,
                        const uint8_t decimals = 3, const bool signed_value = false) {
    if (!isfinite(value) || fabsf(value) > 99999) {
      snprintf(text, capacity, "out of range");
      return;
    }
    const uint32_t scale = decimals == 2 ? 100 : 1000,
                   scaled = uint32_t(fabsf(value) * scale + 0.5f);
    snprintf(text, capacity, "%s%lu.%0*lu",
             scaled && value < 0 ? "-" : signed_value ? "+" : "",
             (unsigned long)(scaled / scale), int(decimals), (unsigned long)(scaled % scale));
  }

  static const __FlashStringHelper *score_text() {
    using BedLevelAssessment::Score;
    switch (stats.score()) {
      case Score::Perfect: return F("Score: PERFECT");
      case Score::Good: return F("Score: GOOD");
      case Score::Ok: return F("Score: OK");
      case Score::Bad: return F("Score: BAD");
      case Score::Horrible: return F("Score: HORRIBLE");
      default: return F("Score: INCOMPLETE");
    }
  }

  static uint16_t score_color() {
    using BedLevelAssessment::Score;
    switch (stats.score()) {
      case Score::Perfect: return 0x07E0;
      case Score::Good: return 0x07FF;
      case Score::Ok: return 0xFFE0;
      case Score::Bad:
      case Score::Horrible: return 0xF800;
      default: return MISSING_COLOR;
    }
  }

  static void begin_triangle() {
    triangle.begin(corner[0], corner[part == 0 ? 1 : 2], corner[part == 0 ? 2 : 3],
                   plot, color_range, cell_missing);
  }

  static void begin_cell() {
    // Painter's order: far (+X,+Y) cells first, front (0,0) cells last.
    cell_y = diagonal - cell_x;
    const uint8_t dx[4] = { 0, 1, 1, 0 }, dy[4] = { 0, 0, 1, 1 };
    cell_missing = false;
    for (uint8_t n = 0; n < 4; ++n) {
      const uint8_t x = cell_x + dx[n], y = cell_y + dy[n];
      float z = mesh[x][y];
      if (!isfinite(z)) { z = center_z; cell_missing = true; }
      corner[n] = project(float(x) / (GRID_MAX_POINTS_X - 1), float(y) / (GRID_MAX_POINTS_Y - 1),
                          z, center_z, z_scale, plot);
    }
    part = 0;
    begin_triangle();
  }

  static bool next_cell() {
    if (++cell_x > _MIN(diagonal, GRID_MAX_POINTS_X - 2)) {
      if (--diagonal < 0) return false;
      cell_x = _MAX(0, diagonal - (GRID_MAX_POINTS_Y - 2));
    }
    begin_cell();
    return true;
  }

  void cancel() { stage = Stage::Idle; }
  bool busy() { return stage != Stage::Idle; }

  void start() {
    cancel();
    stats = {};
    initialized = bedlevel.mesh_is_valid();
    if (initialized)
      for (uint8_t x = 0; x < GRID_MAX_POINTS_X; ++x)
        for (uint8_t y = 0; y < GRID_MAX_POINTS_Y; ++y)
          stats.add(mesh[x][y] = bedlevel.z_values[x][y]);
    has_mesh = stats.count > 0;
    if (has_mesh) {
      center_z = (stats.minimum + stats.maximum) * 0.5f;
      z_scale = (plot.bottom - plot.top) * 0.25f / _MAX(stats.range(), 0.1f);
      color_range = _MAX(_MAX(fabsf(stats.minimum), fabsf(stats.maximum)), 0.05f);
      diagonal = GRID_MAX_POINTS_X + GRID_MAX_POINTS_Y - 4;
      cell_x = GRID_MAX_POINTS_X - 2;
      begin_cell();
    }
    header_part = qr_x = qr_y = legend_part = axis_part = 0;
    stage = Stage::Header;
    next_draw_ms = millis();
  }

  // Each stage emits at most one drawing primitive, including the initial
  // screen, legend and QR. Small batches alone do not protect the panel: it
  // needs real elapsed time between rectangles, not just returns to the loop.
  static bool draw_next() {
    char text[(QR_X - 18) / 6 + 1]; // Header values must stay clear of the QR quiet zone.
    char value[13]; // Longest result is "out of range" (12 characters).
    while (busy()) {
      switch (stage) {
        case Stage::Header:
          switch (header_part++) {
            case 0: DWIN_Draw_Rectangle(1, Color_Bg_Black, 0, 0, DWIN_WIDTH - 1, DWIN_HEIGHT - 1); return true;
            case 1: DWIN_Draw_Rectangle(1, Color_Bg_Blue, 0, 0, DWIN_WIDTH - 1, 23); return true;
            case 2:
              DWIN_Draw_String(false, false, font8x16, Color_Yellow, Color_Bg_Blue,
                               (DWIN_WIDTH - (sizeof("Bed Level Map") - 1) * 8) / 2, 4, F("Bed Level Map"));
              return true;
            case 3: label(12, DWIN_HEIGHT - 14, F("Click: Back | Z auto-scaled")); return true;
            case 4:
              if (!has_mesh) {
                label(12, 44, initialized ? F("No measured points.") : F("No bed mesh available."));
                return true;
              }
              format_mm(value, sizeof(value), stats.minimum, 3, true);
              snprintf(text, sizeof(text), "Min:%s mm", value);
              DWIN_Draw_String(false, false, font6x12, Color_White, Color_Bg_Black, 12, 30, text);
              return true;
            case 5:
              if (!has_mesh) { label(12, 64, F("Run bed leveling.")); return true; }
              format_mm(value, sizeof(value), stats.maximum, 3, true);
              snprintf(text, sizeof(text), "Max:%s mm", value);
              DWIN_Draw_String(false, false, font6x12, Color_White, Color_Bg_Black, 12, 48, text);
              return true;
            case 6:
              if (!has_mesh) continue;
              format_mm(value, sizeof(value), stats.range());
              snprintf(text, sizeof(text), "Range:%s mm", value);
              DWIN_Draw_String(false, false, font6x12, Color_White, Color_Bg_Black, 12, 66, text);
              return true;
            case 7:
              if (!has_mesh) continue;
              format_mm(value, sizeof(value), stats.stddev());
              snprintf(text, sizeof(text), "StdDev:%s mm", value);
              DWIN_Draw_String(false, false, font6x12, Color_White, Color_Bg_Black, 12, 84, text);
              return true;
            case 8:
              DWIN_Draw_String(false, false, font8x16, score_color(), Color_Bg_Black, 12, 104, score_text());
              return true;
            default: stage = Stage::QrBackground; continue;
          }
        case Stage::QrBackground:
          DWIN_Draw_Rectangle(1, Color_White, QR_X, QR_Y,
                               QR_X + BedLevelHelpQR::EXTENT - 1, QR_Y + BedLevelHelpQR::EXTENT - 1);
          stage = Stage::QrData;
          return true;
        case Stage::QrData:
          while (qr_y < BedLevelHelpQR::SIZE) {
            while (qr_x < BedLevelHelpQR::SIZE && !BedLevelHelpQR::dark(qr_x, qr_y)) ++qr_x;
            if (qr_x == BedLevelHelpQR::SIZE) { qr_x = 0; ++qr_y; continue; }
            const uint8_t left = qr_x;
            while (qr_x < BedLevelHelpQR::SIZE && BedLevelHelpQR::dark(qr_x, qr_y)) ++qr_x;
            DWIN_Draw_Rectangle(1, Color_Bg_Black,
              QR_X + (left + BedLevelHelpQR::QUIET) * BedLevelHelpQR::SCALE,
              QR_Y + (qr_y + BedLevelHelpQR::QUIET) * BedLevelHelpQR::SCALE,
              QR_X + (qr_x + BedLevelHelpQR::QUIET) * BedLevelHelpQR::SCALE - 1,
              QR_Y + (qr_y + BedLevelHelpQR::QUIET + 1) * BedLevelHelpQR::SCALE - 1);
            return true;
          }
          stage = Stage::QrCaption;
          continue;
        case Stage::QrCaption:
          label(QR_X + 12, QR_Y + BedLevelHelpQR::EXTENT + 4, F("Help QR"));
          stage = has_mesh ? Stage::Legend : Stage::Idle;
          return true;
        case Stage::Legend: {
          const uint8_t n = legend_part++;
          const int16_t left = 20 + n * (DWIN_WIDTH - 40) / 33,
                        right = 20 + (n + 1) * (DWIN_WIDTH - 40) / 33 - 1;
          DWIN_Draw_Rectangle(1, color((int(n) - 16) * color_range / 16, color_range),
                               left, DWIN_HEIGHT - 64, right, DWIN_HEIGHT - 57);
          if (legend_part == 33) stage = Stage::LegendLow;
          return true;
        }
        case Stage::LegendLow:
          format_mm(text, sizeof(text), -color_range, 2, true);
          DWIN_Draw_String(false, false, font6x12, Color_White, Color_Bg_Black, 20, DWIN_HEIGHT - 52, text);
          stage = Stage::LegendZero;
          return true;
        case Stage::LegendZero:
          label(DWIN_WIDTH / 2 - 3, DWIN_HEIGHT - 52, F("0"));
          stage = Stage::LegendHigh;
          return true;
        case Stage::LegendHigh:
          format_mm(value, sizeof(value), color_range, 2, true);
          snprintf(text, sizeof(text), "%s mm", value);
          DWIN_Draw_String(false, false, font6x12, Color_White, Color_Bg_Black,
                           _MAX(20, DWIN_WIDTH - 20 - int(strlen(text)) * 6), DWIN_HEIGHT - 52, text);
          stage = Stage::Status;
          return true;
        case Stage::Status:
          label(12, DWIN_HEIGHT - 30, F("Rendering..."));
          stage = Stage::Axes;
          return true;
        case Stage::Axes: {
          // Draw first so the filled heatmap occludes the axes naturally.
          const Point origin = axis_origin(), end = axis_end(axis_part);
          DWIN_Draw_Line(AXIS_COLOR, int16_t(lroundf(origin.x)), int16_t(lroundf(origin.y)),
                                     int16_t(lroundf(end.x)), int16_t(lroundf(end.y)));
          if (++axis_part == 3) { axis_part = 0; stage = Stage::Surface; }
          return true;
        }
        case Stage::Surface: {
          Span span;
          if (part < 2 && triangle.next(span)) {
            // Overlap scan bands by one pixel. Panels that treat the far
            // rectangle corner as exclusive otherwise leave visible stripes.
            DWIN_Draw_Rectangle(1, span.color, span.left, span.y,
                                 _MIN(span.right + 1, plot.right), _MIN(span.y + PIXEL_SIZE, plot.bottom));
            return true;
          }
          if (part < 2) {
            if (++part == 1) begin_triangle();
            continue;
          }
          const Point &a = corner[part - 2], &b = corner[(part - 1) % 4];
          DWIN_Draw_Line(GRID_COLOR, int16_t(lroundf(a.x)), int16_t(lroundf(a.y)),
                                   int16_t(lroundf(b.x)), int16_t(lroundf(b.y)));
          if (++part == 6 && !next_cell()) stage = Stage::AxisLabels;
          return true;
        }
        case Stage::AxisLabels: {
          const Point end = axis_end(axis_part);
          // The labels sit beyond the mesh envelope, clear of the statistics,
          // QR and legend. Never draw text over the colored surface.
          const int16_t x = int16_t(lroundf(end.x)) + (axis_part == 0 ? 4 : axis_part == 1 ? -10 : 5),
                        y = int16_t(lroundf(end.y)) - (axis_part == 2 ? 10 : 6);
          label(x, y, axis_part == 0 ? F("X") : axis_part == 1 ? F("Y") : F("Z"));
          if (++axis_part == 3) stage = Stage::FinishClear;
          return true;
        }
        case Stage::FinishClear:
          DWIN_Draw_Rectangle(1, Color_Bg_Black, 0, DWIN_HEIGHT - 30, DWIN_WIDTH - 1, DWIN_HEIGHT - 18);
          stage = Stage::Finish;
          return true;
        case Stage::Finish: label(12, DWIN_HEIGHT - 30, F("Blue:low  Green:0  Red:high")); cancel(); return true;
        default: return false;
      }
    }
    return false;
  }

  void update() {
    if (!busy() || PENDING(millis(), next_draw_ms)) return;
    if (draw_next()) {
      DWIN_UpdateLCD();
      // Timestamp after sending, so a delayed loop never catches up in a burst.
      // Returning instead of sleeping keeps temperature control and Back active.
      next_draw_ms = millis() + BED_LEVEL_VISUALIZER_DRAW_DELAY_MS;
    }
  }
}

#endif // BED_LEVEL_VISUALIZER
