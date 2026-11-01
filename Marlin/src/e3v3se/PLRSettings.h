/** E3V3SE LCD-editable power-loss recovery options. */
#pragma once

#include "../inc/MarlinConfigPre.h"

#if ENABLED(DWIN_PLR_MENU)
  struct PLRSettings {
    uint8_t heat_bed, heat_nozzle;
    int16_t bed_extra;
    uint16_t zraise_tenths, purge_tenths, save_z_hundredths;

    void reset();
    void load();
    bool save() const;
    bool valid() const;
    void preheat(const bool on) const;
    float zraise() const { return zraise_tenths * 0.1f; }
    float purge() const { return purge_tenths * 0.1f; }
    float save_step() const { return save_z_hundredths * 0.01f; }
  };
  extern PLRSettings plrSettings;
#endif
