#include "AutoOffset.h"
#include "../inc/MarlinConfigPre.h"
#if ENABLED(FT_MOTION)
  #include "../module/ft_motion.h"
#endif

#if ENABLED(USE_AUTOZ_TOOL_2)

/*
 *Function Name: getStr(float f)
 *Purpose: Convert floating point to string (Note: ftoa() or %f is not used here because of a BUG in some Marlin versions that will cause floating point conversion to fail)
 *Params: (float)f The floating point value to be converted
 *Return: (char*) converted string
 *Attention: The number of reload calls should not exceed 16
 */
char *getStr(float f)
{
  static char str[16][16];
  static int index = 0;

  memset(str[index % 16], '\0', 16);
  sprintf(str[index % 16], (f >= 0 ? "+%d.%03d" : "-%d.%03d"), (int)fabs(f), ((int)(fabs(f) * 1000)) % 1000);

  return str[index++ % 16];
}

/*
 *Function Name: ckGpioIsInited(int pin)
 *Purpose: Detect whether the given pin has been initialized to avoid repeated initialization of clk, which may cause timing confusion.
 *Params: (int)pin pin to be detected
 *Return: (bool) true=pin has been initialized; false=pin has not been initialized.
 */
bool HX711::ckGpioIsInited(int pin)
{
  static int pinList[32] = {0};
  FOR_LOOP_TIMES(i, 0, 32, {CHECK_AND_RETURN((pinList[i] == pin), true);CHECK_AND_RUN_AND_RETURN((pinList[i] == 0), {pinList[i] = pin;}, false); });
  return true;
}

/*
 *Function Name: init(int clkPin, int sdoPin)
 *Purpose: HX711 driver initialization (80HZ sampling rate)
 *Params: (int)clkPin The clock signal corresponding to HX711
 *(int)Data signal corresponding to sdoPin HX711
 *Return: None
 */
void HX711::init(int clkPin, int sdoPin)
{
  this->clkPin = clkPin;
  this->sdoPin = sdoPin;
  CHECK_AND_RUN((!HX711::ckGpioIsInited(sdoPin)), GPIO_SET_MODE(sdoPin, 0));
  CHECK_AND_RUN((!HX711::ckGpioIsInited(clkPin)), {GPIO_SET_MODE(clkPin, 1); GPIO_SET_VAL(clkPin, 0); });
}

/*
 *Function Name: getVal(bool isShowMsg)
 *Purpose: Block and read the pressure value, the maximum blocking time is 20ms
 *Params: (bool)isShowMsg whether to print debugging information
 *Return: (int) the pressure value read
 *Attention: To achieve a sampling rate of 80HZ, ensure that the frequency configuration pin of HX711 has been set to the corresponding level.
 */
int HX711::getVal(bool isShowMsg, bool reject_timeout)
{
  static unsigned int lastTickMs = 0;
  int count = 0;
  unsigned int ms = GET_TICK_MS();

  GPIO_SET_VAL(clkPin, 0);

  while (GPIO_GET_VAL(sdoPin) == 1 && (GET_TICK_MS() - ms <= 20)) // The sampling rate is 80 hz (12ms period), and the maximum delay here is 20ms.
    MARLIN_CORE_IDLE();

  // A scale sample must never turn a not-ready ADC into a valid weight.
  if (reject_timeout && GPIO_GET_VAL(sdoPin) == 1) return INT32_MIN;

  DISABLE_ALL_ISR();
  for (int i = 0; i < 24; i++)
  {
    GPIO_SET_VAL(clkPin, 1);
    count = count << 1;
    GPIO_SET_VAL(clkPin, 0);
    CHECK_AND_RUN((GPIO_GET_VAL(sdoPin) == 1), (count++));
  }

  GPIO_SET_VAL(clkPin, 1);
  count |= ((count & 0x00800000) != 0 ? 0xFF000000 : 0); // 24-bit signed, converted to 32-bit signed
  GPIO_SET_VAL(clkPin, 0);
  ENABLE_ALL_ISR();

  // CHECK_AND_RUN(isShowMsg, {PRINTF("T=%08d, S=%08d\n", (int)(GET_TICK_MS() -lastTickMs), (int)count);lastTickMs = GET_TICK_MS(); });
  if (isShowMsg)
  {
    lastTickMs = GET_TICK_MS();
    SERIAL_ECHOLNPGM_P("T=", (int)(GET_TICK_MS() - lastTickMs), ", S=", (int)count);
  }
  return count;
}

/*
*Function Name: hFilter(double *vals, int count, double cutFrqHz, double acqFrqHz)
*Purpose: High-pass filter the data
*Params: (double*)vals data to be filtered
                  (int)count length of data to be filtered
                  (double)cutFrqHz filter cutoff frequency
*(double)acqFrqHz filter sampling frequency (equivalent to the sampling frequency of HX711 80HZ)
*Return: None
*/
void Filters::hFilter(double *vals, int count, double cutFrqHz, double acqFrqHz)
{
  double rc = 1.0f / 2.0f / PI / cutFrqHz;
  double coff = rc / (rc + 1 / acqFrqHz);
  double vi = vals[0], viPrev = vals[0], vo = 0, voPrev = 0;
  FOR_LOOP_TIMES(i, 0, count, {
    vi = vals[i];
    vo = (vi - viPrev + voPrev) * coff;
    voPrev = vo;
    viPrev = vi;
    vals[i] = fabs(vo);
  });
}

/*
 *Function Name: tFilter(double *vals, int count)
 *Purpose: perform burr filtering on data
 *Params: (double)cutFrqHz filter cutoff frequency
 *(double)acqFrqHz filter sampling frequency (equivalent to the sampling frequency of HX711 80HZ)
 *Return: None
 */
void Filters::tFilter(double *vals, int count)
{
  FOR_LOOP_TIMES(i, 0, count - 3, {
   double  minVal = (fabs(vals[i]) < fabs(vals[i+1]) ? vals[i] : vals[i+1]);
    vals[i] = fabs(minVal) < fabs(vals[i+2]) ? minVal : vals[i+2]; });
}

/*
*Function Name: lFilter(double *vals, int count, double k1New)
*Purpose: Low-pass filter the data
*Params: (double*)vals data to be filtered
                  (int)count length of data to be filtered
                  (double)k1New first-order filter parameters
*Return: None
*/
void Filters::lFilter(double *vals, int count, double k1New)
{
  FOR_LOOP_TIMES(i, 1, count, vals[i] = vals[i - 1] * (1 - k1New) + vals[i] * k1New);
}

/*
 *Function Name: readBase()
 *Purpose: Get the maximum, minimum, and average pressure values within a given number (BASE_COUNT/2).
 *Params: None
 *Return: (xyz_long_t) x=MIN; y=AVG; z=MAX;
 */
xyz_long_t ProbeAcq::readBase(bool reject_timeout)
{
  static double vals[PI_COUNT / 2] = {0};

  double minVal = +0x00FFFFFF, avgVal = 0, maxVal = -0x00FFFFFF; // min avg max
  for (uint8_t i = 0; i < PI_COUNT; ++i) {
    const int value = hx711.getVal(false, reject_timeout);
    if (reject_timeout && value == INT32_MIN) return { INT32_MIN, INT32_MIN, INT32_MIN };
    if (i >= PI_COUNT / 2) vals[i - PI_COUNT / 2] = value;
  }

  Filters::tFilter(vals, PI_COUNT / 2);
  Filters::lFilter(vals, PI_COUNT / 2, LFILTER_K1_NEW);

  ARY_MIN(minVal, vals, PI_COUNT / 2);
  ARY_MAX(maxVal, vals, PI_COUNT / 2);
  ARY_AVG(avgVal, vals, PI_COUNT / 2);
#if ENABLED(SHOW_MSG)
  PRINTF("\n***BASE:MIN=%d, AVG=%d, MAX=%d***\n\n", (int)minVal, (int)avgVal, (int)maxVal);
#endif
  xyz_long_t xyz = {(int)minVal, (int)avgVal, (int)maxVal};
  return xyz;
}

/*
 *Function Name: checHx711()
 *Purpose: Check whether the HX711 module is working properly
 *Params: None
 *Return: true=normal; false=abnormal;
 *Attention: Theoretically, the difference between the maximum and maximum pressure of HX711 within a certain period of time should be greater than 100 and less than MIN_HOLD.
 */
bool ProbeAcq::checHx711()
{
  xyz_long_t bv = readBase();
  return (abs(bv.x - bv.z) < 100 || abs(bv.x - bv.z) > MIN_HOLD) ? false : true;
}

// === Local utilities for median/validation ===
static inline bool is_valid_offset(const float v) {
  if (isnan(v) || isinf(v)) return false;
  if (fabsf(v) < 0.001f)    return false;                     // discard 0 "ghost"
  if (v < ZOFFSET_VALUE_MIN || v > ZOFFSET_VALUE_MAX) return false;
  return true;
}

static float median_of(float *vals, int n) {
  // simple insert (small n) to sort
  for (int i = 1; i < n; ++i) {
    float key = vals[i];
    int j = i - 1;
    while (j >= 0 && vals[j] > key) { vals[j + 1] = vals[j]; --j; }
    vals[j + 1] = key;
  }
  if (n % 2) return vals[n / 2];
  return 0.5f * (vals[n/2 - 1] + vals[n/2]);
}

// Robust location estimate from multiple bed points.
// 1) Start from median (high breakdown-point),
// 2) Estimate scale with MAD,
// 3) Reject gross outliers,
// 4) Compute a weighted mean with:
//    - Huber residual weight (less influence from noisy points),
//    - Spatial weight (closer to load-cell reference contributes more).
static float robust_offset_from_points(const float *vals, const xyz_float_t *pts, const uint8_t n) {
  if (!n) return NAN;
  if (n == 1) return vals[0];

  float work[5], abs_dev[5];
  for (uint8_t i = 0; i < n; ++i) work[i] = vals[i];
  const float z_med = median_of(work, n);

  for (uint8_t i = 0; i < n; ++i) abs_dev[i] = fabsf(vals[i] - z_med);
  const float mad = median_of(abs_dev, n);
  const float sigma = _MAX(mad * 1.4826f, 0.01f); // Keep a minimum scale for tiny spreads

  constexpr float HUBER_K = 2.5f;
  constexpr float INLIER_K = 3.0f;
  constexpr float DIST_SCALE_MM = 80.0f;
  const float inlier_gate = _MAX(INLIER_K * sigma, ZOFFSET_COMPARE);
  const float inv_dist_scale2 = 1.0f / (DIST_SCALE_MM * DIST_SCALE_MM);
  const xyz_float_t press_ref = PRESS_XYZ_POS;

  float sum_w = 0, sum_wz = 0;
  uint8_t inliers = 0;
  for (uint8_t i = 0; i < n; ++i) {
    const float ri = fabsf(vals[i] - z_med);
    if (ri > inlier_gate) continue;

    ++inliers;
    const float wr = (ri <= HUBER_K * sigma || ri <= 0.0001f) ? 1.0f : (HUBER_K * sigma / ri);
    const float dx = pts[i].x - press_ref.x;
    const float dy = pts[i].y - press_ref.y;
    const float ws = 1.0f / (1.0f + (dx * dx + dy * dy) * inv_dist_scale2);
    const float w = wr * ws;

    sum_w += w;
    sum_wz += w * vals[i];
  }

  if (!inliers || sum_w <= 0) return z_med;

  float z_est = sum_wz / sum_w;

  // Guardrail: if weights drag the estimate too far from median, clamp shift.
  const float max_shift = _MAX(0.25f, 2.0f * sigma);
  if (fabsf(z_est - z_med) > max_shift)
    z_est = z_med + (z_est > z_med ? max_shift : -max_shift);

  PRINTF("***ROBUST_Z: n=%d in=%d med=%s mad=%s sig=%s est=%s***\n",
         (int)n, (int)inliers, getStr(z_med), getStr(mad), getStr(sigma), getStr(z_est));
  return z_est;
}

// probeTimes(0, basePos_mm, 0.02, -10, 0, MIN_HOLD, MAX_HOLD));
float ProbeAcq::probeTimes(int max_times, xyz_float_t rdy_pos, float step_mm, float min_dis_mm, float max_z_err, int min_hold, int max_hold) {
  ProbeAcq pa;
  float mm0 = 0, mm1 = 0;
  pa.hx711.init(HX711_SCK_PIN, HX711_SDO_PIN);

  // Safer depth limit (no more than -3mm)
  // min_dis_mm is negative; fmaxf(-10, -3) => -3
  #if defined(__cplusplus)
    pa.minZ_mm = (float)fmax((double)min_dis_mm, -3.0);
  #else
    pa.minZ_mm = (min_dis_mm > -3.0f ? min_dis_mm : -3.0f);
  #endif

  pa.basePos_mm      = rdy_pos;
  pa.baseSpdXY_mm_s  = 100;
  pa.baseSpdZ_mm_s   = 2;       // go down slower to give the HX711 “time”
  pa.step_mm         = step_mm; // 0.02–0.03 recommended
  pa.minHold         = min_hold;
  pa.maxHold         = max_hold;

  FOR_LOOP_TIMES(i, 0, (max_times <= 0 ? 1 : max_times), {
    mm0 = pa.probePointByStep()->outVal_mm;
    CHECK_AND_RETURN(max_times <= 0, mm0);
    mm1 = pa.probePointByStep()->outVal_mm;
    CHECK_AND_RETURN(fabs(mm0 - mm1) <= max_z_err, (mm0 + mm1) / 2);
  });
  return (mm0 + mm1) / 2;
}

/*
 *Function Name: shakeZAxis(int times)
 *Purpose: Vibrate the Z-axis to eliminate gap stress
 *Params: (int)times the number of vibrations
 */
// void ProbeAcq::shakeZAxis(int times)
// {
//   // Version compatible with 2.1.x using scheduler (not raw STEP)
//   const float z0 = motion.position[Z_AXIS];
//   const float amp = 0.06f; // 0.06 mm up/down per cycle
//   FOR_LOOP_TIMES(i, 0, times, {
//     DO_BLOCKING_MOVE_TO_Z(z0 + amp, 60);
//     DO_BLOCKING_MOVE_TO_Z(z0, 60);
//   });
// }
void ProbeAcq::shakeZAxis(int times) {
  const float z0 = motion.position[Z_AXIS];

  //Approximate equivalent to the old version:
  //4 *0.01 mm = 0.04 mm rise and 0.04 mm fall
  constexpr float SHAKE_STEP_MM      = 0.01f;
  constexpr uint8_t STEPS_PER_SIDE   = 4;
  constexpr float AMP_MM             = SHAKE_STEP_MM * STEPS_PER_SIDE; // 0.04 mm

  // Very low speed to be quiet
  constexpr float SHAKE_FEED_MM_S    = 1.0f;  // 1 mm/s

  const float old_feedrate_mm_s = motion.feedrate_mm_s;

  // Optional: lower acceleration only for Z while shaking
  const float old_z_accel = planner.settings.max_acceleration_mm_per_s2[Z_AXIS];
  planner.settings.max_acceleration_mm_per_s2[Z_AXIS] = 20.0f; // adjust as needed

  planner.synchronize();           // Ensure nothing is pending
  motion.feedrate_mm_s = SHAKE_FEED_MM_S; // Set smooth feedrate

  for (uint8_t i = 0; i < times; ++i) {
    // Move up a bit
    motion.position[Z_AXIS] = z0 + AMP_MM;
    motion.goto_current_position();

    // Return to original position
    motion.position[Z_AXIS] = z0;
    motion.goto_current_position();
  }

  planner.synchronize(); // Execute the entire sequence at once

  // Restore parameters
  planner.settings.max_acceleration_mm_per_s2[Z_AXIS] = old_z_accel;
  motion.feedrate_mm_s = old_feedrate_mm_s;
}


/*
 *Function Name: calMinZ()
 *Purpose: Calculate the corresponding z-axis height based on the pressure value in the pressure queue after triggering
 *Params: None
 *Return: None
 */
void ProbeAcq::calMinZ()
{
  double *valP_t = &this->valP[PI_COUNT]; // rock_ does not start with *2, and the array is out of bounds using 20230204

  // 1. Filter rock
  Filters::tFilter(this->valP, PI_COUNT * 2);
  Filters::hFilter(this->valP, PI_COUNT * 2, RC_CUTE_FRQ, 80);
  Filters::lFilter(this->valP, PI_COUNT * 2, LFILTER_K1_NEW);

#if ENABLED(SHOW_MSG)
  double *posZ_t = &this->posZ[PI_COUNT];
  PRINTF("%s", "\nx=[");
  FOR_LOOP_TIMES(i, 0, PI_COUNT, PRINTF((i == (PI_COUNT - 1) ? "%s]\n\n" : "%s,"), getStr(posZ_t[i])));
  PRINTF("%s", "y=[");
  FOR_LOOP_TIMES(i, 0, PI_COUNT, PRINTF((i == (PI_COUNT - 1) ? "%s]\n\n" : "%s,"), getStr(valP_t[i])));
#endif

  // 3. Normalize data to facilitate processing
  double valMin = +0x00FFFFFF, valMax = -0x00FFFFFF;
  ARY_MIN(valMin, valP_t, PI_COUNT);
  ARY_MAX(valMax, valP_t, PI_COUNT);
  FOR_LOOP_TIMES(i, 0, PI_COUNT, { valP_t[i] = (valP_t[i] - valMin) / (valMax - valMin); });

  // 4. Rotate (slope remove) and find earliest trigger
  double angle = atan((valP_t[PI_COUNT - 1] - valP_t[0]) / PI_COUNT);
  double sinAngle = sin(-angle), cosAngle = cos(-angle);
  FOR_LOOP_TIMES(i, 0, PI_COUNT, valP_t[i] = (i - 0) * sinAngle + (valP_t[i] - 0) * cosAngle + 0);

  // 5. Find minimum index
  valMin = +0x00FFFFFF;
  ARY_MIN_INDEX(valMin, this->outIndex, valP_t, PI_COUNT);
  this->outVal_mm = posZ[this->outIndex + PI_COUNT];
#if ENABLED(SHOW_MSG)
  PRINTF("***CalZ Idx=%d, Z=%s***\n", this->outIndex, getStr(this->outVal_mm));
#endif
}

/*
 *Function Name: checkTrigger()
 *Purpose: Trigger status detection, used to detect whether the nozzle is in normal contact with the pressure sensor
 *Return: (bool) true=Trigger detected; false=Trigger condition not met.
 */
bool ProbeAcq::checkTrigger() {
  // We use a filtered copy (as before) for stability,
  // but the final criterion is simpler and with fewer restrictions.
  static double vp_t[PI_COUNT * 2] = {0};
  static double *valP_t = &vp_t[PI_COUNT];

  // Copy and filters (same as before)
  FOR_LOOP_TIMES(i, 0, PI_COUNT * 2, vp_t[i] = this->valP[i]);
  Filters::tFilter(vp_t, PI_COUNT * 2);
  Filters::hFilter(vp_t, PI_COUNT * 2, RC_CUTE_FRQ, 80);
  Filters::lFilter(vp_t, PI_COUNT * 2, LFILTER_K1_NEW);

  // 1) We do not treat “reaching the minimum Z” as a trigger.
  //    The boundary cut is handled by the loop in probePointByStep().
  //    Here we only detect a REAL contact.
  //    (No return here.)

  // 2) Sustained overpressure => stop for safety (count it as a late trigger).
  const int iA = PI_COUNT - 1, iB = PI_COUNT - 2, iC = PI_COUNT - 3;
  if (abs(valP_t[iA]) > this->maxHold && abs(valP_t[iB]) > this->maxHold && abs(valP_t[iC]) > this->maxHold)
    return true;

  // 3) Insufficient data
  if (this->valP[0] == 0) return false;

  // 4) Three last crescents
  if (!(valP_t[iA] > valP_t[iB] && valP_t[iB] > valP_t[iC])) return false;

  // 5) Minimum threshold (more direct and less strict)
  //    We ask that the last one pass the threshold and that the previous ones show “rise”.
  if (abs(valP_t[iA]) < this->minHold) return false;

  // 6) Extra gentle cumulative slope criterion:
  //    sufficient increase compared to 3 samples ago.
  if ((valP_t[iA] - valP_t[iC]) < (this->minHold * 0.25)) return false;

  return true;
}

/*
 *Function Name: probePointByStep()
 *Purpose: Single step method measurement and return measurement results.
 *Params: None
 *Return: (ProbeAcq) this pointer
 */
ProbeAcq* ProbeAcq::probePointByStep() {
  this->outIndex  = PI_COUNT - 1;
  this->outVal_mm = 0;

  // 0) Mover a base XY y Z
  DO_BLOCKING_MOVE_TO_XY(this->basePos_mm.x, this->basePos_mm.y, this->baseSpdXY_mm_s);
  DO_BLOCKING_MOVE_TO_Z (this->basePos_mm.z, this->baseSpdZ_mm_s);

  // 1) Small vibration
  // {
  //   const float z0 = motion.position[Z_AXIS];
  //   const float ampZ = 0.20f;
  //   DO_BLOCKING_MOVE_TO_Z(z0 + ampZ, 120);
  //   DO_BLOCKING_MOVE_TO_Z(z0,        120);
  // }

  // 2) Fast Baseline HX711
  int unfitAvgVal = 0;
  {
    const uint8_t S = 8;
    long acc = 0;
    FOR_LOOP_TIMES(i, 0, S, { acc += this->hx711.getVal(false); MARLIN_CORE_IDLE(); });
    unfitAvgVal = (int)(acc / (long)S);
  }

  // 3) Allow negative Z during search
  #if ENABLED(SOFT_ENDSTOPS)
    extern bool soft_endstops_enabled;
    const bool prev_soft = soft_endstops_enabled;
    soft_endstops_enabled = false;   // = M211 S0
  #endif

  // 4) Init colas
  FOR_LOOP_TIMES(i, 0, PI_COUNT * 2, { this->valP[i] = 0; this->posZ[i] = 0; });

  // 5) Step descent (safer: small step and shallow limit)
  const float step_mm = this->step_mm;          // typical 0.02..0.03
  const float z_limit = this->minZ_mm;          // e.g. -3.0 (see clamp in probeTimes)
  float relZ = 0.0f;

  while (relZ > z_limit) {
    // Step
    DO_BLOCKING_MOVE_TO_Z(motion.position[Z_AXIS] - step_mm, max(2.0f, this->baseSpdZ_mm_s));
    relZ = motion.position[Z_AXIS] - this->basePos_mm.z;

    // Measurement
    const int nowVal = this->hx711.getVal(false);
    FOR_LOOP_TIMES(i, 0, PI_COUNT * 2 - 1, this->valP[i] = this->valP[i + 1]);
    FOR_LOOP_TIMES(i, 0, PI_COUNT * 2 - 1, this->posZ[i] = this->posZ[i + 1]);
    this->valP[PI_COUNT * 2 - 1] = nowVal - unfitAvgVal;
    this->posZ[PI_COUNT * 2 - 1] = relZ;

    // ¿trigger real?
    if (checkTrigger()) { calMinZ(); break; }

    // Have we reached the travel limit? -> Clean ABORT (without trigger)
    if (relZ <= z_limit) break;

    MARLIN_CORE_IDLE();
  }

  // 6) Restore soft-endstops
  #if ENABLED(SOFT_ENDSTOPS)
    soft_endstops_enabled = prev_soft;     // = M211 S1
  #endif

  // Note: if there was no trigger, outVal_mm remains 0 (you filter it above with your is_valid_offset)
  return this;
}
/*
 *Function Name: clearByBed(xyz_float_t basePos_mm, float norm, float minTemp, float maxTemp)
 */
bool clearByBed(xyz_float_t startPos, xyz_float_t endPos, float minTemp, float maxTemp)
{
  ProbeAcq pa;
  pa.hx711.init(HX711_SCK_PIN, HX711_SDO_PIN);
  DO_BLOCKING_MOVE_TO_Z(startPos.z, 5);
  DO_BLOCKING_MOVE_TO_XY(startPos.x, startPos.y - 10, 50);
  Popup_Window_Height(Nozz_Hot);
  SET_HOTEND_TEMP(maxTemp, 0);
  SET_BED_TEMP(60);
  WAIT_HOTEND_TEMP(60 * 5 * 1000, 5);
  WAIT_BED_TEMP(60 * 5 * 1000, 2);
  Popup_Window_Height(Nozz_Clear);
  In_out_feedtock_level(LEVEL_DISTANCE,FEEDING_DEF_SPEED,false);
  DO_BLOCKING_MOVE_TO_XY(startPos.x, startPos.y, 50);
  float start_mm = ProbeAcq::probeTimes(3, startPos, 0.03, -10, 0.2, MIN_HOLD, MAX_HOLD / 2);
  float end_mm   = ProbeAcq::probeTimes(3, endPos,   0.03, -10, 0.2, MIN_HOLD, MAX_HOLD / 2);
  startPos.z = start_mm; endPos.z = end_mm;
  DO_BLOCKING_MOVE_TO_XYZ(startPos.x, startPos.y + 3, startPos.z, 50);
  DO_BLOCKING_MOVE_TO_XYZ(endPos.x, endPos.y - 3, endPos.z - 0.1, 5);
  endPos.x -= 10; endPos.y -= 10;
  DO_BLOCKING_MOVE_TO_XYZ(endPos.x, endPos.y, endPos.z - 0.1, 5);
  RUN_AND_WAIT_GCODE_CMD("G28 Z", true);
  return true;
}

/*
 *Function Name: probeByPress(xyz_float_t basePos_mm, float*outZ)
 */
bool probeByPress(xyz_float_t basePos_mm, float *outZ)
{
  float outZ_mm[3] = {0};
  FOR_LOOP_TIMES(i, 0, 3, outZ_mm[i] = ProbeAcq::probeTimes(0, basePos_mm, 0.02, -10, 0, MIN_HOLD, MAX_HOLD));
  ARY_SORT(outZ_mm, 3);
#if ENABLED(SHOW_MSG)
  PRINTF("\n***PROBE BY PRESS: z=%s, zs={%s, %s, %s}***\n", getStr(outZ_mm[1]), getStr(outZ_mm[0]), getStr(outZ_mm[1]), getStr(outZ_mm[2]));
#endif
  *outZ = outZ_mm[1];
  PRINTF("\n***PROBE BY PRESS: press_z=%s***\n", getStr(*outZ));
  return true;
}

/*
 *Function Name: probeByTouch(xyz_float_t rdyPos_mm, float*outZ)
 */
bool probeByTouch(xyz_float_t rdyPos_mm, float *outZ)
{
  ProbeAcq pa;
  pa.shakeZAxis(20);
  xyz_float_t touchOftPos = CRTOUCH_OFT_POS;
  int oldNozTmp = GET_NOZZLE_TAR_TEMP(0);
  int oldBedTmp = GET_BED_TAR_TEMP();

  DO_BLOCKING_MOVE_TO_Z(rdyPos_mm.z, 5);
  DO_BLOCKING_MOVE_TO_XY(rdyPos_mm.x - touchOftPos.x, rdyPos_mm.y - touchOftPos.y, 100);
  *outZ = PROBE_PPINT_BY_TOUCH(rdyPos_mm.x - touchOftPos.x, rdyPos_mm.y - touchOftPos.y);
  PRINTF("\n***PROBE BY TOUCH: touch_z=%s***\n", getStr(*outZ));

  SET_HOTEND_TEMP(oldNozTmp, 0);
  SET_BED_TEMP(oldBedTmp);

  probe.stow();
  return true;
}

/*
 *Function Name: printTestResult(float *zTouch, float *zPress)
 */
void printTestResult(float *zTouch, float *zPress)
{
  static float acqVals[128][3] = {0}; // Save up to 128 sets of measurement data
  static int acqValIndex = 0;

  PRINTF("\n***GET Z OFFSET: zTouch={%s, %s, %s}, zPress={%s, %s, %s}, zOffset={%s, %s, %s}***\n",
         getStr(zTouch[0]), getStr(zTouch[1]), getStr(zTouch[2]), getStr(zPress[0]), getStr(zPress[1]), getStr(zPress[2]),
         getStr(zPress[0] - zTouch[0]), getStr(zPress[1] - zTouch[1]), getStr(zPress[2] - zTouch[2]));

  float zt_avg = 0, zp_avg = 0;
  ARY_AVG(zt_avg, zTouch, 3);
  ARY_AVG(zp_avg, zPress, 3);

  acqVals[acqValIndex][0] = zp_avg;
  acqVals[acqValIndex][1] = zt_avg;
  acqVals[acqValIndex][2] = zp_avg - zt_avg;
  acqValIndex = (acqValIndex >= 127 ? 127 : (acqValIndex + 1));
  FOR_LOOP_TIMES(i, 0, acqValIndex, PRINTF("%d\t%s\t%s\t%s\n", i, getStr(acqVals[i][0]), getStr(acqVals[i][1]), getStr(acqVals[i][2])));
}

// High ounce (one point)
float Hight_One(xyz_float_t pressPos)
{
  float temp_value = 0;
  float zTouch[1] = {0};
  float zPress[1] = {0};

  bool isRunProByPress = true, isRunProByTouch = true;
  SET_BED_LEVE_ENABLE(false);

  CHECK_AND_RUN(isRunProByTouch, {FOR_LOOP_TIMES(i, 0, 1, {probeByTouch(pressPos, &zTouch[0]); pressPos.z = zTouch[0]; })});

  SET_BED_LEVE_ENABLE(false);
  CHECK_AND_RUN(isRunProByPress, FOR_LOOP_TIMES(i, 0, 1, {probeByPress(pressPos, &zPress[0]); zPress[0] += NOZ_TEMP_OFT_MM; }));

  temp_value = (zPress[0] - zTouch[0]);
  printTestResult(zTouch, zPress);
  DO_BLOCKING_MOVE_TO_Z(5, 5);
  return temp_value;
}

// === Variant of Multiple_Hight that accepts an explicit base point ===
static float Multiple_Hight_At(xyz_float_t basePos, bool isRunProByPress, bool isRunProByTouch) {
  // Up to 3 samples per compatibility (NIN is limited to [1..3])
  float zoffset_value[3] = {NAN, NAN, NAN};
  const uint8_t NIN = (ZOFFSET_REPEAT_NIN < 1 ? 1 : (ZOFFSET_REPEAT_NIN > 3 ? 3 : ZOFFSET_REPEAT_NIN));
  const uint8_t NAX = (ZOFFSET_REPEAT_NAX < 1 ? 1 : (ZOFFSET_REPEAT_NAX > 3 ? 3 : ZOFFSET_REPEAT_NAX));

  xyz_float_t pressPos = basePos;

  // Acquire NIN readings
  for (uint8_t k = 0; k < NIN; k++) {
    pressPos.y = basePos.y - (k * 5);     
    zoffset_value[k] = Hight_One(pressPos);
    PRINTF("\n***OUTPUT_ZOFFSET(@[%s,%s]): zOffset=%s***\n",getStr(pressPos.x), getStr(pressPos.y), getStr(zoffset_value[k]));
    // RUN_AND_WAIT_GCODE_CMD("G28", true);
  }

  // Simple case: NIN == 1 → return that reading as is
  if (NIN == 1) {
    return zoffset_value[0];
  }


  const float a0 = zoffset_value[0];
  const float a1 = zoffset_value[1];
  const float cmp01 = fabsf(a0) - fabsf(a1);

  if (fabsf(cmp01) <= ZOFFSET_COMPARE) {
    // Simple average of the two
    return 0.5f * (a0 + a1);
  }

  // If the first two differ more than the threshold and there is permission for a third, take a third
  if (NAX >= 3) {
    // third “additional” reading
    pressPos.y = basePos.y - ((2 - 2) * 5); 
    zoffset_value[2] = Hight_One(pressPos);
    PRINTF("\n***OUTPUT_ZOFFSET(@[%s,%s] 3rd): zOffset=%s***\n",getStr(pressPos.x), getStr(pressPos.y), getStr(zoffset_value[2]));

    const float a2 = zoffset_value[2];
    const float d20 = fabsf(a2) - fabsf(a0);
    const float d21 = fabsf(a2) - fabsf(a1);

    // If the third is not “close” to any, we are left with the most “stable” between a0/a1:
    if (fabsf(d20) > ZOFFSET_COMPARE && fabsf(d21) > ZOFFSET_COMPARE) {
      return (fabsf(a0) < fabsf(a1)) ? a0 : a1;
    }

    // If it is close to one of the two, replace that one and average
    float b0 = a0, b1 = a1;
    if (fabsf(d20) <= ZOFFSET_COMPARE) b0 = a2;
    else                               b1 = a2;

    return 0.5f * (b0 + b1);
  }

  // No third allowed (NAX < 3): take the “shortest/stable” of the first two
  return (fabsf(a0) < fabsf(a1)) ? a0 : a1;
}

// Original Multiple High 
// float Multiple_Hight(bool isRunProByPress, bool isRunProByTouch)
// {
//   float zoffset_value[3] = {0};
//   uint8_t loop_max = 0, loop_num = 0;
//   xyz_float_t pressPos = PRESS_XYZ_POS;
//   float temp_zoffset = 0, temp_zoffset1 = 0, zoffset_avg = 0;

//   for (loop_num = 0; loop_num < ZOFFSET_REPEAT_NIN; loop_num++)
//   {
//     pressPos.y -= (loop_num *5);
//     zoffset_value[loop_num] = Hight_One(pressPos);
//     PRINTF("\n***OUTPUT_ZOFFSET: zOffset=%s***\n", getStr(zoffset_value[loop_num]));
//     RUN_AND_WAIT_GCODE_CMD("G28", true);
//   }
//   temp_zoffset = fabs(zoffset_value[0]) -fabs(zoffset_value[1]);
//   if (fabs(temp_zoffset) <= ZOFFSET_COMPARE)
//   {
//     ARY_AVG(zoffset_avg, zoffset_value, 2);
//     SET_BED_LEVE_ENABLE(true);
//     In_out_feedtock_level(LEVEL_DISTANCE,FEEDING_DEF_SPEED,true);
//     SET_HOTEND_TEMP(140, 0);
//     SET_FAN_SPD(255);
//     WAIT_HOTEND_TEMP(60 *5 *1000, 5);
//     Popup_Window_Height(Nozz_Finish);
//     return zoffset_avg;
//   }
//   else
//   {
//     for (loop_max = 2; loop_max < ZOFFSET_REPEAT_NAX; loop_max++)
//     {
//       pressPos.y -= (loop_max -2) *5;
//       zoffset_value[2] = Hight_One(pressPos);
//       temp_zoffset = fabs(zoffset_value[2]) -fabs(zoffset_value[0]);
//       temp_zoffset1 = fabs(zoffset_value[2]) -fabs(zoffset_value[1]);
//       if ((fabs(temp_zoffset) > ZOFFSET_COMPARE) && (fabs(temp_zoffset1) > ZOFFSET_COMPARE))
//       {
//         continue;
//       }
//       else if ((fabs(temp_zoffset) <= ZOFFSET_COMPARE) || (fabs(temp_zoffset1) <= ZOFFSET_COMPARE))
//       {
//         if ((fabs(temp_zoffset) <= ZOFFSET_COMPARE)) zoffset_value[1] = zoffset_value[2];
//         else                                         zoffset_value[0] = zoffset_value[2];

//         ARY_AVG(zoffset_avg, zoffset_value, 2);
//         SET_BED_LEVE_ENABLE(true);
//         In_out_feedtock_level(LEVEL_DISTANCE,FEEDING_DEF_SPEED,true);
//         SET_HOTEND_TEMP(140, 0);
//         SET_FAN_SPD(255);
//         WAIT_HOTEND_TEMP(60 *5 *1000, 5);
//         Popup_Window_Height(Nozz_Finish);
//         return zoffset_avg;
//       }
//     }
//     if (ZOFFSET_REPEAT_NAX == loop_max)
//     {
//       return zoffset_avg;
//     }
//     return zoffset_avg;
//   }
// }

/*
 *Function Name: getZOffset(float*outOffset)
 *Purpose: measure multiple points and estimate Z offset with robust statistics
 */
bool getZOffset(bool isNozzleClr, bool isRunProByPress, bool isRunProByTouch, float *outOffset)
{
  // The load-cell sampling needs standard stepper motion; FT Motion is restored on exit
  TERN_(FT_MOTION, FTM_DISABLE_IN_SCOPE());
  #if ENABLED(X_ROUTINE_AUTO_OFFSET)
    SERIAL_ECHOLNPGM_P("=== Starting Get Z Offset (5 points, X Routine) ===");
  #elif ENABLED(D_ROUTINE_AUTO_OFFSET)
    SERIAL_ECHOLNPGM_P("=== Starting Get Z Offset (4 points, D Routine) ===");
  #endif
  
  // Preparation
  SET_Z_OFFSET(0, false);
  RUN_AND_WAIT_GCODE_CMD("G28", true);

  // Cleaning (one time, as before)
  xyz_float_t pressPos = PRESS_XYZ_POS;
  xyz_float_t touchOftPos = CRTOUCH_OFT_POS;
  xyz_float_t rdyPos[3] = {{0, 0, HIGHT_UPRAISE_Z}, {0, 0, HIGHT_UPRAISE_Z}, {0, 0, HIGHT_UPRAISE_Z}};
  rdyPos[0].x = rdyPos[2].x = (pressPos.x < (BED_SIZE_X_MM / 2) ? (touchOftPos.x < 0) : (touchOftPos.x > 0)) ? pressPos.x : touchOftPos.x + 10;
  rdyPos[0].x -= 9;
  rdyPos[0].y = rdyPos[1].y = ((pressPos.y < (BED_SIZE_Y_MM / 2) ? (touchOftPos.y < 0) : (touchOftPos.y > 0)) ? pressPos.y : touchOftPos.y + 10);
  rdyPos[0].y = rdyPos[1].y -= 17;
  rdyPos[1].x = rdyPos[0].x + (pressPos.x < (BED_SIZE_X_MM / 2) ? +1 : -1) * BED_SIZE_X_MM / 5;
  rdyPos[2].y = rdyPos[0].y + (pressPos.y < (BED_SIZE_Y_MM / 2) ? +1 : -1) * BED_SIZE_Y_MM / 5;
  rdyPos[2].x = (rdyPos[0].x + (rdyPos[1].x - rdyPos[0].x) / 2);

  xyz_float_t startPos = {CLEAR_NOZZL_START_X, CLEAR_NOZZL_START_Y, 0};
  xyz_float_t endPos   = {CLEAR_NOZZL_END_X,   CLEAR_NOZZL_END_Y,   0};
  CHECK_AND_RUN(isNozzleClr, clearByBed(startPos, endPos, 140, 175));
  Popup_Window_Height(Nozz_Hight);

#if ENABLED(X_ROUTINE_AUTO_OFFSET)
  // Points requested
  const xyz_float_t Probes[5] = {
    {  28,  28, 0},   // Left front
    { 110, 110, 0},   // center approx
    { 180, 180, 0}, //back-right this point is too far from the load cell, could cause damage in the bed disable if needed
    { 180,  28, 0},   // Right front
    {  28, 180, 0},   // Back left
  };

  // Measure each point using the same robust routine (Multiple_Hight_) but centered on the coordinate
  float vals[5] = {0};
  xyz_float_t valid_pts[5] = {};
  uint8_t vcount = 0;

  for (uint8_t i = 0; i < 5; ++i)
  
  {
    float zoff = Multiple_Hight_At(Probes[i], isRunProByPress, isRunProByTouch);
    // Filters invalid values ​​(≈0, out of range)
    if (is_valid_offset(zoff)) {
      vals[vcount++] = zoff;
      valid_pts[vcount - 1] = Probes[i];
      PRINTF("***POINT[%d @ %s,%s] => zOffset=%s (kept)\n", i, getStr(Probes[i].x), getStr(Probes[i].y), getStr(zoff));
    } else {
      PRINTF("***POINT[%d @ %s,%s] => zOffset=%s (discarded)\n", i, getStr(Probes[i].x), getStr(Probes[i].y), getStr(zoff));
    }
    // RUN_AND_WAIT_GCODE_CMD("G28", true);  // not needed between points
  }

  if (vcount == 0) {
    SERIAL_ECHOLNPGM_P("No valid readings across 5 points.");
    return false;
  }

  // Final robust estimate (median fallback internal)
#elif ENABLED(D_ROUTINE_AUTO_OFFSET)
  // Points requested
  const xyz_float_t Probes[4] = {
    {  28,  28, 0},   // Left front
    { 110, 110, 0},   // center approx
    { 180,  28, 0},   // Right front
    {  28, 180, 0},   // Back left
  };

  // Measure each point using the same robust routine (Multiple_Hight_) but centered on the coordinate
  float vals[4] = {0};
  xyz_float_t valid_pts[4] = {};
  uint8_t vcount = 0;

  for (uint8_t i = 0; i < 4; ++i)
  
  {
    float zoff = Multiple_Hight_At(Probes[i], isRunProByPress, isRunProByTouch);
    // Filters invalid values ​​(≈0, out of range)
    if (is_valid_offset(zoff)) {
      vals[vcount++] = zoff;
      valid_pts[vcount - 1] = Probes[i];
      PRINTF("***POINT[%d @ %s,%s] => zOffset=%s (kept)\n", i, getStr(Probes[i].x), getStr(Probes[i].y), getStr(zoff));
    } else {
      PRINTF("***POINT[%d @ %s,%s] => zOffset=%s (discarded)\n", i, getStr(Probes[i].x), getStr(Probes[i].y), getStr(zoff));
    }
    // RUN_AND_WAIT_GCODE_CMD("G28", true);  // not needed between points
  }

  if (vcount == 0) {
    SERIAL_ECHOLNPGM_P("No valid readings across 4 points.");
    return false;
  }

  // Final robust estimate (median fallback internal)

#endif

  *outOffset = robust_offset_from_points(vals, valid_pts, vcount);

#if ENABLED(X_ROUTINE_AUTO_OFFSET)
    SERIAL_ECHOLNPGM_P("=== Z Offset Measurement Completed (5 points) ===");
    SERIAL_ECHOLNPGM("OUTPUT_ZOFFSET(5pt ROBUST): ", *outOffset);
#elif ENABLED(D_ROUTINE_AUTO_OFFSET)
    SERIAL_ECHOLNPGM_P("=== Z Offset Measurement Completed (4 points) ===");
    SERIAL_ECHOLNPGM("OUTPUT_ZOFFSET(4pt ROBUST): ", *outOffset);
#endif
 
if ((*outOffset > ZOFFSET_VALUE_MAX) || (*outOffset < ZOFFSET_VALUE_MIN))
  {
    SERIAL_ECHOLNPGM_P("=== Z Offset Measurement Failed: Out of Range ===");
    return false;
  }

  SET_Z_OFFSET(*outOffset, true);
  return (isRunProByPress && isRunProByTouch);
}

#endif
