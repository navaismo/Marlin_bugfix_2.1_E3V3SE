/**
 * Marlin 3D Printer Firmware
 * Copyright (c) 2026 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#pragma once

namespace BedLevelVisualizer {
  void start();
  void update();
  void cancel();
  bool busy();
}
