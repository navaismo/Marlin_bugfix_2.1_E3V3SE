/**
 * Marlin 3D Printer Firmware
 * Copyright (c) 2026 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#pragma once

// Geometry and span generation are independent of the LCD and printer hardware.
#include <stdint.h>
#include <math.h>

namespace BedLevelSurface {

  struct Point { float x, y, z; };
  struct Bounds { int16_t left, top, right, bottom; };
  struct Span { int16_t left, right, y; uint16_t color; };

  constexpr uint8_t PIXEL_SIZE = 1;
  constexpr uint16_t MISSING_COLOR = 0x7BEF;

  inline uint16_t color(const float z, const float range) {
    // Symmetric around zero: blue -> cyan -> green -> yellow -> red.
    // Quantization makes adjacent samples share a single LCD rectangle.
    int index = int(lroundf((z / range + 1) * 16));
    if (index < 0) index = 0;
    if (index > 32) index = 32;
    const uint8_t ramp = (index % 8) * 255 / 8;
    uint8_t r = 0, g = 0, b = 0;
    if (index < 8) { g = ramp; b = 255; }
    else if (index < 16) { g = 255; b = 255 - ramp; }
    else if (index < 24) { r = ramp; g = 255; }
    else { r = 255; g = index == 32 ? 0 : 255 - ramp; }
    return uint16_t((r & 0xF8) << 8) | uint16_t((g & 0xFC) << 3) | (b >> 3);
  }

  inline Point project(const float u, const float v, const float z, const float center_z,
                       const float z_scale, const Bounds &bounds) {
    const float center_x = (bounds.left + bounds.right) * 0.5f,
                center_y = (bounds.top + bounds.bottom) * 0.5f,
                half_width = (bounds.right - bounds.left) * 0.5f,
                // Leave room for height exaggeration without flattening a
                // tilted bed into a nearly horizontal strip.
                half_depth = (bounds.bottom - bounds.top) / 3.0f;
    return { center_x + (u - v) * half_width,
             center_y + (1 - u - v) * half_depth - (z - center_z) * z_scale, z };
  }

  class Triangle {
    Point a{}, b{}, c{};
    float inverse_area = 0, range = 1;
    int16_t left = 0, right = -1, top = 0, bottom = -1, x = 0, y = 0;
    bool missing = false;

    bool sample(const int16_t px, const int16_t py, uint16_t &result) const {
      const float sx = px + PIXEL_SIZE * 0.5f, sy = py + PIXEL_SIZE * 0.5f,
                  wa = ((b.y - c.y) * (sx - c.x) + (c.x - b.x) * (sy - c.y)) * inverse_area,
                  wb = ((c.y - a.y) * (sx - c.x) + (a.x - c.x) * (sy - c.y)) * inverse_area,
                  wc = 1 - wa - wb;
      if (wa < -0.00001f || wb < -0.00001f || wc < -0.00001f) return false;
      result = missing ? MISSING_COLOR : color(wa * a.z + wb * b.z + wc * c.z, range);
      return true;
    }

  public:
    void begin(const Point &p0, const Point &p1, const Point &p2, const Bounds &bounds,
               const float color_range, const bool unknown = false) {
      a = p0; b = p1; c = p2; range = color_range; missing = unknown;
      const float area = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y);
      left = bounds.left; right = bounds.right - PIXEL_SIZE + 1;
      top = bounds.top; bottom = bounds.bottom - PIXEL_SIZE + 1;
      if (fabsf(area) < 0.001f) { right = -1; return; }
      inverse_area = 1 / area;
      const int16_t min_x = int16_t(floorf(fminf(a.x, fminf(b.x, c.x)) / PIXEL_SIZE)) * PIXEL_SIZE,
                    max_x = int16_t(ceilf(fmaxf(a.x, fmaxf(b.x, c.x)) / PIXEL_SIZE)) * PIXEL_SIZE,
                    min_y = int16_t(floorf(fminf(a.y, fminf(b.y, c.y)) / PIXEL_SIZE)) * PIXEL_SIZE,
                    max_y = int16_t(ceilf(fmaxf(a.y, fmaxf(b.y, c.y)) / PIXEL_SIZE)) * PIXEL_SIZE;
      if (min_x > left) left = min_x;
      if (max_x < right) right = max_x;
      if (min_y > top) top = min_y;
      if (max_y < bottom) bottom = max_y;
      x = left; y = top;
    }

    // Emit just one horizontal run. The caller controls the work per UI update.
    bool next(Span &span) {
      while (y <= bottom && left <= right) {
        uint16_t value;
        while (x <= right && !sample(x, y, value)) x += PIXEL_SIZE;
        if (x > right) { x = left; y += PIXEL_SIZE; continue; }
        const int16_t start = x;
        const uint16_t run_color = value;
        x += PIXEL_SIZE;
        while (x <= right && sample(x, y, value) && value == run_color) x += PIXEL_SIZE;
        span = { start, int16_t(x - 1), y, run_color };
        return true;
      }
      return false;
    }
  };
}
