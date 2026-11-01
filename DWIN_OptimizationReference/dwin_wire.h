// Shared DWIN wire protocol + throttle-strategy code for dwin_replay.cpp and
// dwin_stress.cpp. Frames sent here are byte-for-byte identical in layout to
// what Marlin/src/lcd/dwin/creality/dwin_lcd.cpp's DWIN_Send() produces:
//   0xAA <opcode> <data...> 0xCC 0x33 0xC3 0x3C
// with every byte (including the 0xAA and the tail) separated by
// interbyte_us, matching DWIN_Send's `delayMicroseconds(1)` per byte.
//
// Three throttle strategies:
//   PerFrame:  delay after every single frame (SET and FILL), plus extra
//              time scaled to a fill's height for vertically-merged rects.
//              Matches dwin_lcd.cpp's thumb_throttle().
//   BatchAll:  delay only every N frames, counting SET and FILL together.
//              The ORIGINAL DWIN_RenderThumb did delay(25) every 15
//              *pixels*, and since it emits 2 frames/pixel, that is
//              batch_size=30, batch_delay_ms=25.
//   BatchFill: delay only every N rect-FILL commands; SET (palette) frames
//              never delay on their own.
//
// SAFETY: an unthrottled flood of DWIN commands has previously overrun this
// panel's input buffer badly enough to require a PHYSICAL POWER CYCLE to
// recover. Never run with all throttling disabled.
#pragma once

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>

enum class Strategy { PerFrame, BatchAll, BatchFill };

struct Options {
  std::string port;
  std::string file;
  int baud = 115200;
  Strategy strategy = Strategy::PerFrame;
  double base_delay_ms = 3.0;      // PerFrame: delay after every frame (SET and FILL)
  double set_delay_ms = -1.0;      // PerFrame: override for SET frames; -1 = use base_delay_ms
  int row_us = 0;                  // PerFrame: extra delay per row of FILL height beyond 1
  int batch_size = 0;              // BatchAll: frames (SET+FILL) per delay
  double batch_delay_ms = 25.0;    // BatchAll: delay applied every batch_size frames
  int fill_batch_size = 0;         // BatchFill: FILL commands per delay; SET commands never delay
  double fill_batch_delay_ms = 25.0; // BatchFill: delay applied every fill_batch_size fills
  int interbyte_us = 1;       // matches DWIN_Send's delayMicroseconds(1)
  bool clear_first = false;
};

// Whole-screen bounds (DWIN_WIDTH/DWIN_HEIGHT in dwin_lcd.h).
constexpr uint16_t SCREEN_X0 = 0, SCREEN_Y0 = 0, SCREEN_X1 = 239, SCREEN_Y1 = 319;
constexpr uint16_t THUMB_SIZE = 96; // matches the fixed 96x96 thumbnail

// Historically-correct throttle presets, so tools can reproduce exactly
// what each algorithm actually ran at rather than an arbitrary guess.
constexpr int ORIGINAL_BATCH_SIZE = 30;      // 2 frames/pixel x 15 px
constexpr double ORIGINAL_BATCH_DELAY_MS = 25.0;
constexpr double NEW_BASE_DELAY_MS = 3.0;
constexpr int NEW_ROW_US = 500;

// Converts a (possibly fractional) millisecond delay to whole microseconds
// for usleep(), so e.g. 0.5ms delays work.
inline long ms_to_us(double ms) {
  return std::llround(ms * 1000.0);
}

inline int open_serial(const std::string &path, int baud) {
  int fd = open(path.c_str(), O_RDWR | O_NOCTTY);
  if (fd < 0) {
    perror(("open " + path).c_str());
    exit(1);
  }
  termios tty{};
  if (tcgetattr(fd, &tty) != 0) {
    perror("tcgetattr");
    exit(1);
  }
  speed_t speed = B115200;
  switch (baud) {
    case 9600: speed = B9600; break;
    case 19200: speed = B19200; break;
    case 38400: speed = B38400; break;
    case 57600: speed = B57600; break;
    case 115200: speed = B115200; break;
    case 230400: speed = B230400; break;
    default:
      fprintf(stderr, "unsupported baud %d, falling back to 115200\n", baud);
  }
  cfsetispeed(&tty, speed);
  cfsetospeed(&tty, speed);

  tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8;
  tty.c_cflag |= (CLOCAL | CREAD);
  tty.c_cflag &= ~(PARENB | PARODD);
  tty.c_cflag &= ~CSTOPB;
  tty.c_cflag &= ~CRTSCTS;
  tty.c_lflag = 0;
  tty.c_oflag = 0;
  tty.c_iflag &= ~(IXON | IXOFF | IXANY | ICRNL | INLCR);
  tty.c_cc[VMIN] = 0;
  tty.c_cc[VTIME] = 0;

  if (tcsetattr(fd, TCSANOW, &tty) != 0) {
    perror("tcsetattr");
    exit(1);
  }
  tcflush(fd, TCIOFLUSH);
  return fd;
}

inline void send_byte(int fd, uint8_t b, int interbyte_us) {
  if (write(fd, &b, 1) != 1) {
    perror("write");
    exit(1);
  }
  if (interbyte_us > 0) usleep(interbyte_us);
}

inline void send_frame(int fd, uint8_t opcode, const std::vector<uint8_t> &data, int interbyte_us) {
  send_byte(fd, 0xAA, interbyte_us);
  send_byte(fd, opcode, interbyte_us);
  for (uint8_t b : data) send_byte(fd, b, interbyte_us);
  static const uint8_t tail[4] = {0xCC, 0x33, 0xC3, 0x3C};
  for (uint8_t b : tail) send_byte(fd, b, interbyte_us);
}

inline std::vector<uint8_t> word(uint16_t v) {
  return {uint8_t(v >> 8), uint8_t(v & 0xFF)};
}

// Shared throttle state across a whole replay run -- the batched models'
// frame counter must persist across both SET and FILL calls, exactly like
// the original firmware's `pixel_count` persisted across both frames of a
// per-pixel draw.
struct ThrottleState {
  int frame_count = 0;
};

inline void throttle_after_frame(const Options &opt, ThrottleState &st, int rows, bool is_set) {
  switch (opt.strategy) {
    case Strategy::BatchAll:
      if (++st.frame_count >= opt.batch_size) {
        usleep(ms_to_us(opt.batch_delay_ms));
        st.frame_count = 0;
      }
      return;
    case Strategy::BatchFill:
      // Palette-set frames never delay on their own here -- only rect-fill
      // commands count toward the batch.
      if (is_set) return;
      if (++st.frame_count >= opt.fill_batch_size) {
        usleep(ms_to_us(opt.fill_batch_delay_ms));
        st.frame_count = 0;
      }
      return;
    case Strategy::PerFrame: {
      const double d = (is_set && opt.set_delay_ms >= 0.0) ? opt.set_delay_ms : opt.base_delay_ms;
      const long total_us = ms_to_us(d) + long(rows) * opt.row_us;
      if (total_us > 0) usleep(total_us);
      return;
    }
  }
}

inline void set_color(int fd, uint16_t color, const Options &opt, ThrottleState &st) {
  std::vector<uint8_t> data = word(color);
  auto bc = word(0xFFFF);
  data.insert(data.end(), bc.begin(), bc.end());
  send_frame(fd, 0x40, data, opt.interbyte_us);
  throttle_after_frame(opt, st, 0, /*is_set=*/true);
}

inline void fill_rect(int fd, uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1, const Options &opt, ThrottleState &st) {
  std::vector<uint8_t> data;
  for (uint16_t v : {x0, y0, x1, y1}) {
    auto w = word(v);
    data.insert(data.end(), w.begin(), w.end());
  }
  send_frame(fd, 0x5B, data, opt.interbyte_us);
  const int rows = (y1 > y0) ? (y1 - y0) : 0;
  throttle_after_frame(opt, st, rows, /*is_set=*/false);
}

inline std::string describe_settings(const Options &opt) {
  char buf[160];
  switch (opt.strategy) {
    case Strategy::BatchAll:
      snprintf(buf, sizeof(buf), "batch-all: batch_size=%d batch_delay=%gms", opt.batch_size, opt.batch_delay_ms);
      break;
    case Strategy::BatchFill:
      snprintf(buf, sizeof(buf), "batch-fill: fill_batch_size=%d fill_batch_delay=%gms",
               opt.fill_batch_size, opt.fill_batch_delay_ms);
      break;
    case Strategy::PerFrame:
      snprintf(buf, sizeof(buf), "per-frame: base_delay=%gms row_us=%d", opt.base_delay_ms, opt.row_us);
      break;
  }
  return buf;
}

inline std::vector<std::string> load_commands(const std::string &path) {
  FILE *f = fopen(path.c_str(), "r");
  if (!f) {
    perror(("open " + path).c_str());
    exit(1);
  }
  std::vector<std::string> lines;
  char buf[256];
  while (fgets(buf, sizeof(buf), f)) lines.push_back(buf);
  fclose(f);
  return lines;
}

// Parses one "kind:a:b" throttle spec and applies it to opt. Shared between
// dwin_replay.cpp's --sweep and dwin_stress.cpp's --strategy-spec.
//   per:<base_delay_ms>:<row_us>            -- Strategy::PerFrame
//   batch:<batch_size>:<batch_delay_ms>      -- Strategy::BatchAll (all frames)
//   fillbatch:<fill_batch_size>:<delay_ms>   -- Strategy::BatchFill (fill-rects only)
inline void parse_throttle_spec(const std::string &spec, Options &opt) {
  size_t p1 = spec.find(':');
  size_t p2 = spec.find(':', p1 == std::string::npos ? p1 : p1 + 1);
  if (p1 == std::string::npos || p2 == std::string::npos) {
    fprintf(stderr, "bad throttle spec (want kind:a:b): %s\n", spec.c_str());
    exit(1);
  }
  const std::string kind = spec.substr(0, p1);
  const double a = std::stod(spec.substr(p1 + 1, p2 - p1 - 1));
  const double b = std::stod(spec.substr(p2 + 1));
  if (kind == "per") {
    opt.strategy = Strategy::PerFrame;
    opt.base_delay_ms = a;
    opt.row_us = int(std::lround(b));
  } else if (kind == "batch") {
    opt.strategy = Strategy::BatchAll;
    opt.batch_size = int(std::lround(a));
    opt.batch_delay_ms = b;
  } else if (kind == "fillbatch") {
    opt.strategy = Strategy::BatchFill;
    opt.fill_batch_size = int(std::lround(a));
    opt.fill_batch_delay_ms = b;
  } else {
    fprintf(stderr, "unknown throttle kind '%s' (want per, batch, or fillbatch)\n", kind.c_str());
    exit(1);
  }
}

inline std::vector<std::string> split_commas(const std::string &s) {
  std::vector<std::string> out;
  size_t start = 0;
  while (start <= s.size()) {
    size_t comma = s.find(',', start);
    if (comma == std::string::npos) {
      out.push_back(s.substr(start));
      break;
    }
    out.push_back(s.substr(start, comma - start));
    start = comma + 1;
  }
  return out;
}
