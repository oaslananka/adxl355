#include "adxl355/adxl355.h"

#include <string.h>

/* ---------------------------------------------------------------------------
 * Internal helpers
 * --------------------------------------------------------------------------- */

static inline int read_reg(adxl355_t *dev, uint8_t reg, uint8_t *byte)
{
    return dev->bus.read(dev->bus.ctx, reg, byte, 1);
}

static inline int write_reg(adxl355_t *dev, uint8_t reg, uint8_t byte)
{
    return dev->bus.write(dev->bus.ctx, reg, &byte, 1);
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

    /* Put device into standby mode after probe. */
    if (write_reg(dev, ADXL355_REG_POWER_CTL, ADXL355_POWER_STANDBY) != 0) {
        return ADXL355_ERR_BUS;
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
    if (range < ADXL355_RANGE_2G || range > ADXL355_RANGE_8G) {
        return ADXL355_ERR_INVALID_ARG;
    }
    uint8_t reg;
    if (read_reg(dev, ADXL355_REG_RANGE, &reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    reg = (uint8_t)((reg & (uint8_t)(~ADXL355_RANGE_SEL_MASK)) |
                    ((uint8_t)range & ADXL355_RANGE_SEL_MASK));
    if (write_reg(dev, ADXL355_REG_RANGE, reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    dev->range = range;
    return ADXL355_OK;
}

adxl355_status_t adxl355_get_range(adxl355_t *dev, adxl355_range_t *range)
{
    if (dev == NULL || range == NULL) {
        return ADXL355_ERR_NULL;
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
    uint8_t reg;
    if (read_reg(dev, ADXL355_REG_POWER_CTL, &reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    /* Datasheet Rev.D, Table 43: bit 0 = 1 => standby, bit 0 = 0 => measurement */
    if (mode == ADXL355_POWER_STANDBY) {
        reg |= (uint8_t)(1U << ADXL355_POWER_MODE_BIT);
    } else {
        reg &= (uint8_t)~(1U << ADXL355_POWER_MODE_BIT);
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
    if (odr > ADXL355_ODR_3_906_HZ) {
        return ADXL355_ERR_INVALID_ARG;
    }
    uint8_t reg;
    if (read_reg(dev, ADXL355_REG_FILTER, &reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    /* Datasheet Rev.D, Table 38: ODR_LPF in bits 3:0, HPF_CORNER in bits 6:4 */
    reg = (uint8_t)((reg & ADXL355_FILTER_HPF_MASK) | ((uint8_t)odr & ADXL355_FILTER_ODR_MASK));
    if (write_reg(dev, ADXL355_REG_FILTER, reg) != 0) {
        return ADXL355_ERR_BUS;
    }
    return ADXL355_OK;
}

adxl355_status_t adxl355_read_raw(adxl355_t *dev, adxl355_raw_xyz_t *out)
{
    if (dev == NULL || out == NULL) {
        return ADXL355_ERR_NULL;
    }

    uint8_t buf[9];
    if (dev->bus.read(dev->bus.ctx, ADXL355_REG_XDATA3, buf, 9) != 0) {
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
    uint8_t buf[2];
    if (dev->bus.read(dev->bus.ctx, ADXL355_REG_TEMP2, buf, 2) != 0) {
        return ADXL355_ERR_BUS;
    }
    *out = (int16_t)(((uint16_t)buf[0] << 8) | (uint16_t)buf[1]);
    return ADXL355_OK;
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
    *out = 25.0f + ((float)raw - 1885.0f) / -9.05f;
    return ADXL355_OK;
}

adxl355_status_t adxl355_read_status(adxl355_t *dev, uint8_t *status)
{
    if (dev == NULL || status == NULL) {
        return ADXL355_ERR_NULL;
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
        default:                     return "ADXL355_UNKNOWN";
    }
}
