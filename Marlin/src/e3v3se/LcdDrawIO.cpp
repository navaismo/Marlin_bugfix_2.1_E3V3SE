// GPLv3. TJC transport adapter; the original native LCD driver stays intact.
#include "../inc/MarlinConfig.h"
#if ENABLED(M9001_DRAW_PROTOCOL)
#include "LcdDraw.h"
#include "../MarlinCore.h"
#include "../module/planner.h"
#include "../lcd/dwin/creality/dwin.h"
#include "../core/serial.h"

namespace LcdDrawIO {
  uint32_t now() { return millis(); }
  bool allowed() {
    // Thermal autostart alone is not host printing. Movement commands preempt drawing.
    return checkkey == ThumbPrint && !marlin.printingIsPaused() && !marlin.wait_for_user && !planner.has_blocks_queued();
  }
  uint8_t send(const uint8_t *frame, const uint8_t length) {
    const int free = LCD_SERIAL.availableForWrite();
    if (free < length) return 0;
    const uint8_t queued = SERIAL_TX_BUFFER_SIZE - free + length; // includes shift-register margin
    for (uint8_t i = 0; i < length; ++i) LCD_SERIAL.write(frame[i]);
    return queued;
  }
  int read() { return LCD_SERIAL.available() ? LCD_SERIAL.read() : -1; }
  void reply(const char *status, const uint32_t sid, const uint16_t seq) {
    char line[60];
    snprintf(line, sizeof(line), "M9001 %s %08lX %04X", status, (unsigned long)sid, seq);
    SERIAL_ECHOLN(line);
  }
}
#endif
