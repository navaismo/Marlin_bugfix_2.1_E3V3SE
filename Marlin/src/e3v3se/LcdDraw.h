#pragma once
#include <stdint.h>

// M9001 v2: bounded print-card drawing, or explicitly negotiated full-screen drawing.
// Both modes stream operations without a framebuffer.
namespace LcdDraw {
  constexpr uint8_t PAYLOAD = 42;
  bool active();
  void command(const char *args);
  void tick();
  void cancel();
  void before_command(char letter, uint16_t code);
}

namespace LcdDrawIO {
  uint32_t now();
  bool allowed(bool fullscreen=false);
  bool begin_fullscreen();
  void end_fullscreen();
  uint8_t send(const uint8_t *frame, uint8_t length);
  int read();
  void reply(const char *state, uint32_t sid, uint16_t seq);
}
