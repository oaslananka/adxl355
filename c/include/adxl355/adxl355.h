#ifndef ADXL355_H
#define ADXL355_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#include "adxl355_registers.h"
#include "adxl355_version.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------------------------------------------------------------------
 * Error / Status codes
 * --------------------------------------------------------------------------- */
/** Stable status values returned by the public C API. */
typedef enum {
    ADXL355_OK              = 0,   /**< Operation completed successfully. */
    ADXL355_ERR_NULL        = -1,  /**< A required pointer was NULL. */
    ADXL355_ERR_BUS         = -2,  /**< Transport failed or returned a non-exact length. */
    ADXL355_ERR_TIMEOUT     = -3,  /**< A bounded ready/poll operation timed out. */
    ADXL355_ERR_INVALID_ARG = -4,  /**< A value or enum encoding was invalid. */
    ADXL355_ERR_BAD_DEVICE  = -5,  /**< Identity registers did not match ADXL355. */
    ADXL355_ERR_NOT_READY   = -6,  /**< A coherent sample was unavailable. */
    ADXL355_ERR_UNSUPPORTED = -7,  /**< The requested operation is not implemented. */
    ADXL355_ERR_STATE       = -8,  /**< Probe or another required state transition is missing. */
    ADXL355_ERR_THRESHOLD   = -9,  /**< Caller-owned self-test thresholds were violated. */
    ADXL355_ERR_RESTORE     = -10  /**< Exact register restoration failed. */
} adxl355_status_t;

/* ---------------------------------------------------------------------------
 * Enums
 * --------------------------------------------------------------------------- */
/**
 * Acceleration range selection.
 * Register values (datasheet Rev.D, Table 42): 0x01=2g, 0x02=4g, 0x03=8g
 */
typedef enum {
    ADXL355_RANGE_2G = 0x01,
    ADXL355_RANGE_4G = 0x02,
    ADXL355_RANGE_8G = 0x03
} adxl355_range_t;

/**
 * Power mode selection.
 * Datasheet Rev.D, Table 43: bit 0 = 1 => standby, bit 0 = 0 => measurement.
 */
typedef enum {
    ADXL355_POWER_STANDBY      = 1,
    ADXL355_POWER_MEASUREMENT  = 0
} adxl355_power_mode_t;


/** Axis selection for offset calibration registers. */
typedef enum {
    ADXL355_AXIS_X = 0,
    ADXL355_AXIS_Y = 1,
    ADXL355_AXIS_Z = 2
} adxl355_axis_t;

/** FILTER register output-data-rate encodings, from 4000 Hz through 3.906 Hz. */
typedef enum {
    ADXL355_ODR_4000_HZ   = 0,
    ADXL355_ODR_2000_HZ   = 1,
    ADXL355_ODR_1000_HZ   = 2,
    ADXL355_ODR_500_HZ    = 3,
    ADXL355_ODR_250_HZ    = 4,
    ADXL355_ODR_125_HZ    = 5,
    ADXL355_ODR_62_5_HZ   = 6,
    ADXL355_ODR_31_25_HZ  = 7,
    ADXL355_ODR_15_625_HZ = 8,
    ADXL355_ODR_7_813_HZ  = 9,
    ADXL355_ODR_3_906_HZ  = 10
} adxl355_odr_t;

/* ---------------------------------------------------------------------------
 * Data structures
 * --------------------------------------------------------------------------- */

/** Raw 20-bit acceleration data (already decoded to int32). */
typedef struct {
    int32_t x;
    int32_t y;
    int32_t z;
} adxl355_raw_xyz_t;

/** Acceleration in floating-point units. */
typedef struct {
    float x;
    float y;
    float z;
} adxl355_float_xyz_t;

/** Optional caller-owned absolute-delta acceptance policy in g. */
typedef struct {
    adxl355_float_xyz_t min_abs_delta_g;
    adxl355_float_xyz_t max_abs_delta_g;
} adxl355_self_test_thresholds_t;

/** Bounded self-test acquisition configuration. */
typedef struct {
    uint16_t sample_count;
    uint16_t settle_samples;
    uint16_t max_ready_polls;
    uint16_t poll_delay_ms;
    bool enforce_thresholds;
    adxl355_self_test_thresholds_t thresholds;
} adxl355_self_test_config_t;

/** Measured self-test response; threshold status is caller-policy dependent. */
typedef struct {
    adxl355_float_xyz_t baseline_g;
    adxl355_float_xyz_t stimulated_g;
    adxl355_float_xyz_t delta_g;
    adxl355_float_xyz_t abs_delta_g;
    uint16_t samples;
    bool thresholds_evaluated;
    bool thresholds_passed;
} adxl355_self_test_result_t;

/**
 * Transport abstraction – function-pointer bus interface.
 *
 * Read and write callbacks return the exact number of bytes transferred on
 * success and a negative value on bus failure. The driver accepts success only
 * when the returned count equals the requested length; zero, partial, and
 * overlong counts are reported as ADXL355_ERR_BUS.
 * The driver does NOT own the context pointer; the caller must ensure it
 * remains valid for the lifetime of the adxl355_t object.
 */
typedef struct {
    /**
     * Read `len` bytes starting at `reg` into `data`.
     * Return exactly `len` on success or a negative value on bus failure.
     * Returning zero, a partial count, or a count greater than `len` violates
     * the contract and is detected as ADXL355_ERR_BUS.
     */
    int (*read)(void *ctx, uint8_t reg, uint8_t *data, size_t len);

    /**
     * Write `len` bytes from `data` starting at `reg`.
     * Return exactly `len` on success or a negative value on bus failure.
     * Partial and overlong counts are rejected as ADXL355_ERR_BUS.
     */
    int (*write)(void *ctx, uint8_t reg, const uint8_t *data, size_t len);

    /**
     * Blocking delay in milliseconds.
     * May be NULL if the application never calls functions that require
     * a delay (e.g., software reset).
     */
    void (*delay_ms)(void *ctx, uint32_t ms);

    /** Opaque context passed to every bus callback. */
    void *ctx;
} adxl355_bus_t;

/** Main device handle – initialised via adxl355_init(). */
typedef struct {
    adxl355_bus_t   bus;          /**< Bus abstraction (copied) */
    adxl355_range_t range;        /**< Current range setting */
    bool            initialized;  /**< Set after successful init+probe */
} adxl355_t;

/* ---------------------------------------------------------------------------
 * Scaling constants
 * --------------------------------------------------------------------------- */

/** ±2 g scale: g-per-LSB (nominal). @warning Verify against datasheet. */
#define ADXL355_SCALE_2G_G_PER_LSB   0.0000039f

/** ±4 g scale: g-per-LSB (nominal). @warning Verify against datasheet. */
#define ADXL355_SCALE_4G_G_PER_LSB   0.0000078f

/** ±8 g scale: g-per-LSB (nominal). @warning Verify against datasheet. */
#define ADXL355_SCALE_8G_G_PER_LSB   0.0000156f

/** Standard gravity in m/s². */
#define ADXL355_STANDARD_GRAVITY_M_S2  9.80665f

/* ---------------------------------------------------------------------------
 * Core API
 * --------------------------------------------------------------------------- */

/**
 * Initialise a device handle.
 *
 * Copies the bus abstraction and zeros internal state. Does NOT touch the
 * hardware; call adxl355_probe() to verify connectivity.
 *
 * @param dev  Pointer to an uninitialised adxl355_t.
 * @param bus  Bus abstraction. The contents are copied.
 * @return ADXL355_OK on success, ADXL355_ERR_NULL if dev or bus is NULL.
 */
adxl355_status_t adxl355_init(adxl355_t *dev, const adxl355_bus_t *bus);

/**
 * Probe for the ADXL355 by reading the identity registers.
 *
 * On success the device range cache is synchronized from the RANGE register,
 * the device is placed into standby mode without changing unrelated POWER_CTL
 * bits, and `dev->initialized` is set to true. A failed probe leaves the device
 * handle uninitialized.
 *
 * @param dev  Initialised device handle.
 * @return ADXL355_OK if all three ID registers match,
 *         ADXL355_ERR_BAD_DEVICE if they don't,
 *         ADXL355_ERR_INVALID_ARG for reserved RANGE encoding,
 *         ADXL355_ERR_BUS on bus error.
 */
adxl355_status_t adxl355_probe(adxl355_t *dev);

/**
 * Perform a software reset.
 *
 * After reset the device defaults to standby mode with ±2g range.
 * The caller should wait at least 1 ms after reset before further
 * communication.
 *
 * @param dev  Initialised device handle.
 * @return ADXL355_OK, ADXL355_ERR_STATE before a successful probe, or another error code.
 */
adxl355_status_t adxl355_reset(adxl355_t *dev);

/**
 * Set the acceleration range.
 *
 * The driver requires a successful probe. If the device is measuring, it
 * temporarily enters standby, updates only RANGE_SEL while preserving I2C_HS,
 * INT_POL, and reserved bits, then restores the original POWER_CTL value. The
 * cached range is updated immediately after a successful RANGE write so it
 * remains consistent even if restoring measurement mode fails.
 *
 * @param dev   Initialised device handle.
 * @param range Desired range.
 * @return ADXL355_OK, ADXL355_ERR_STATE before probe, ADXL355_ERR_BUS on
 *         transition/configuration/restore failure, or an argument error.
 */
adxl355_status_t adxl355_set_range(adxl355_t *dev, adxl355_range_t range);

/**
 * Read the currently configured range.
 *
 * This reads from the device register, not the cached value.
 *
 * @param dev    Initialised device handle.
 * @param[out] range  Current range setting.
 * @return ADXL355_OK or error code.
 */
adxl355_status_t adxl355_get_range(adxl355_t *dev, adxl355_range_t *range);

/**
 * Set the power mode (standby / measurement).
 *
 * @param dev  Initialised device handle.
 * @param mode Desired power mode.
 * @return ADXL355_OK or error code.
 */
adxl355_status_t adxl355_set_power_mode(adxl355_t *dev, adxl355_power_mode_t mode);

/**
 * Set the output data rate / filter corner.
 *
 * If measurement mode is active, the driver temporarily enters standby and
 * restores the exact original POWER_CTL value after updating FILTER.
 *
 * @param dev Initialised and probed device handle.
 * @param odr Desired ODR value.
 * @return ADXL355_OK or error code.
 */
adxl355_status_t adxl355_set_odr(adxl355_t *dev, adxl355_odr_t odr);


/* ---------------------------------------------------------------------------
 * Offset calibration
 * --------------------------------------------------------------------------- */

/**
 * Read one signed 16-bit hardware offset value.
 *
 * Offset bits match acceleration data bits [19:4], so one offset count equals
 * 16 raw acceleration LSB. A successful probe is required.
 *
 * @param dev Initialised and probed device handle.
 * @param axis Axis whose offset register pair will be read.
 * @param[out] offset Signed register value; modified only on success.
 * @return ADXL355_OK, ADXL355_ERR_STATE before probe, ADXL355_ERR_INVALID_ARG
 *         for an invalid axis, or ADXL355_ERR_BUS on an exact-length failure.
 */
adxl355_status_t adxl355_read_offset(adxl355_t *dev, adxl355_axis_t axis, int16_t *offset);

/**
 * Write one signed 16-bit hardware offset value using one two-byte transfer.
 *
 * The driver temporarily enters standby when needed and restores the exact
 * original POWER_CTL value after the write. The offset is volatile device
 * state and is reset by power cycle or software reset.
 *
 * @param dev Initialised and probed device handle.
 * @param axis Axis whose offset register pair will be written.
 * @param offset Signed two's-complement offset value.
 * @return ADXL355_OK, ADXL355_ERR_STATE before probe, ADXL355_ERR_INVALID_ARG
 *         for an invalid axis, or ADXL355_ERR_BUS if write/restore fails.
 */
adxl355_status_t adxl355_write_offset(adxl355_t *dev, adxl355_axis_t axis, int16_t offset);


/* ---------------------------------------------------------------------------
 * Electrostatic self-test
 * --------------------------------------------------------------------------- */

/**
 * Fill a bounded acquisition configuration without normative thresholds.
 *
 * @param[out] config Configuration to initialize.
 * @return ADXL355_OK or ADXL355_ERR_NULL.
 */
adxl355_status_t adxl355_self_test_config_default(adxl355_self_test_config_t *config);

/**
 * Run the Rev.D ST1+ST2 electrostatic response sequence.
 *
 * The implementation temporarily uses ±2 g, 125 Hz, and measurement mode,
 * collects baseline and stimulated means, then restores SELF_TEST, RANGE,
 * FILTER, cached range, and POWER_CTL exactly. A restore failure takes
 * precedence over the operation status. If caller thresholds are enabled and
 * violated, the result remains populated and ADXL355_ERR_THRESHOLD is returned.
 *
 * @param dev Initialised and probed device handle.
 * @param config Optional bounded configuration; NULL selects defaults.
 * @param[out] result Measured response and caller-policy result.
 * @return ADXL355_OK, ADXL355_ERR_THRESHOLD, ADXL355_ERR_TIMEOUT,
 *         ADXL355_ERR_RESTORE, or another validated driver error.
 */
adxl355_status_t adxl355_run_self_test(adxl355_t *dev,
                                        const adxl355_self_test_config_t *config,
                                        adxl355_self_test_result_t *result);

/* ---------------------------------------------------------------------------
 * Data readout
 * --------------------------------------------------------------------------- */

/**
 * Read raw 20-bit acceleration data for all three axes.
 *
 * The returned values are sign-extended to int32.
 *
 * @param dev Initialised and probed device handle.
 * @param[out] out Raw XYZ data structure.
 * @return ADXL355_OK or error code.
 */
adxl355_status_t adxl355_read_raw(adxl355_t *dev, adxl355_raw_xyz_t *out);

/**
 * Read acceleration in g (gravity multiples).
 *
 * @param dev Initialised and probed device handle.
 * @param[out] out Acceleration in g.
 * @return ADXL355_OK or error code.
 */
adxl355_status_t adxl355_read_g(adxl355_t *dev, adxl355_float_xyz_t *out);

/**
 * Read acceleration in m/s².
 *
 * @param dev Initialised and probed device handle.
 * @param[out] out Acceleration in m/s².
 * @return ADXL355_OK or error code.
 */
adxl355_status_t adxl355_read_mps2(adxl355_t *dev, adxl355_float_xyz_t *out);

/**
 * Read the coherent 12-bit unsigned temperature value.
 *
 * The driver performs a two-byte TEMP2/TEMP1 burst, re-reads TEMP2, masks
 * reserved TEMP2 bits 7:4, and retries up to three times if the high data
 * nibble changed across the sample. The output is modified only on success.
 *
 * @param dev Initialised device handle.
 * @param[out] out Raw temperature in the range 0..4095.
 * @return ADXL355_OK, ADXL355_ERR_BUS on partial/bus reads, or
 *         ADXL355_ERR_NOT_READY if no coherent sample is obtained.
 */
adxl355_status_t adxl355_read_temperature_raw(adxl355_t *dev, int16_t *out);

/**
 * Read temperature in degrees Celsius.
 *
 * Datasheet Rev.D nominal conversion:
 *   T(°C) = 25.0 + (raw_temp - 1885.0) / -9.05
 *
 * @param dev Initialised device handle.
 * @param[out] out Temperature in °C.
 * @return ADXL355_OK or error code.
 */
adxl355_status_t adxl355_read_temperature_c(adxl355_t *dev, float *out);

/**
 * Read the status register.
 *
 * @param dev    Initialised device handle.
 * @param[out] status Raw status register value.
 * @return ADXL355_OK or error code.
 */
adxl355_status_t adxl355_read_status(adxl355_t *dev, uint8_t *status);

/* ---------------------------------------------------------------------------
 * Utility / conversion functions (stateless, reentrant)
 * --------------------------------------------------------------------------- */

/**
 * Decode three bytes into a 20-bit two's complement integer.
 *
 * @param b0 MSB (first byte read from XDATA3 / YDATA3 / ZDATA3).
 * @param b1 Middle byte.
 * @param b2 LSB (last byte).
 * @return Sign-extended 32-bit integer in range [-524288, 524287].
 */
int32_t adxl355_decode_raw20(uint8_t b0, uint8_t b1, uint8_t b2);

/**
 * Convert a decoded 20-bit raw value to g.
 *
 * @param raw   Decoded raw value.
 * @param range Current range setting.
 * @return Acceleration in g.
 */
float adxl355_raw_to_g(int32_t raw, adxl355_range_t range);

/**
 * Convert a decoded 20-bit raw value to m/s².
 *
 * @param raw   Decoded raw value.
 * @param range Current range setting.
 * @return Acceleration in m/s².
 */
float adxl355_raw_to_mps2(int32_t raw, adxl355_range_t range);


/**
 * Calculate a hardware offset from rounded raw acceleration means.
 *
 * Formula: current_offset +
 * round_half_away_from_zero((measured_raw - expected_raw) / 16).
 * Inputs must be valid signed 20-bit acceleration values. When `saturate` is
 * false, a resulting value outside int16_t is rejected. When true, it is clamped.
 *
 * @param measured_raw Rounded measured mean in signed 20-bit raw LSB.
 * @param expected_raw Desired signed 20-bit raw LSB target.
 * @param current_offset Existing signed offset-register value.
 * @param saturate Clamp overflow to int16_t when true; reject it when false.
 * @param[out] offset Calculated offset; modified only on success.
 * @return ADXL355_OK, ADXL355_ERR_NULL, or ADXL355_ERR_INVALID_ARG.
 */
adxl355_status_t adxl355_calculate_offset(int32_t measured_raw,
                                           int32_t expected_raw,
                                           int16_t current_offset,
                                           bool saturate,
                                           int16_t *offset);

/**
 * Return a static human-readable string for a status code.
 *
 * @param status Public status value or an unknown integer cast to the enum.
 * @return Process-lifetime string; never NULL.
 */
const char *adxl355_status_string(adxl355_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* ADXL355_H */
