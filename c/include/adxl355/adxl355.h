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
typedef enum {
    ADXL355_OK             = 0,
    ADXL355_ERR_NULL       = -1,
    ADXL355_ERR_BUS        = -2,
    ADXL355_ERR_TIMEOUT    = -3,
    ADXL355_ERR_INVALID_ARG = -4,
    ADXL355_ERR_BAD_DEVICE = -5,
    ADXL355_ERR_NOT_READY  = -6,
    ADXL355_ERR_UNSUPPORTED = -7,
    ADXL355_ERR_STATE       = -8
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

/**
 * Transport abstraction – function-pointer bus interface.
 *
 * All bus operations must return 0 only after transferring the complete
 * requested length, and non-zero on partial transfer or bus failure.
 * The driver does NOT own the context pointer; the caller must ensure it
 * remains valid for the lifetime of the adxl355_t object.
 */
typedef struct {
    /**
     * Read `len` bytes starting at `reg` into `data`.
     * Must return 0 on success, non-zero on bus error.
     */
    int (*read)(void *ctx, uint8_t reg, uint8_t *data, size_t len);

    /**
     * Write `len` bytes from `data` starting at `reg`.
     * Must return 0 on success, non-zero on bus error.
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

/** Return a human-readable string for a status code. */
const char *adxl355_status_string(adxl355_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* ADXL355_H */
