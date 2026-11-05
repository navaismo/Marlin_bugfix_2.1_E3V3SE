#pragma once

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

#define DWIN_CREALITY_LCD 1
#ifndef DWIN_RENDER_THUMBNAIL
  #define DWIN_RENDER_THUMBNAIL 1
#endif
#define ALL(A,B) ((A) && (B))

struct Card {
  std::string contents;
  size_t pos = 0;
  bool opened = false, fail_open = false;
  unsigned closes = 0;
  void openFileRead(const char*) { pos = 0; opened = !fail_open; }
  bool isFileOpen() { return opened; }
  bool eof() { return pos >= contents.size(); }
  int16_t get() { return eof() ? -1 : contents[pos++]; }
  void setIndex(size_t p) { pos = p; }
  void closefile() { opened = false; ++closes; }
};
extern Card card;

struct HAL { void watchdog_refresh(); };
extern HAL hal;
void delay(int ms);
void DWIN_Set_Color(uint16_t foreground, uint16_t background);
void DWIN_Fill_Rect_Raw(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1);
