/** E3V3SE LCD-editable power-loss recovery options. */
#include "../inc/MarlinConfig.h"

#if ENABLED(DWIN_PLR_MENU)

#include "PLRSettings.h"
#include "../feature/powerloss.h"
#include "../libs/BL24CXX.h"
#include "../module/temperature.h"
#include <string.h>

PLRSettings plrSettings;

// The wizard uses 0x01..0x06. Marlin's settings start at byte 100.
// Keep this versioned, checksummed extension outside both regions.
static constexpr uint16_t PLR_SETTINGS_ADDRESS = 0x20;
static_assert(sizeof(PLRSettings) == 10, "Unexpected PLR settings layout");
static constexpr uint8_t PLR_SETTINGS_SIZE = 4 + sizeof(PLRSettings) + 2;
static_assert(PLR_SETTINGS_ADDRESS + PLR_SETTINGS_SIZE <= 100, "PLR settings overlap Marlin EEPROM");

static uint16_t plr_settings_crc(const uint8_t *data, const uint8_t count) {
  uint16_t crc = 0xFFFF;
  for (uint8_t i = 0; i < count; ++i) {
    crc ^= uint16_t(data[i]) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

void PLRSettings::reset() {
  heat_bed = ENABLED(PLR_HEAT_BED_ON_REBOOT);
  heat_nozzle = ENABLED(PLR_HEAT_NOZZLE_ON_REBOOT);
  bed_extra = 0;
  #ifdef PLR_HEAT_BED_EXTRA
    bed_extra = PLR_HEAT_BED_EXTRA;
  #endif
  zraise_tenths = constrain(lroundf(POWER_LOSS_ZRAISE * 10), 0L, 200L);
  purge_tenths = 0;
  #ifdef POWER_LOSS_PURGE_LEN
    purge_tenths = constrain(lroundf(POWER_LOSS_PURGE_LEN * 10), 0L, 500L);
  #endif
  save_z_hundredths = 5;
  #ifdef POWER_LOSS_MIN_Z_CHANGE
    save_z_hundredths = constrain(lroundf(POWER_LOSS_MIN_Z_CHANGE * 100), 1L, 100L);
  #endif
  LIMIT(bed_extra, 0, 20);
}

bool PLRSettings::valid() const {
  return heat_bed <= 1 && heat_nozzle <= 1
      && WITHIN(bed_extra, 0, 20) && zraise_tenths <= 200
      && purge_tenths <= 500 && WITHIN(save_z_hundredths, 1, 100);
}

void PLRSettings::load() {
  uint8_t data[PLR_SETTINGS_SIZE];
  BL24CXX::read(PLR_SETTINGS_ADDRESS, data, sizeof(data));
  const uint16_t stored_crc = uint16_t(data[sizeof(data) - 2]) | uint16_t(data[sizeof(data) - 1]) << 8;
  PLRSettings loaded;
  memcpy(&loaded, data + 4, sizeof(loaded));
  if (memcmp(data, "PLR1", 4) == 0 && stored_crc == plr_settings_crc(data, sizeof(data) - 2) && loaded.valid())
    *this = loaded;
  else
    reset();
}

bool PLRSettings::save() const {
  if (!valid()) return false;
  uint8_t data[PLR_SETTINGS_SIZE] = { 'P', 'L', 'R', '1' };
  memcpy(data + 4, this, sizeof(*this));
  const uint16_t crc = plr_settings_crc(data, sizeof(data) - 2);
  data[sizeof(data) - 2] = crc & 0xFF;
  data[sizeof(data) - 1] = crc >> 8;
  // Invalidate first, then commit the signature after the payload and CRC.
  BL24CXX::writeOneByte(PLR_SETTINGS_ADDRESS, 0);
  BL24CXX::write(PLR_SETTINGS_ADDRESS + 1, data + 1, sizeof(data) - 1);
  BL24CXX::writeOneByte(PLR_SETTINGS_ADDRESS, data[0]);
  uint8_t stored[PLR_SETTINGS_SIZE];
  BL24CXX::read(PLR_SETTINGS_ADDRESS, stored, sizeof(stored));
  return memcmp(data, stored, sizeof(data)) == 0;
}

void PLRSettings::preheat(const bool on) const {
  if (heat_bed)
    thermalManager.setTargetBed(on && recovery.info.target_temperature_bed > 0
      ? constrain(recovery.info.target_temperature_bed + bed_extra, 0, BED_MAX_TARGET) : 0);
  if (heat_nozzle)
    thermalManager.setTargetHotend(on ? constrain(recovery.info.target_temperature[0], 0, thermalManager.hotend_max_target(0)) : 0, 0);
}

#endif
