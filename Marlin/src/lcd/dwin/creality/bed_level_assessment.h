/**
 * Marlin 3D Printer Firmware
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Assessment thresholds ported from Ender-3V3-SE v1.0.9.8_1f.
 */
#pragma once

#include <math.h>
#include <stdint.h>

namespace BedLevelAssessment {
  enum class Score : uint8_t { Perfect, Good, Ok, Bad, Horrible, Incomplete };

  inline Score classify(const float delta, const float stddev) {
    if (!isfinite(delta) || !isfinite(stddev)) return Score::Incomplete;
    if (stddev <= 0.1f && delta <= 0.3f) return Score::Perfect;
    if (stddev <= 0.2f && delta <= 0.5f) return Score::Good;
    if (stddev <= 0.3f && delta <= 1.0f) return Score::Ok;
    if (stddev <= 1.0f && delta <= 2.0f) return Score::Bad;
    return Score::Horrible;
  }

  struct Stats {
    float minimum = INFINITY, maximum = -INFINITY, mean = 0, m2 = 0;
    uint16_t count = 0, missing = 0;

    void add(const float z) {
      if (!isfinite(z)) { ++missing; return; }
      if (z < minimum) minimum = z;
      if (z > maximum) maximum = z;
      // Population standard deviation, as in the original assessment, without
      // its extra flattened mesh buffer or assumptions about square grids.
      const float delta = z - mean;
      mean += delta / ++count;
      m2 += delta * (z - mean);
    }

    float range() const { return count ? maximum - minimum : 0; }
    float stddev() const { return count ? sqrtf(fmaxf(m2 / count, 0)) : 0; }
    Score score() const { return count && !missing ? classify(range(), stddev()) : Score::Incomplete; }
  };
}
