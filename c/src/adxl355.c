#include "adxl355/adxl355.h"

#include <limits.h>
#include <math.h>
#include <string.h>

enum {
    ADXL355_TEMP2_DATA_MASK = 0x0F,
    ADXL355_TEMP_READ_ATTEMPTS = 3,
};

static const float ADXL355_TEMP_INTERCEPT_LSB = 1885.0f;
static const float ADXL355_TEMP_INTERCEPT_C = 25.0f;
static const float ADXL355_TEMP_SLOPE_LSB_PER_C = -9.05f;

/* ---------------------------------------------------------------------------
 * Internal helpers
 * --------------------------------------------------------------------------- */

static int read_exact(adxl355_t *dev, uint8_t reg, uint8_t *data, size_t len)
{
    if (len > (size_t)INT_MAX) {
        return -1;
    }
    return dev->bus.read(dev->bus.ctx, reg, data, len) == (int)len ? 0 : -1;
}

static int write_exact(adxl355_t *dev, uint8_t reg, const uint8_t *data, size_t len)
{
    if (len > (size_t)INT_MAX) {
        return -1;
    }
    return dev->bus.write(dev->bus.ctx, reg, data, len) == (int)len ? 0 : -1;
}

static inline int read_reg(adxl355_t *dev, uint8_t reg, uint8_t *byte)
{
    return read_exact(dev, reg, byte, 1U);
}

static inline int write_reg(adxl355_t *dev, uint8_t reg, uint8_t byte)
{
    return write_exact(dev, reg, &byte, 1U);
}

typedef struct {
    uint8_t original_power_ctl;
    bool restore_measurement;
} adxl355_config_guard_t;

static uint8_t clear_u8_bits(uint8_t value, uint8_t mask)
{
    return (uint8_t)(value & (uint8_t)(UINT8_MAX ^ mask));
}

static adxl355_status_t require_initialized(const adxl355_t *dev)
{
    return dev->initialized ? ADXL355_OK : ADXL355_ERR_STATE;
}

static adxl355_status_t enter_configuration_standby(
    adxl355_t *dev, adxl355_config_guard_t *guard)
{
    if (read_reg(dev, ADXL355_REG_POWER_CTL, &guard->original_power_ctl) != 0) {
        return ADXL355_ERR_BUS;
    }
    guard->restore_measurement =
        (guard->original_power_ctl & (uint8_t)(1U << ADXL355_POWER_MODE_BIT)) == 0U;
    if (guard->restore_measurement) {
        uint8_t standby = (uint8_t)(guard->original_power_ctl |
                                    (uint8_t)(1U << ADXL355_POWER_MODE_BIT));
        if (write_reg(dev, ADXL355_REG_POWER_CTL, standby) != 0) {
            return ADXL355_ERR_BUS;
        }
    }
    return ADXL355_OK;
}

static adxl355_status_t finish_configuration(
    adxl355_t *dev,
    const adxl355_config_guard_t *guard,
    adxl355_status_t operation_status)
{
    if (guard->restore_measurement &&
        write_reg(dev, ADXL355_REG_POWER_CTL, guard->original_power_ctl) != 0) {
        return ADXL355_ERR_BUS;
    }
    return operation_status;
}


static bool offset_register_for_axis(adxl355_axis_t axis, uint8_t *reg)
{
    switch (axis) {
        case ADXL355_AXIS_X:
            *reg = ADXL355_REG_OFFSET_X_H;
            return true;
        case ADXL355_AXIS_Y:
            *reg = ADXL355_REG_OFFSET_Y_H;
            return true;
        case ADXL355_AXIS_Z:
            *reg = ADXL355_REG_OFFSET_Z_H;
            return true;
        default:
            return false;
    }
}

static bool range_from_register(uint8_t reg, adxl355_range_t *range)
{
    switch (reg & ADXL355_RANGE_SEL_MASK) {
        case ADXL355_RANGE_2G:
            *range = ADXL355_RANGE_2G;
            return true;
        case ADXL355_RANGE_4G:
            *range = ADXL355_RANGE_4G;
            return true;
        case ADXL355_RANGE_8G:
            *range = ADXL355_RANGE_8G;
            return true;
        default:
            return false;
    }
}

/* ---------------------------------------------------------------------------
 * Scale factor lookup
 * --------------------------------------------------------------------------- */
static float range_to_scale_g_per_lsb(adxl355_range_t range)
{
    switch (range) {
        case ADXL355_RANGE_2G: return ADXL355_SCALE_2G_G_PER_LSB;
        case ADXL355_RANGE_4G: return ADXL355_SCALE_4G_G_PER_LSB;
        case ADXL355_RANGE_8G: return ADXL355_SCALE_8G_G_PER_LSB;
        default:               return ADXL355_SCALE_4G_G_PER_LSB; /* safe default */
    }
}

/* ---------------------------------------------------------------------------
 * Core API
 * --------------------------------------------------------------------------- */

adxl355_status_t adxl355_init(adxl355_t *dev, const adxl355_bus_t *bus)
{
    if (dev == NULL || bus == NULL) {
        return ADXL355_ERR_NULL;
    }
    memset(dev, 0, sizeof(*dev));
    dev->bus = *bus;
    dev->range = ADXL355_RANGE_2G; /* datasheet reset default */
    dev->initialized = false;
    return ADXL355_OK;
}

adxl355_status_t adxl355_probe(adxl355_t *dev)
{
    if (dev == NULL) {
        return ADXL355_ERR_NULL;
    }
    dev->initialized = false;
    if (dev->bus.read == NULL || dev->bus.write == NULL) {
        return ADXL355_ERR_NULL;
    }

    uint8_t id_ad, id_mst, part_id;

    if (read_reg(dev, ADXL355_REG_DEVID_AD, &id_ad) != 0) {
        return ADXL355_ERR_BUS;
    }
    if (read_reg(dev, ADXL355_REG_DEVID_MST, &id_mst) != 0) {
        return ADXL355_ERR_BUS;
    }
    if (read_reg(dev, ADXL355_REG_PARTID, &part_id) != 0) {
        return ADXL355_ERR_BUS;
    }

    if (id_ad != ADXL355_DEVID_AD ||
        id_mst != ADXL355_DEVID_MST ||
        part_id != ADXL355_PARTID_VALUE) {
        return ADXL355_ERR_BAD_DEVICE;
    }

    uint8_t range_reg;
    adxl355_range_t detected_range;
    if (read_reg(dev, ADXL355_REG_RANGE, &range_reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    if (!range_from_register(range_reg, &detected_range)) {
        return ADXL355_ERR_INVALID_ARG;
    }

    uint8_t power_ctl;
    if (read_reg(dev, ADXL355_REG_POWER_CTL, &power_ctl) != 0) {
        return ADXL355_ERR_BUS;
    }
    if ((power_ctl & (uint8_t)(1U << ADXL355_POWER_MODE_BIT)) == 0U) {
        power_ctl |= (uint8_t)(1U << ADXL355_POWER_MODE_BIT);
        if (write_reg(dev, ADXL355_REG_POWER_CTL, power_ctl) != 0) {
            return ADXL355_ERR_BUS;
        }
    }

    dev->range = detected_range;
    dev->initialized = true;
    return ADXL355_OK;
}

adxl355_status_t adxl355_reset(adxl355_t *dev)
{
    if (dev == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }
    if (write_reg(dev, ADXL355_REG_RESET, ADXL355_RESET_CODE) != 0) {
        return ADXL355_ERR_BUS;
    }
    if (dev->bus.delay_ms != NULL) {
        dev->bus.delay_ms(dev->bus.ctx, 10);
    }
    dev->range = ADXL355_RANGE_2G;
    return ADXL355_OK;
}

adxl355_status_t adxl355_set_range(adxl355_t *dev, adxl355_range_t range)
{
    if (dev == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }
    if (range < ADXL355_RANGE_2G || range > ADXL355_RANGE_8G) {
        return ADXL355_ERR_INVALID_ARG;
    }

    adxl355_config_guard_t guard;
    adxl355_status_t status = enter_configuration_standby(dev, &guard);
    if (status != ADXL355_OK) {
        return status;
    }

    uint8_t reg;
    if (read_reg(dev, ADXL355_REG_RANGE, &reg) != 0) {
        status = ADXL355_ERR_BUS;
    } else {
        reg = (uint8_t)(clear_u8_bits(reg, ADXL355_RANGE_SEL_MASK) |
                        ((uint8_t)range & ADXL355_RANGE_SEL_MASK));
        if (write_reg(dev, ADXL355_REG_RANGE, reg) != 0) {
            status = ADXL355_ERR_BUS;
        } else {
            dev->range = range;
        }
    }
    return finish_configuration(dev, &guard, status);
}

adxl355_status_t adxl355_get_range(adxl355_t *dev, adxl355_range_t *range)
{
    if (dev == NULL || range == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }
    uint8_t reg;
    if (read_reg(dev, ADXL355_REG_RANGE, &reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    if (!range_from_register(reg, range)) {
        return ADXL355_ERR_INVALID_ARG;
    }
    return ADXL355_OK;
}

adxl355_status_t adxl355_set_power_mode(adxl355_t *dev, adxl355_power_mode_t mode)
{
    if (dev == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }
    if (mode != ADXL355_POWER_STANDBY && mode != ADXL355_POWER_MEASUREMENT) {
        return ADXL355_ERR_INVALID_ARG;
    }

    uint8_t reg;
    if (read_reg(dev, ADXL355_REG_POWER_CTL, &reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    if (mode == ADXL355_POWER_STANDBY) {
        reg |= (uint8_t)(1U << ADXL355_POWER_MODE_BIT);
    } else {
        reg = clear_u8_bits(reg, (uint8_t)(1U << ADXL355_POWER_MODE_BIT));
    }
    if (write_reg(dev, ADXL355_REG_POWER_CTL, reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    return ADXL355_OK;
}

adxl355_status_t adxl355_set_odr(adxl355_t *dev, adxl355_odr_t odr)
{
    if (dev == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }
    if (odr > ADXL355_ODR_3_906_HZ) {
        return ADXL355_ERR_INVALID_ARG;
    }

    adxl355_config_guard_t guard;
    adxl355_status_t status = enter_configuration_standby(dev, &guard);
    if (status != ADXL355_OK) {
        return status;
    }

    uint8_t reg;
    if (read_reg(dev, ADXL355_REG_FILTER, &reg) != 0) {
        status = ADXL355_ERR_BUS;
    } else {
        reg = (uint8_t)((reg & ADXL355_FILTER_HPF_MASK) |
                        ((uint8_t)odr & ADXL355_FILTER_ODR_MASK));
        if (write_reg(dev, ADXL355_REG_FILTER, reg) != 0) {
            status = ADXL355_ERR_BUS;
        }
    }
    return finish_configuration(dev, &guard, status);
}


adxl355_status_t adxl355_read_offset(adxl355_t *dev, adxl355_axis_t axis, int16_t *offset)
{
    if (dev == NULL || offset == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }
    uint8_t reg;
    if (!offset_register_for_axis(axis, &reg)) {
        return ADXL355_ERR_INVALID_ARG;
    }
    uint8_t data[2];
    if (read_exact(dev, reg, data, sizeof(data)) != 0) {
        return ADXL355_ERR_BUS;
    }
    uint16_t encoded = (uint16_t)(((uint16_t)data[0] << 8) | (uint16_t)data[1]);
    int32_t signed_value = (int32_t)encoded;
    if ((encoded & UINT16_C(0x8000)) != 0U) {
        signed_value -= INT32_C(0x10000);
    }
    *offset = (int16_t)signed_value;
    return ADXL355_OK;
}

adxl355_status_t adxl355_write_offset(adxl355_t *dev, adxl355_axis_t axis, int16_t offset)
{
    if (dev == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }
    uint8_t reg;
    if (!offset_register_for_axis(axis, &reg)) {
        return ADXL355_ERR_INVALID_ARG;
    }

    adxl355_config_guard_t guard;
    adxl355_status_t status = enter_configuration_standby(dev, &guard);
    if (status != ADXL355_OK) {
        return status;
    }

    uint16_t encoded = (uint16_t)offset;
    uint8_t data[2] = {
        (uint8_t)(encoded >> 8),
        (uint8_t)(encoded & UINT16_C(0x00FF)),
    };
    if (write_exact(dev, reg, data, sizeof(data)) != 0) {
        status = ADXL355_ERR_BUS;
    }
    return finish_configuration(dev, &guard, status);
}


typedef struct {
    uint8_t range_reg;
    uint8_t filter_reg;
    uint8_t power_ctl_reg;
    uint8_t self_test_reg;
    adxl355_range_t cached_range;
} adxl355_self_test_state_t;

static bool finite_nonnegative_xyz(const adxl355_float_xyz_t *value)
{
    return isfinite(value->x) && isfinite(value->y) && isfinite(value->z) &&
           value->x >= 0.0f && value->y >= 0.0f && value->z >= 0.0f;
}

static bool self_test_config_valid(const adxl355_self_test_config_t *config)
{
    if (config->sample_count == 0U || config->sample_count > 1024U ||
        config->settle_samples > 1024U || config->max_ready_polls == 0U ||
        config->max_ready_polls > 60000U || config->poll_delay_ms == 0U ||
        config->poll_delay_ms > 1000U) {
        return false;
    }
    if (!config->enforce_thresholds) {
        return true;
    }
    const adxl355_float_xyz_t *minimum = &config->thresholds.min_abs_delta_g;
    const adxl355_float_xyz_t *maximum = &config->thresholds.max_abs_delta_g;
    return finite_nonnegative_xyz(minimum) && finite_nonnegative_xyz(maximum) &&
           maximum->x >= minimum->x && maximum->y >= minimum->y &&
           maximum->z >= minimum->z;
}

static adxl355_status_t wait_for_data_ready(adxl355_t *dev,
                                             const adxl355_self_test_config_t *config)
{
    if (dev->bus.delay_ms == NULL) {
        return ADXL355_ERR_UNSUPPORTED;
    }
    for (uint16_t poll = 0U; poll < config->max_ready_polls; poll++) {
        uint8_t status;
        if (read_reg(dev, ADXL355_REG_STATUS, &status) != 0) {
            return ADXL355_ERR_BUS;
        }
        if ((status & ADXL355_STATUS_DATA_RDY) != 0U) {
            return ADXL355_OK;
        }
        dev->bus.delay_ms(dev->bus.ctx, config->poll_delay_ms);
    }
    return ADXL355_ERR_TIMEOUT;
}

static adxl355_status_t discard_self_test_samples(
    adxl355_t *dev,
    const adxl355_self_test_config_t *config)
{
    for (uint16_t sample = 0U; sample < config->settle_samples; sample++) {
        adxl355_status_t status = wait_for_data_ready(dev, config);
        if (status != ADXL355_OK) {
            return status;
        }
        adxl355_raw_xyz_t ignored;
        status = adxl355_read_raw(dev, &ignored);
        if (status != ADXL355_OK) {
            return status;
        }
    }
    return ADXL355_OK;
}

static adxl355_status_t collect_self_test_mean(
    adxl355_t *dev,
    const adxl355_self_test_config_t *config,
    adxl355_float_xyz_t *mean_g)
{
    adxl355_status_t status = discard_self_test_samples(dev, config);
    if (status != ADXL355_OK) {
        return status;
    }
    int64_t sum_x = 0;
    int64_t sum_y = 0;
    int64_t sum_z = 0;
    for (uint16_t sample = 0U; sample < config->sample_count; sample++) {
        status = wait_for_data_ready(dev, config);
        if (status != ADXL355_OK) {
            return status;
        }
        adxl355_raw_xyz_t raw;
        status = adxl355_read_raw(dev, &raw);
        if (status != ADXL355_OK) {
            return status;
        }
        sum_x += raw.x;
        sum_y += raw.y;
        sum_z += raw.z;
    }
    const float scale = ADXL355_SCALE_2G_G_PER_LSB / (float)config->sample_count;
    mean_g->x = (float)sum_x * scale;
    mean_g->y = (float)sum_y * scale;
    mean_g->z = (float)sum_z * scale;
    return ADXL355_OK;
}

static bool within_axis_threshold(float value, float minimum, float maximum)
{
    return value >= minimum && value <= maximum;
}

static bool self_test_thresholds_pass(
    const adxl355_self_test_thresholds_t *thresholds,
    const adxl355_float_xyz_t *absolute_delta)
{
    return within_axis_threshold(absolute_delta->x,
                                 thresholds->min_abs_delta_g.x,
                                 thresholds->max_abs_delta_g.x) &&
           within_axis_threshold(absolute_delta->y,
                                 thresholds->min_abs_delta_g.y,
                                 thresholds->max_abs_delta_g.y) &&
           within_axis_threshold(absolute_delta->z,
                                 thresholds->min_abs_delta_g.z,
                                 thresholds->max_abs_delta_g.z);
}

static adxl355_status_t read_self_test_state(adxl355_t *dev,
                                              adxl355_self_test_state_t *state)
{
    if (read_reg(dev, ADXL355_REG_RANGE, &state->range_reg) != 0 ||
        read_reg(dev, ADXL355_REG_FILTER, &state->filter_reg) != 0 ||
        read_reg(dev, ADXL355_REG_POWER_CTL, &state->power_ctl_reg) != 0 ||
        read_reg(dev, ADXL355_REG_SELF_TEST, &state->self_test_reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    state->cached_range = dev->range;
    if ((state->self_test_reg & ADXL355_SELF_TEST_MASK) != 0U) {
        return ADXL355_ERR_STATE;
    }
    return ADXL355_OK;
}

static adxl355_status_t configure_self_test(adxl355_t *dev,
                                             const adxl355_self_test_state_t *state)
{
    const uint8_t standby = (uint8_t)(state->power_ctl_reg |
                                      (uint8_t)(1U << ADXL355_POWER_MODE_BIT));
    const uint8_t range_2g = (uint8_t)(clear_u8_bits(state->range_reg,
                                                     ADXL355_RANGE_SEL_MASK) |
                                       ADXL355_RANGE_2G_VAL);
    const uint8_t filter_125hz = (uint8_t)(clear_u8_bits(state->filter_reg,
                                                         ADXL355_FILTER_ODR_MASK) |
                                           (uint8_t)ADXL355_ODR_125_HZ);
    const uint8_t self_test_off = clear_u8_bits(state->self_test_reg,
                                                ADXL355_SELF_TEST_MASK);
    const uint8_t measurement = clear_u8_bits(state->power_ctl_reg,
                                               (uint8_t)(1U << ADXL355_POWER_MODE_BIT));
    if (write_reg(dev, ADXL355_REG_POWER_CTL, standby) != 0 ||
        write_reg(dev, ADXL355_REG_RANGE, range_2g) != 0 ||
        write_reg(dev, ADXL355_REG_FILTER, filter_125hz) != 0 ||
        write_reg(dev, ADXL355_REG_SELF_TEST, self_test_off) != 0 ||
        write_reg(dev, ADXL355_REG_POWER_CTL, measurement) != 0) {
        return ADXL355_ERR_BUS;
    }
    dev->range = ADXL355_RANGE_2G;
    return ADXL355_OK;
}

static adxl355_status_t restore_self_test_state(adxl355_t *dev,
                                                 const adxl355_self_test_state_t *state)
{
    bool failed = false;
    const uint8_t standby = (uint8_t)(state->power_ctl_reg |
                                      (uint8_t)(1U << ADXL355_POWER_MODE_BIT));
    failed = write_reg(dev, ADXL355_REG_SELF_TEST, state->self_test_reg) != 0 || failed;
    failed = write_reg(dev, ADXL355_REG_POWER_CTL, standby) != 0 || failed;
    failed = write_reg(dev, ADXL355_REG_RANGE, state->range_reg) != 0 || failed;
    failed = write_reg(dev, ADXL355_REG_FILTER, state->filter_reg) != 0 || failed;
    failed = write_reg(dev, ADXL355_REG_POWER_CTL, state->power_ctl_reg) != 0 || failed;
    dev->range = state->cached_range;
    return failed ? ADXL355_ERR_RESTORE : ADXL355_OK;
}

adxl355_status_t adxl355_self_test_config_default(adxl355_self_test_config_t *config)
{
    if (config == NULL) {
        return ADXL355_ERR_NULL;
    }
    memset(config, 0, sizeof(*config));
    config->sample_count = 32U;
    config->settle_samples = 4U;
    config->max_ready_polls = 500U;
    config->poll_delay_ms = 1U;
    return ADXL355_OK;
}

adxl355_status_t adxl355_run_self_test(adxl355_t *dev,
                                        const adxl355_self_test_config_t *config,
                                        adxl355_self_test_result_t *result)
{
    if (dev == NULL || config == NULL || result == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t status = require_initialized(dev);
    if (status != ADXL355_OK) {
        return status;
    }
    if (!self_test_config_valid(config)) {
        return ADXL355_ERR_INVALID_ARG;
    }
    memset(result, 0, sizeof(*result));
    adxl355_self_test_state_t state;
    status = read_self_test_state(dev, &state);
    if (status != ADXL355_OK) {
        return status;
    }

    status = configure_self_test(dev, &state);
    if (status == ADXL355_OK) {
        const uint8_t self_test_mode =
            (uint8_t)(clear_u8_bits(state.self_test_reg, ADXL355_SELF_TEST_MASK) |
                      ADXL355_SELF_TEST_ST1);
        status = write_reg(dev, ADXL355_REG_SELF_TEST, self_test_mode) == 0
                     ? ADXL355_OK
                     : ADXL355_ERR_BUS;
    }
    if (status == ADXL355_OK) {
        status = collect_self_test_mean(dev, config, &result->baseline_g);
    }
    if (status == ADXL355_OK) {
        const uint8_t enabled = (uint8_t)(clear_u8_bits(state.self_test_reg,
                                                        ADXL355_SELF_TEST_MASK) |
                                           ADXL355_SELF_TEST_MASK);
        status = write_reg(dev, ADXL355_REG_SELF_TEST, enabled) == 0
                     ? ADXL355_OK
                     : ADXL355_ERR_BUS;
    }
    if (status == ADXL355_OK) {
        status = collect_self_test_mean(dev, config, &result->stimulated_g);
    }
    if (status == ADXL355_OK) {
        result->delta_g.x = result->stimulated_g.x - result->baseline_g.x;
        result->delta_g.y = result->stimulated_g.y - result->baseline_g.y;
        result->delta_g.z = result->stimulated_g.z - result->baseline_g.z;
        result->abs_delta_g.x = fabsf(result->delta_g.x);
        result->abs_delta_g.y = fabsf(result->delta_g.y);
        result->abs_delta_g.z = fabsf(result->delta_g.z);
        result->samples = config->sample_count;
        result->thresholds_evaluated = config->enforce_thresholds;
        result->thresholds_passed = !config->enforce_thresholds ||
                                    self_test_thresholds_pass(&config->thresholds,
                                                              &result->abs_delta_g);
        if (!result->thresholds_passed) {
            status = ADXL355_ERR_THRESHOLD;
        }
    }

    const adxl355_status_t restore = restore_self_test_state(dev, &state);
    return restore == ADXL355_OK ? status : restore;
}

adxl355_status_t adxl355_read_raw(adxl355_t *dev, adxl355_raw_xyz_t *out)
{
    if (dev == NULL || out == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }

    uint8_t buf[9];
    if (read_exact(dev, ADXL355_REG_XDATA3, buf, 9U) != 0) {
        return ADXL355_ERR_BUS;
    }

    out->x = adxl355_decode_raw20(buf[0], buf[1], buf[2]);
    out->y = adxl355_decode_raw20(buf[3], buf[4], buf[5]);
    out->z = adxl355_decode_raw20(buf[6], buf[7], buf[8]);
    return ADXL355_OK;
}

adxl355_status_t adxl355_read_g(adxl355_t *dev, adxl355_float_xyz_t *out)
{
    if (dev == NULL || out == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_raw_xyz_t raw;
    adxl355_status_t status = adxl355_read_raw(dev, &raw);
    if (status != ADXL355_OK) {
        return status;
    }
    float scale = range_to_scale_g_per_lsb(dev->range);
    out->x = (float)raw.x * scale;
    out->y = (float)raw.y * scale;
    out->z = (float)raw.z * scale;
    return ADXL355_OK;
}

adxl355_status_t adxl355_read_mps2(adxl355_t *dev, adxl355_float_xyz_t *out)
{
    if (dev == NULL || out == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t status = adxl355_read_g(dev, out);
    if (status != ADXL355_OK) {
        return status;
    }
    out->x *= ADXL355_STANDARD_GRAVITY_M_S2;
    out->y *= ADXL355_STANDARD_GRAVITY_M_S2;
    out->z *= ADXL355_STANDARD_GRAVITY_M_S2;
    return ADXL355_OK;
}

adxl355_status_t adxl355_read_temperature_raw(adxl355_t *dev, int16_t *out)
{
    if (dev == NULL || out == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }
    for (uint8_t attempt = 0U; attempt < ADXL355_TEMP_READ_ATTEMPTS; attempt++) {
        uint8_t sample[2];
        uint8_t confirm_temp2;
        if (read_exact(dev, ADXL355_REG_TEMP2, sample, 2U) != 0) {
            return ADXL355_ERR_BUS;
        }
        if (read_exact(dev, ADXL355_REG_TEMP2, &confirm_temp2, 1U) != 0) {
            return ADXL355_ERR_BUS;
        }

        uint8_t sample_temp2 = (uint8_t)(sample[0] & ADXL355_TEMP2_DATA_MASK);
        confirm_temp2 &= ADXL355_TEMP2_DATA_MASK;
        if (sample_temp2 == confirm_temp2) {
            int16_t raw = (int16_t)(((uint16_t)sample_temp2 << 8) | (uint16_t)sample[1]);
            *out = raw;
            return ADXL355_OK;
        }
    }
    return ADXL355_ERR_NOT_READY;
}

adxl355_status_t adxl355_read_temperature_c(adxl355_t *dev, float *out)
{
    if (dev == NULL || out == NULL) {
        return ADXL355_ERR_NULL;
    }
    int16_t raw;
    adxl355_status_t status = adxl355_read_temperature_raw(dev, &raw);
    if (status != ADXL355_OK) {
        return status;
    }
    /* Datasheet Rev.D temperature sensor: 12-bit unsigned, nominal intercept 1885 LSB at 25°C,
     * slope -9.05 LSB/°C. Formula: T(°C) = 25.0 + (raw - 1885.0) / -9.05 */
    *out = ADXL355_TEMP_INTERCEPT_C +
           ((float)raw - ADXL355_TEMP_INTERCEPT_LSB) / ADXL355_TEMP_SLOPE_LSB_PER_C;
    return ADXL355_OK;
}

adxl355_status_t adxl355_read_status(adxl355_t *dev, uint8_t *status)
{
    if (dev == NULL || status == NULL) {
        return ADXL355_ERR_NULL;
    }
    adxl355_status_t state = require_initialized(dev);
    if (state != ADXL355_OK) {
        return state;
    }
    return (read_reg(dev, ADXL355_REG_STATUS, status) == 0)
           ? ADXL355_OK
           : ADXL355_ERR_BUS;
}

/* ---------------------------------------------------------------------------
 * Utility / conversion functions
 * --------------------------------------------------------------------------- */

int32_t adxl355_decode_raw20(uint8_t b0, uint8_t b1, uint8_t b2)
{
    int32_t raw = ((int32_t)b0 << 12) | ((int32_t)b1 << 4) | ((int32_t)b2 >> 4);
    /* Sign-extend the 20-bit value to 32 bits */
    if (raw & 0x80000) {
        raw -= 0x100000;
    }
    return raw;
}

float adxl355_raw_to_g(int32_t raw, adxl355_range_t range)
{
    return (float)raw * range_to_scale_g_per_lsb(range);
}

float adxl355_raw_to_mps2(int32_t raw, adxl355_range_t range)
{
    return (float)raw * range_to_scale_g_per_lsb(range) * ADXL355_STANDARD_GRAVITY_M_S2;
}


adxl355_status_t adxl355_calculate_offset(int32_t measured_raw,
                                           int32_t expected_raw,
                                           int16_t current_offset,
                                           bool saturate,
                                           int16_t *offset)
{
    if (offset == NULL) {
        return ADXL355_ERR_NULL;
    }
    const int32_t raw_min = -INT32_C(524288);
    const int32_t raw_max = INT32_C(524287);
    if (measured_raw < raw_min || measured_raw > raw_max ||
        expected_raw < raw_min || expected_raw > raw_max) {
        return ADXL355_ERR_INVALID_ARG;
    }

    int64_t delta = (int64_t)measured_raw - (int64_t)expected_raw;
    int64_t adjustment = delta >= 0 ? (delta + INT64_C(8)) / INT64_C(16)
                                    : (delta - INT64_C(8)) / INT64_C(16);
    int64_t counts = (int64_t)current_offset + adjustment;
    if (counts > INT16_MAX) {
        if (!saturate) {
            return ADXL355_ERR_INVALID_ARG;
        }
        counts = INT16_MAX;
    } else if (counts < INT16_MIN) {
        if (!saturate) {
            return ADXL355_ERR_INVALID_ARG;
        }
        counts = INT16_MIN;
    }
    *offset = (int16_t)counts;
    return ADXL355_OK;
}

const char *adxl355_status_string(adxl355_status_t status)
{
    switch (status) {
        case ADXL355_OK:             return "ADXL355_OK";
        case ADXL355_ERR_NULL:       return "ADXL355_ERR_NULL";
        case ADXL355_ERR_BUS:        return "ADXL355_ERR_BUS";
        case ADXL355_ERR_TIMEOUT:    return "ADXL355_ERR_TIMEOUT";
        case ADXL355_ERR_INVALID_ARG: return "ADXL355_ERR_INVALID_ARG";
        case ADXL355_ERR_BAD_DEVICE: return "ADXL355_ERR_BAD_DEVICE";
        case ADXL355_ERR_NOT_READY:  return "ADXL355_ERR_NOT_READY";
        case ADXL355_ERR_UNSUPPORTED: return "ADXL355_ERR_UNSUPPORTED";
        case ADXL355_ERR_STATE:       return "ADXL355_ERR_STATE";
        case ADXL355_ERR_THRESHOLD:   return "ADXL355_ERR_THRESHOLD";
        case ADXL355_ERR_RESTORE:     return "ADXL355_ERR_RESTORE";
        default:                     return "ADXL355_UNKNOWN";
    }
}
