#ifndef ADXL355_TEST_MOCK_BUS_H
#define ADXL355_TEST_MOCK_BUS_H

#include "adxl355/adxl355.h"
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Mock bus for testing ADXL355 driver without real hardware.
 *
 * Simulates a register file. Read/write operations go into the map.
 * You can pre-set register values (e.g., for probe simulation).
 */

/** Maximum number of registers the mock can track. */
#define ADXL355_MOCK_NUM_REGS 128

/** Call log entry for verifying driver behaviour. */
typedef struct {
    bool     is_write;
    uint8_t  reg;
    uint8_t  data;
    size_t   len;
} adxl355_mock_call_t;

/** Maximum number of logged calls. */
#define ADXL355_MOCK_MAX_CALLS 256

typedef struct {
    uint8_t  regs[ADXL355_MOCK_NUM_REGS];       /**< Simulated register file. */
    int      force_error;                        /**< If non-zero, every bus call fails. */
    int      force_read_error;                   /**< If non-zero, reads fail. */
    int      force_write_error;                  /**< If non-zero, writes fail. */
    int      fail_read_reg;                      /**< Register-specific read failure; -1 disables. */
    int      fail_write_reg;                     /**< Register-specific write failure; -1 disables. */
    size_t   fail_write_occurrence;              /**< 1-based matching write to fail; 0 fails all. */
    size_t   fail_write_matches;                 /**< Matching write attempts observed. */
    size_t   call_count;                         /**< Number of recorded successful bus calls. */
    adxl355_mock_call_t calls[ADXL355_MOCK_MAX_CALLS]; /**< Call history. */
    void    *delay_ctx;                          /**< Context for delay callback (unused). */
} adxl355_mock_bus_t;

/** Initialise the mock bus (zero everything). */
void adxl355_mock_bus_init(adxl355_mock_bus_t *mock);

/** Pre-set the identity registers so that probe() succeeds. */
void adxl355_mock_bus_set_identity_ok(adxl355_mock_bus_t *mock);

/** Pre-set fake acceleration data (raw 20-bit per axis). */
void adxl355_mock_bus_set_xyz_raw(adxl355_mock_bus_t *mock,
                                  int32_t raw_x, int32_t raw_y, int32_t raw_z);

/** Return the adxl355_bus_t interface wrapping this mock. */
adxl355_bus_t adxl355_mock_bus_get_interface(adxl355_mock_bus_t *mock);

#ifdef __cplusplus
}
#endif

#endif /* ADXL355_TEST_MOCK_BUS_H */
