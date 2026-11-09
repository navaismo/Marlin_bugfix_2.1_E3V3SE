// GPLv3. Bounded host print-card executor, independent of native navigation.
#ifdef LCD_DRAW_NATIVE_TEST
  #define ENABLED(V) 0
#else
  #include "../inc/MarlinConfig.h"
#endif
#if defined(LCD_DRAW_NATIVE_TEST) || ENABLED(M9001_DRAW_PROTOCOL)
#include "LcdDraw.h"
#include <string.h>

namespace LcdDraw {
  enum Phase : uint8_t { IDLE, WAIT, DRAW, FENCE, SETTLE, DONE };
  static struct {
    uint32_t sid, last_crc, stream_crc, deadline, session_end, wire_until;
    uint16_t seq;
    uint8_t data[PAYLOAD], length, pos, phase, frames, fence, fence_len, strip, filling;
  } state;
  static_assert(sizeof(state) <= 88, "Drawing state exceeds the C13 RAM budget.");

  static bool due(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }
  static uint32_t crc(uint32_t c, const uint8_t *p, uint8_t n) {
    while (n--) {
      c ^= *p++;
      for (uint8_t i = 0; i < 8; ++i) c = (c >> 1) ^ (0xEDB88320UL & -(c & 1));
    }
    return c;
  }
  static uint32_t word32(const uint8_t *p) {
    return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3];
  }
  static uint16_t word16(const uint8_t *p) { return uint16_t(p[0]) << 8 | p[1]; }
  static int8_t digit(char c) {
    if (c == '_') return 6; // G-free Base64 avoids MeatPack's in-payload G-code heuristic.
    if (c == 'G') return -1;
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    return c == '+' ? 62 : c == '/' ? 63 : -1;
  }
  // Strict, canonical Base64. Decode to stack scratch before touching live state.
  static uint8_t decode(const char *s, uint8_t *out) {
    const size_t len = strlen(s);
    if (!len || len > 72 || len % 4) return 0;
    uint8_t n = 0;
    for (uint8_t i = 0; i < len; i += 4) {
      const int8_t a = digit(s[i]), b = digit(s[i+1]),
                   c = s[i+2] == '=' ? 0 : digit(s[i+2]),
                   d = s[i+3] == '=' ? 0 : digit(s[i+3]);
      if (a < 0 || b < 0 || c < 0 || d < 0) return 0;
      const bool pad2 = s[i+2] == '=', pad1 = s[i+3] == '=';
      if ((pad2 && !pad1) || ((pad1 || pad2) && i + 4 != len)
          || (pad2 && (b & 15)) || (pad1 && !pad2 && (c & 3))) return 0;
      out[n++] = uint8_t(a << 2 | b >> 4);
      if (!pad2) out[n++] = uint8_t(b << 4 | c >> 2);
      if (!pad1) out[n++] = uint8_t(c << 6 | d);
    }
    return n;
  }
  bool active() { return state.phase >= WAIT && state.phase <= SETTLE; }
  static void reply(const char *s) { LcdDrawIO::reply(s, state.sid, state.seq); }
  void cancel() {
    if (active()) { state.phase = IDLE; reply("ABORTED"); }
  }
  void before_command(char letter, uint16_t code) {
    if (letter == 'M' && (code == 9001 || code == 105 || code == 114 || code == 115)) return;
    cancel();
  }
  static uint8_t op_size(const uint8_t *p, uint8_t remain) {
    if (*p == 0) return remain >= 3 ? 3 : 0; // COLOR RGB565
    if (*p == 2) { // STRIP x,y,count,RGB565... (high-entropy fallback)
      if (remain < 6 || !p[3] || p[3] > 19 || remain < 4 + 2 * p[3]) return 0;
      return p[1] + p[3] <= 240 && p[2] >= 25 && p[2] <= 122 ? 4 + 2 * p[3] : 0;
    }
    if (*p != 1 || remain < 5) return 0;     // RECT x0,y0,x1,y1
    return p[1] <= p[3] && p[3] < 240 && p[2] >= 25
        && p[2] <= p[4] && p[4] <= 122 ? 5 : 0;
  }
  void command(const char *args) {
    while (*args == ' ') ++args;
    if (!strcmp(args, "Q")) { LcdDrawIO::reply("CAPS 2 42 240 320", 0, 0); return; }
    if (!*args) { reply("FORMAT"); return; }
    const char kind = *args++;
    uint8_t packet[54];
    const uint8_t n = decode(args, packet);
    if (n < 9 || packet[0] != 2) { reply("FORMAT"); return; }
    uint32_t sum = crc(0xFFFFFFFFUL, reinterpret_cast<const uint8_t *>(&kind), 1);
    sum = crc(sum, packet, n - 4) ^ 0xFFFFFFFFUL;
    if (sum != word32(packet + n - 4)) { reply("CRC"); return; }
    const uint32_t sid = word32(packet + 1);
    if (!sid) { reply("FORMAT"); return; }
    const uint32_t now = LcdDrawIO::now();
    if (kind == 'B' && n == 9) {
      if (sid == state.sid && state.phase == IDLE) { reply("ABORTED"); return; }
      if (sid == state.sid && (active() || state.phase == DONE)) {
        reply(state.phase == DONE ? "DONE" : state.phase == WAIT ? "ACK" : "BUSY");
        return;
      }
      if (active() || !LcdDrawIO::allowed()) { LcdDrawIO::reply("BUSY", sid, 0); return; }
      state.sid = sid; state.seq = 0; state.stream_crc = 0xFFFFFFFFUL;
      state.last_crc = 0; state.length = state.pos = 0;
      state.phase = WAIT;
      state.deadline = now + 5000; state.session_end = now + 120000;
      reply("ACK"); return;
    }
    if (sid != state.sid) { reply("SESSION"); return; }
    if (kind == 'A' && n == 9) { cancel(); return; }
    if (kind == 'E' && n == 15) {
      if (word16(packet + 5) != state.seq
          || word32(packet + 7) != (state.stream_crc ^ 0xFFFFFFFFUL)) { reply("ORDER"); return; }
      if (state.phase == DONE) { reply("DONE"); return; }
      if (state.phase == FENCE || state.phase == SETTLE) return;
      if (state.phase != WAIT) { reply("BUSY"); return; }
      state.phase = FENCE; state.fence = state.fence_len = 0; state.deadline = now + 1000;
      return;
    }
    if (kind != 'D' || n <= 11 || n > 11 + PAYLOAD) { reply("FORMAT"); return; }
    const uint16_t seq = word16(packet + 5);
    if (state.seq && seq == state.seq - 1 && sum == state.last_crc) { reply("ACK"); return; }
    if (state.phase != WAIT) { reply("BUSY"); return; }
    if (seq != state.seq || seq == 0xFFFF) { reply("ORDER"); return; }
    const uint8_t len = n - 11;
    if (!seq && packet[7] != 0) { reply("FORMAT"); return; }
    for (uint8_t pos = 0; pos < len;) {
      const uint8_t step = op_size(packet + 7 + pos, len - pos);
      if (!step) { reply("BOUNDS"); return; }
      pos += step;
    }
    memcpy(state.data, packet + 7, len);
    state.length = len; state.pos = state.strip = state.filling = 0; state.last_crc = sum;
    state.stream_crc = crc(state.stream_crc, state.data, len);
    state.phase = DRAW; state.deadline = now + 5000;
  }
  // A frame is queued only when the UART has space. The conservative wire-time
  // deadline also covers pre-existing native bytes, including the final stop bit.
  static bool frame(const uint8_t *p, uint8_t len, uint32_t now) {
    if (!due(now, state.wire_until)) return false;
    const uint8_t queued = LcdDrawIO::send(p, len);
    if (!queued) return false;
    state.wire_until = now + (uint32_t(queued) * 10000 + 115199) / 115200;
    if (++state.frames == 10) { state.frames = 0; state.wire_until += 16; }
    return true;
  }
  void tick() {
    if (!active()) return;
    const uint32_t now = LcdDrawIO::now();
    if (!LcdDrawIO::allowed() || (state.phase != SETTLE && due(now, state.deadline)) || due(now, state.session_end)) { cancel(); return; }
    if (state.phase == DRAW) {
      const uint8_t *p = state.data + state.pos;
      if (*p == 0) {
        const uint8_t f[] = {0xAA, 0x40, p[1], p[2], 0xFF, 0xFF, 0xCC, 0x33, 0xC3, 0x3C};
        if (!frame(f, sizeof(f), now)) return;
        state.pos += 3;
      }
      else if (*p == 2) {
        if (!state.filling) {
          const uint8_t *rgb = p + 4 + 2 * state.strip;
          const uint8_t f[] = {0xAA, 0x40, rgb[0], rgb[1], 0xFF, 0xFF, 0xCC, 0x33, 0xC3, 0x3C};
          if (!frame(f, sizeof(f), now)) return;
          state.filling = 1;
        }
        else {
          const uint8_t x = p[1] + state.strip;
          const uint8_t f[] = {0xAA, 0x5B, 0, x, 0, p[2], 0, x, 0, p[2], 0xCC, 0x33, 0xC3, 0x3C};
          if (!frame(f, sizeof(f), now)) return;
          state.filling = 0;
          if (++state.strip == p[3]) { state.strip = 0; state.pos += 4 + 2 * p[3]; }
        }
      }
      else {
        const uint8_t f[] = {0xAA, 0x5B, 0, p[1], 0, p[2], 0, p[3], 0, p[4], 0xCC, 0x33, 0xC3, 0x3C};
        if (!frame(f, sizeof(f), now)) return;
        state.pos += 5;
      }
      if (state.pos == state.length) { ++state.seq; state.phase = WAIT; state.deadline = now + 5000; reply("ACK"); }
    }
    else if (state.phase == FENCE) {
      if (!state.fence) {
        if (!due(now, state.wire_until)) return;
        bool drained = false;
        for (uint8_t i = 0; i < 32; ++i) {
          if (LcdDrawIO::read() < 0) { drained = true; break; }
        }
        if (!drained) return; // Bounded draining over multiple ticks; never accept a stale fence.
        const uint8_t f[] = {0xAA, 0x00, 0xCC, 0x33, 0xC3, 0x3C};
        if (!frame(f, sizeof(f), now)) return;
        state.fence = 1;
      }
      const uint8_t prefix[] = {0xAA, 0x00, 'O', 'K'}, tail[] = {0xCC, 0x33, 0xC3, 0x3C};
      for (uint8_t i = 0; i < 16; ++i) {
        const int c = LcdDrawIO::read();
        if (c < 0) break;
        if (state.fence < 5) {
          state.fence = c == prefix[state.fence - 1] ? state.fence + 1 : c == 0xAA ? 2 : 1;
          continue;
        }
        if (++state.fence_len > 48) { state.fence = 1; state.fence_len = 0; continue; }
        state.fence = c == tail[state.fence - 5] ? state.fence + 1 : c == 0xCC ? 6 : 5;
        if (state.fence == 9) { state.phase = SETTLE; state.deadline = now + 50; break; }
      }
    }
    else if (state.phase == SETTLE && due(now, state.deadline)) { state.phase = DONE; reply("DONE"); }
  }
}
#endif
