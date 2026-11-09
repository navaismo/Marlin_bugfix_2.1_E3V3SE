#include <iostream>
#include <string>
#include <vector>
#include <deque>
#include <iomanip>
#include "../../Marlin/src/e3v3se/LcdDraw.h"
static uint32_t clock_ms;
static bool allowed = true, blocked = false, automatic = true;
static std::deque<uint8_t> rx;
namespace LcdDrawIO {
uint32_t now() { return clock_ms; }
bool allowed() { return ::allowed; }
uint8_t send(const uint8_t *p, uint8_t n) {
  if (blocked) return 0;
  std::cout << "F ";
  for (uint8_t i=0; i<n; ++i) std::cout << std::hex << std::setw(2) << std::setfill('0') << unsigned(p[i]);
  std::cout << std::dec << " " << clock_ms << '\n';
  if (p[1] == 0 && automatic) for (uint8_t c : {0xAA,0x00,0x4F,0x4B,0x56,0x31,0xCC,0x33,0xC3,0x3C}) rx.push_back(c);
  return n + 1;
}
int read() { if (rx.empty()) return -1; int v=rx.front(); rx.pop_front(); return v; }
void reply(const char *s, uint32_t sid, uint16_t seq) {
  std::cout << "L M9001 " << s << " " << std::hex << std::setw(8) << std::setfill('0') << sid
            << " " << std::setw(4) << seq << std::dec << '\n';
}
}
int main() {
  std::string op;
  while (std::cin >> op) {
    if (op == "C") { std::string s; std::getline(std::cin,s); LcdDraw::command(s.c_str()); }
    else if (op == "T") { unsigned n; std::cin >> n; while (n--) { ++clock_ms; LcdDraw::tick(); } }
    else if (op == "Z") std::cout << "Z\n" << std::flush;
    else if (op == "X") LcdDraw::cancel();
    else if (op == "G") { char c; unsigned n; std::cin >> c >> n; LcdDraw::before_command(c,n); }
    else if (op == "A") std::cin >> allowed;
    else if (op == "B") std::cin >> blocked;
    else if (op == "H") std::cin >> automatic;
    else if (op == "R") { std::string s; std::cin >> s; for(size_t i=0;i<s.size();i+=2)rx.push_back(std::stoul(s.substr(i,2),nullptr,16)); }
    else return 2;
  }
}
