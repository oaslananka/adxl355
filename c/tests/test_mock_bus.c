#include "test_mock_bus.h"
#include <limits.h>
#include <string.h>

/* ---------------------------------------------------------------------------
 * Mock bus callbacks
 * --------------------------------------------------------------------------- */

static void encode_axis(uint8_t *data, int32_t raw)
{
    const uint32_t value = (uint32_t)(raw & INT32_C(0xFFFFF));
    data[0] = (uint8_t)((value >> 12) & UINT32_C(0xFF));
    data[1] = (uint8_t)((value >> 4) & UINT32_C(0xFF));
    data[2] = (uint8_t)((value & UINT32_C(0x0F)) << 4);
}

static void encode_xyz(uint8_t *data, const adxl355_raw_xyz_t *raw)
{
    encode_axis(&data[0], raw->x);
    encode_axis(&data[3], raw->y);
    encode_axis(&data[6], raw->z);
}


static int mock_read(void *ctx, uint8_t reg, uint8_t *data, size_t len)
{
    adxl355_mock_bus_t *mock = (adxl355_mock_bus_t *)ctx;
    if (mock->force_error != 0 || mock->force_read_error != 0 ||
        (mock->fail_read_reg >= 0 && reg == (uint8_t)mock->fail_read_reg)) {
        return -1;
    }
    /* Log the call */
    if (mock->call_count < ADXL355_MOCK_MAX_CALLS) {
        mock->calls[mock->call_count].is_write = false;
        mock->calls[mock->call_count].reg      = reg;
        mock->calls[mock->call_count].len      = len;
    }
    mock->call_count++;

    size_t reported_len = len;
    if (mock->short_read_reg >= 0 && reg == (uint8_t)mock->short_read_reg) {
        reported_len = mock->short_read_length;
    }
    size_t copy_len = reported_len < len ? reported_len : len;
    if (mock->emulate_self_test && reg == ADXL355_REG_XDATA3 && copy_len == 9U) {
        const uint8_t mode =
            (uint8_t)(mock->regs[ADXL355_REG_SELF_TEST] & ADXL355_SELF_TEST_MASK);
        if (mode == ADXL355_SELF_TEST_MASK) {
            encode_xyz(data, &mock->self_test_stimulated);
        } else if (mode == ADXL355_SELF_TEST_ST1) {
            encode_xyz(data, &mock->self_test_baseline);
        } else {
            for (size_t i = 0; i < copy_len; i++) {
                data[i] = mock->regs[reg + i];
            }
        }
    } else {
        for (size_t i = 0; i < copy_len && (reg + i) < ADXL355_MOCK_NUM_REGS; i++) {
            data[i] = mock->regs[reg + i];
        }
    }
    return reported_len <= (size_t)INT_MAX ? (int)reported_len : -1;
}

static int mock_write(void *ctx, uint8_t reg, const uint8_t *data, size_t len)
{
    adxl355_mock_bus_t *mock = (adxl355_mock_bus_t *)ctx;
    if (mock->force_error != 0 || mock->force_write_error != 0) {
        return -1;
    }
    if (mock->fail_write_reg >= 0 && reg == (uint8_t)mock->fail_write_reg) {
        mock->fail_write_matches++;
        if (mock->fail_write_occurrence == 0U ||
            mock->fail_write_matches == mock->fail_write_occurrence) {
            return -1;
        }
    }
    /* Log the call */
    if (mock->call_count < ADXL355_MOCK_MAX_CALLS) {
        mock->calls[mock->call_count].is_write = true;
        mock->calls[mock->call_count].reg      = reg;
        mock->calls[mock->call_count].len      = len;
        if (len > 0) {
            mock->calls[mock->call_count].data = data[0];
        }
    }
    mock->call_count++;

    for (size_t i = 0; i < len && (reg + i) < ADXL355_MOCK_NUM_REGS; i++) {
        mock->regs[reg + i] = data[i];
    }
    if (reg == ADXL355_REG_RESET && len > 0 && data[0] == ADXL355_RESET_CODE) {
        mock->regs[ADXL355_REG_RANGE] = ADXL355_RANGE_2G;
    }
    return len <= (size_t)INT_MAX ? (int)len : -1;
}

static void mock_delay(void *ctx, uint32_t ms)
{
    (void)ctx;
    (void)ms;
    /* No actual delay in test */
}

/* ---------------------------------------------------------------------------
 * Mock API
 * --------------------------------------------------------------------------- */

void adxl355_mock_bus_init(adxl355_mock_bus_t *mock)
{
    memset(mock, 0, sizeof(*mock));
    mock->fail_read_reg = -1;
    mock->short_read_reg = -1;
    mock->fail_write_reg = -1;
    mock->regs[ADXL355_REG_RANGE] = ADXL355_RANGE_2G;
    mock->regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_STANDBY;
}

void adxl355_mock_bus_set_identity_ok(adxl355_mock_bus_t *mock)
{
    mock->regs[ADXL355_REG_DEVID_AD]  = ADXL355_DEVID_AD;
    mock->regs[ADXL355_REG_DEVID_MST] = ADXL355_DEVID_MST;
    mock->regs[ADXL355_REG_PARTID]    = ADXL355_PARTID_VALUE;
}

void adxl355_mock_bus_set_xyz_raw(adxl355_mock_bus_t *mock,
                                  int32_t raw_x, int32_t raw_y, int32_t raw_z)
{
    adxl355_raw_xyz_t raw = {raw_x, raw_y, raw_z};
    encode_xyz(&mock->regs[ADXL355_REG_XDATA3], &raw);
}

void adxl355_mock_bus_set_self_test_xyz(adxl355_mock_bus_t *mock,
                                        adxl355_raw_xyz_t baseline,
                                        adxl355_raw_xyz_t stimulated)
{
    mock->emulate_self_test = true;
    mock->self_test_baseline = baseline;
    mock->self_test_stimulated = stimulated;
    mock->regs[ADXL355_REG_STATUS] = ADXL355_STATUS_DATA_RDY;
}


adxl355_bus_t adxl355_mock_bus_get_interface(adxl355_mock_bus_t *mock)
{
    adxl355_bus_t bus;
    bus.read     = mock_read;
    bus.write    = mock_write;
    bus.delay_ms = mock_delay;
    bus.ctx      = (void *)mock;
    return bus;
}
