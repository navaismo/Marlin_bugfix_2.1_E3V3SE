#include "../../inc/MarlinConfig.h"

#if ENABLED(BED_SCALE)

#include "../../gcode/gcode.h"
#include "bed_scale.h"

/********
*
* M770 A(Samples) ->  report + curve estimation
* M771 A(Samples) ->  TARE
* M772 I(idx) S(grams) A(samples) ->  Save calibration index point
*
*********
*
* Examples:
*
* M771 A32 =           TARE with 32 samples
* M772 I1 S640 A32 =   Save calibration point 1 with 640g
* M772 I2 S1250 A32 =  Save calibration point 2 with 1250g
* M772 I3 S2000 A32 =  Save calibration point 3 with 2000g (optional)
* M770 A16 =           Report + curve estimation
*
*/

// M770: report + curve estimation
void GcodeSuite::M770() {
  const uint8_t samples = (uint8_t)parser.byteval('A', 1);

  const int32_t raw = bed_scale_read_raw_avg(samples);
  if (raw == INT32_MIN) { SERIAL_ECHOLNPGM("BS raw=INVALID"); return; }

  const int32_t delta = raw - bed_scale.offset_raw;
  const float g = bed_scale_estimate_grams_from_delta(delta);

  SERIAL_ECHOPGM("BS raw=");
  SERIAL_ECHO(raw);
  SERIAL_ECHOPGM(" offset=");
  SERIAL_ECHO(bed_scale.offset_raw);
  SERIAL_ECHOPGM(" delta=");
  SERIAL_ECHO(delta);
  SERIAL_ECHOPGM(" g_est=");
  SERIAL_ECHOLN(g, 2);
}


// M771: TARE
void GcodeSuite::M771() {
  const uint8_t samples = (uint8_t)parser.byteval('A', 16);

  bed_scale_tare(samples);

  SERIAL_ECHOPGM("BS TARE ok offset_raw=");
  SERIAL_ECHOLN(bed_scale.offset_raw);
}

// M772: Save calibration point
void GcodeSuite::M772() {
  if (!parser.seen('S') || !parser.seen('I')) {
    SERIAL_ECHOLNPGM("BS CAL usage: M772 I<1..3> S<grams> [A<samples>]");
    return;
  }

  const uint8_t idx = (uint8_t)parser.byteval('I');
  if (idx < 1 || idx > 3) { SERIAL_ECHOLNPGM("BS CAL idx must be 1..3"); return; }

  const float grams = parser.floatval('S');
  const uint8_t samples = (uint8_t)parser.byteval('A', 16);

  const bool ok = bed_scale_set_point(idx, grams, samples);
  if (!ok) { SERIAL_ECHOLNPGM("BS CAL failed"); return; }

  SERIAL_ECHOPGM("BS CAL ok idx=");
  SERIAL_ECHO((int)idx);
  SERIAL_ECHOPGM(" grams=");
  SERIAL_ECHO(grams, 3);
  SERIAL_ECHOPGM(" delta=");
  SERIAL_ECHOLN(bed_scale.p[idx - 1].delta);
}

#endif // ENABLED(BED_SCALE)
