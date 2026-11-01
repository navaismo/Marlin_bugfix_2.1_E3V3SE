#pragma once
#include "../../inc/MarlinConfig.h"

#if ENABLED(BED_SCALE)

#if DISABLED(USE_AUTOZ_TOOL_2)
  #error "BED_SCALE requires USE_AUTOZ_TOOL_2 (HX711 and filters)."
#endif
#if DISABLED(SET_PROGRESS_MANUALLY)
  #error "BED_SCALE requires SET_PROGRESS_MANUALLY for M73 L sampling."
#endif

struct CalPoint {
  int32_t delta;   // raw - offset_raw
  float   grams;   // grams at that delta
  bool    set;
};

struct BedScaleState {
  // Core
  int32_t offset_raw;
  bool enabled;
  bool inited;

  // Calibration points (3)
  CalPoint p[3];

  // Drop detection (minimal)
  float    drop_threshold_g;   // grams
  uint8_t  drop_confirm_n;     // consecutive layers needed
  uint16_t drop_ignore_layers; // ignore first N layers

  // History
  uint16_t last_layer;
  float    last_g_est;
  bool     have_last_g;
  uint8_t  drop_hits;
};

extern BedScaleState bed_scale;

// Init / enable
void bed_scale_init();
void bed_scale_enable(bool on);

// Read (filtered via AutoOffset pipeline)
int32_t bed_scale_read_raw_avg(uint8_t samples = 1);
int32_t bed_scale_read_delta_avg(uint8_t samples = 1);

// Tare / calibration points
void bed_scale_tare(uint8_t samples = 1);
bool bed_scale_set_point(uint8_t idx, float grams, uint8_t samples = 1);

// Estimator
float bed_scale_estimate_grams_from_delta(const int32_t delta);

// M73 L hook: serial format is consumed by the bed-scale plugin.
void bed_scale_on_layer(const int32_t layer);

// Drop logic (calls pause request internally)
bool bed_scale_check_drop_and_pause(const uint16_t layer, const float g_est);

#endif // ENABLED(BED_SCALE)
