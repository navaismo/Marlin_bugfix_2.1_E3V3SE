/**
 * Marlin 3D Printer Firmware
 * Copyright (c) 2026 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 *
 * Based on Sprinter and grbl.
 * Copyright (c) 2011 Camiel Gubbels / Erik van der Zalm
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 */
#pragma once

#include "../../inc/MarlinConfigPre.h"

#if ENABLED(PINPUT_RESONANCE_EVENTS)
  namespace resonance_host_events {
    bool command();                  // True if M495 has been handled / rejected
    bool cancel();                   // True if an instrumented M496 was handled
    bool stop_requested();           // ISR-safe standard-motion block-boundary cancellation
    bool prepared();                 // Check homing / cancellation before proceeding
    bool reject_command();           // Dispatch guard while the prepared sweep waits
    void homed();                    // Main context, successful native G28 returned
    bool wait_for_arm();             // Enter the nonblocking host-arming barrier
    bool exciting();                 // Main context, after sweep initialization
    bool stopping(const bool done);  // ISR-safe; false while final FT frames drain
    void idle();                     // Deferred events, emergency stop, and arming deadline
  }
#endif
