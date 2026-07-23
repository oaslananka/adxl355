#include "test_mock_bus.h"
#include <string.h>

/* ---------------------------------------------------------------------------
 * Mock bus callbacks
 * --------------------------------------------------------------------------- */

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

    /* Simulate register read */
    for (size_t i = 0; i < len && (reg + i) < ADXL355_MOCK_NUM_REGS; i++) {
        data[i] = mock->regs[reg + i];
    }
    return 0;
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
    return 0;
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
    /* Encode 20-bit values into the three data registers each */
    uint32_t ux = (uint32_t)(raw_x & 0xFFFFF);
    mock->regs[ADXL355_REG_XDATA3] = (uint8_t)((ux >> 12) & 0xFF);
    mock->regs[ADXL355_REG_XDATA2] = (uint8_t)((ux >> 4) & 0xFF);
    mock->regs[ADXL355_REG_XDATA1] = (uint8_t)((ux & 0x0F) << 4);

    uint32_t uy = (uint32_t)(raw_y & 0xFFFFF);
    mock->regs[ADXL355_REG_YDATA3] = (uint8_t)((uy >> 12) & 0xFF);
    mock->regs[ADXL355_REG_YDATA2] = (uint8_t)((uy >> 4) & 0xFF);
    mock->regs[ADXL355_REG_YDATA1] = (uint8_t)((uy & 0x0F) << 4);

    uint32_t uz = (uint32_t)(raw_z & 0xFFFFF);
    mock->regs[ADXL355_REG_ZDATA3] = (uint8_t)((uz >> 12) & 0xFF);
    mock->regs[ADXL355_REG_ZDATA2] = (uint8_t)((uz >> 4) & 0xFF);
    mock->regs[ADXL355_REG_ZDATA1] = (uint8_t)((uz & 0x0F) << 4);
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
