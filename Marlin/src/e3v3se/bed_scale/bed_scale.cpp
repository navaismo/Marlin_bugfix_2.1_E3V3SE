#include "../../inc/MarlinConfig.h"
#include "bed_scale.h"
#include "../AutoOffset.h"
#include "../../gcode/queue.h"

#if ENABLED(BED_SCALE)

// Reutilizamos exactamente la infraestructura de AutoOffset
ProbeAcq cell;

BedScaleState bed_scale = {
  /*offset_raw*/ 0,
  /*enabled*/ false,
  /*inited*/ false,

  /*p*/ { {0,0,false}, {0,0,false}, {0,0,false} },

  // Drop defaults (ajustables luego)
  /*drop_threshold_g*/ 20.0f,
  /*drop_confirm_n*/ 2,
  /*drop_ignore_layers*/ 3,

  /*last_layer*/ 0,
  /*last_g_est*/ 0.0f,
  /*have_last_g*/ false,
  /*drop_hits*/ 0
};

// ------------------------------------------------------------
// Pause request (OctoPrint plugin vs SD)
// ------------------------------------------------------------
static inline void bed_scale_request_pause() {
  #if ENABLED(OCTOPRINT_PLUGIN)
    // OJO: esto es solo un "mensaje" para que tu plugin reaccione
    // (tu plugin ya intercepta "pause-job-bs")
    SERIAL_ECHOLNPGM("M9000 pause-job-bs");
  #else
    queue.inject_P(PSTR("M25"));
  #endif
}

// ------------------------------------------------------------
// Init
// ------------------------------------------------------------
void bed_scale_init() {
  if (bed_scale.inited) return;
  cell.hx711.init(HX711_SCK_PIN, HX711_SDO_PIN);
  bed_scale.inited = true;
}

void bed_scale_enable(bool on) {
  bed_scale_init();
  bed_scale.enabled = on;
}

// ------------------------------------------------------------
// Read (IMPORTANT):
// Use AutoOffset readBase() which already does multi-sample + filters.
// We'll repeat it "samples" times only if you want extra smoothing.
// ------------------------------------------------------------
int32_t bed_scale_read_raw_avg(uint8_t samples) {
  bed_scale_init();
  if (samples < 1) samples = 1;

  int64_t acc = 0;
  uint8_t got = 0;

  for (uint8_t i = 0; i < samples; i++) {
    // readBase() devuelve {min, avg, max} ya filtrado. Usamos avg (y).
    const xyz_long_t r = cell.readBase(true);
    if (r.y == INT32_MIN) return INT32_MIN;
    acc += (int32_t)r.y;
    got++;
  }

  return got ? (int32_t)(acc / got) : INT32_MIN;
}

int32_t bed_scale_read_delta_avg(uint8_t samples) {
  const int32_t raw = bed_scale_read_raw_avg(samples);
  if (raw == INT32_MIN) return INT32_MIN;
  return raw - bed_scale.offset_raw;
}

// ------------------------------------------------------------
// TARE
// ------------------------------------------------------------
void bed_scale_tare(uint8_t samples) {
  bed_scale_init();
  const int32_t raw = bed_scale_read_raw_avg(samples);
  if (raw == INT32_MIN) return;

  bed_scale.offset_raw = raw;

  // reset history
  bed_scale.have_last_g = false;
  bed_scale.last_g_est = 0.0f;
  bed_scale.last_layer = 0;
  bed_scale.drop_hits  = 0;
}

// ------------------------------------------------------------
// Save calibration point
// idx: 1..3
// grams must be > 0
// ------------------------------------------------------------
bool bed_scale_set_point(uint8_t idx, float grams, uint8_t samples) {
  if (idx < 1 || idx > 3) return false;
  if (!(grams > 0)) return false;

  const int32_t delta = bed_scale_read_delta_avg(samples);
  if (delta == INT32_MIN) return false;

  CalPoint &cp = bed_scale.p[idx - 1];
  cp.delta = delta;
  cp.grams = grams;
  cp.set = true;
  return true;
}

// ------------------------------------------------------------
// Estimator: piecewise linear with implicit (0g, delta=0) anchor
// Works regardless of polarity, by sorting points by delta.
// NOTE: For your logs (heavier => more negative delta), delta ordering
// will be: 0, -9k, -18k, -22k ...
// ------------------------------------------------------------
static inline bool cp_ok(const CalPoint &p) { return p.set && p.grams > 0; }
static inline void cp_swap(CalPoint &a, CalPoint &b) { CalPoint t = a; a = b; b = t; }

static inline float lerp_f(const float x, const float x0, const float y0, const float x1, const float y1) {
  if (x1 == x0) return y0;
  return y0 + (x - x0) * (y1 - y0) / (x1 - x0);
}

float bed_scale_estimate_grams_from_delta(const int32_t delta) {

  // Build compact list: anchor + valid points
  CalPoint v[4];
  v[0] = { 0, 0.0f, true };

  uint8_t k = 1;
  for (uint8_t i = 0; i < 3; i++)
    if (cp_ok(bed_scale.p[i]))
      v[k++] = bed_scale.p[i];

  // no calibration points
  if (k < 2) return 0.0f;

  // Sort by delta DESC (0 then more negative)
  // Example: 0, -9k, -18k, -22k
  for (uint8_t i = 0; i < k; i++)
    for (uint8_t j = i + 1; j < k; j++)
      if (v[i].delta < v[j].delta)
        cp_swap(v[i], v[j]);

  // Light clamp: if delta is on/above tare side -> 0g
  // (in your polarity, delta near 0 or positive means no load)
  if (delta >= v[0].delta) return 0.0f;

  // Heavy clamp: beyond heaviest point -> max grams
  if (delta <= v[k - 1].delta) return v[k - 1].grams;

  // Find segment where: a.delta >= delta >= b.delta
  for (uint8_t i = 0; i < k - 1; i++) {
    const CalPoint &a = v[i];
    const CalPoint &b = v[i + 1];

    if (delta <= a.delta && delta >= b.delta) {
      return lerp_f((float)delta, (float)a.delta, a.grams, (float)b.delta, b.grams);
    }
  }

  return 0.0f;
}

// ------------------------------------------------------------
// Drop detection (minimal + ALWAYS send pause when confirmed)
// - ignores first N layers
// - requires consecutive hits
// - if confirmed, always calls pause request (no drop_tripped gate)
// ------------------------------------------------------------
bool bed_scale_check_drop_and_pause(const uint16_t layer, const float g_est) {

  // Init history on first reading
  if (!bed_scale.have_last_g) {
    bed_scale.have_last_g = true;
    bed_scale.last_g_est  = g_est;
    bed_scale.last_layer  = layer;
    bed_scale.drop_hits   = 0;
    return false;
  }

  // Only evaluate if layer changes forward (defensive)
  if (layer == bed_scale.last_layer) {
    bed_scale.last_g_est = g_est;
    return false;
  }

  // Ignore early layers
  if (layer <= bed_scale.drop_ignore_layers) {
    bed_scale.last_g_est = g_est;
    bed_scale.last_layer = layer;
    bed_scale.drop_hits  = 0;
    return false;
  }

  // Drop is “weight decreased”
  const float drop_g = bed_scale.last_g_est - g_est;

  if (drop_g >= bed_scale.drop_threshold_g) bed_scale.drop_hits++;
  else bed_scale.drop_hits = 0;

  bed_scale.last_g_est = g_est;
  bed_scale.last_layer = layer;

  if (bed_scale.drop_hits >= bed_scale.drop_confirm_n) {

    SERIAL_ECHOPGM("BedScale DROP DETECTED on layer ");
    SERIAL_ECHO((int)layer);
    SERIAL_ECHOPGM(" drop_g=");
    SERIAL_ECHO(drop_g, 2);
    SERIAL_ECHOPGM(" thr=");
    SERIAL_ECHOLN(bed_scale.drop_threshold_g, 2);

    // IMPORTANT: Always send the pause request when confirmed
    bed_scale_request_pause();
    return true;
  }

  return false;
}

// Preserve the original per-layer protocol and experimental detection policy.
void bed_scale_on_layer(const int32_t layer) {
  const int32_t raw = bed_scale_read_raw_avg(1);
  if (raw == INT32_MIN) return;
  const int32_t delta = raw - bed_scale.offset_raw;
  const float g_est = bed_scale_estimate_grams_from_delta(delta);
  SERIAL_ECHOPGM("BedScale L");
  SERIAL_ECHO(layer);
  SERIAL_ECHOPGM(" delta=");
  SERIAL_ECHO(delta);
  SERIAL_ECHOPGM(" g_est=");
  SERIAL_ECHOLN(g_est, 2);
  if (bed_scale_check_drop_and_pause((uint16_t)layer, g_est))
    SERIAL_ECHOLNPGM("BedScale Object drop detected - Pause requested");
}

#endif // ENABLED(BED_SCALE)
