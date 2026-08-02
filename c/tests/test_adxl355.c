#include "adxl355/adxl355.h"
#include "test_mock_bus.h"
#include "fifo_vectors.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <limits.h>

/* ---------------------------------------------------------------------------
 * Simple test framework (no external deps)
 * --------------------------------------------------------------------------- */
static int  g_tests_run  = 0;
static int  g_tests_pass = 0;
static int  g_tests_fail = 0;

#define TEST_ASSERT(cond, msg) do {                                     \
    g_tests_run++;                                                      \
    if (!(cond)) {                                                      \
        fprintf(stderr, "  FAIL [%s:%d] %s\n", __FILE__, __LINE__, msg);\
        g_tests_fail++;                                                 \
    } else {                                                            \
        g_tests_pass++;                                                 \
    }                                                                   \
} while(0)

#define TEST_START(name)   printf("\n--- %s ---\n", name)
#define TEST_END()         printf("  passed\n")

/* near-enough float comparison */
static int approx_eq(float a, float b, float eps)
{
    return fabsf(a - b) < eps;
}

/* ---------------------------------------------------------------------------
 * Tests
 * --------------------------------------------------------------------------- */

static void test_decode_raw20_zero(void)
{
    TEST_START("decode_raw20_zero");
    int32_t v = adxl355_decode_raw20(0, 0, 0);
    TEST_ASSERT(v == 0, "0,0,0 should decode to 0");
    TEST_END();
}

static void test_decode_raw20_positive_one(void)
{
    TEST_START("decode_raw20_positive_one");
    /* bytes: [0, 0, 16] => raw bit 0 set */
    int32_t v = adxl355_decode_raw20(0, 0, 16);
    TEST_ASSERT(v == 1, "should decode to 1");
    TEST_END();
}

static void test_decode_raw20_positive_max(void)
{
    TEST_START("decode_raw20_positive_max");
    int32_t v = adxl355_decode_raw20(127, 255, 240);
    TEST_ASSERT(v == 524287, "0x7FFFF = 524287");
    TEST_END();
}

static void test_decode_raw20_negative_min(void)
{
    TEST_START("decode_raw20_negative_min");
    int32_t v = adxl355_decode_raw20(128, 0, 0);
    TEST_ASSERT(v == -524288, "0x80000 = -524288");
    TEST_END();
}

static void test_decode_raw20_negative_one(void)
{
    TEST_START("decode_raw20_negative_one");
    int32_t v = adxl355_decode_raw20(255, 255, 240);
    TEST_ASSERT(v == -1, "0xFFFFF = -1");
    TEST_END();
}

static void test_raw_to_g_2g(void)
{
    TEST_START("raw_to_g_2g");
    float g = adxl355_raw_to_g(524287, ADXL355_RANGE_2G);
    float expected = 524287.0f * 0.0000039f;
    TEST_ASSERT(approx_eq(g, expected, 1e-6f), "raw 524287 @ 2g");
    TEST_END();
}

static void test_raw_to_g_4g(void)
{
    TEST_START("raw_to_g_4g");
    float g = adxl355_raw_to_g(524287, ADXL355_RANGE_4G);
    float expected = 524287.0f * 0.0000078f;
    TEST_ASSERT(approx_eq(g, expected, 1e-6f), "raw 524287 @ 4g");
    TEST_END();
}

static void test_raw_to_g_8g(void)
{
    TEST_START("raw_to_g_8g");
    float g = adxl355_raw_to_g(524287, ADXL355_RANGE_8G);
    float expected = 524287.0f * 0.0000156f;
    TEST_ASSERT(approx_eq(g, expected, 1e-6f), "raw 524287 @ 8g");
    TEST_END();
}

static void test_raw_to_mps2(void)
{
    TEST_START("raw_to_mps2");
    float mps2 = adxl355_raw_to_mps2(100000, ADXL355_RANGE_2G);
    float expected = 100000.0f * 0.0000039f * 9.80665f;
    TEST_ASSERT(approx_eq(mps2, expected, 1e-5f), "raw 100000 @ 2g -> m/s^2");
    TEST_END();
}

static void test_init_null_args(void)
{
    TEST_START("init_null_args");
    adxl355_t dev;
    adxl355_bus_t bus;
    memset(&bus, 0, sizeof(bus));
    TEST_ASSERT(adxl355_init(NULL, &bus) == ADXL355_ERR_NULL, "dev NULL");
    TEST_ASSERT(adxl355_init(&dev, NULL) == ADXL355_ERR_NULL, "bus NULL");
    TEST_END();
}

static void test_init_defaults_to_2g(void)
{
    TEST_START("init_defaults_to_2g");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;

    TEST_ASSERT(adxl355_init(&dev, &bus) == ADXL355_OK, "init should succeed");
    TEST_ASSERT(dev.range == ADXL355_RANGE_2G, "init range should be 2g");
    TEST_END();
}

static void test_probe_synchronizes_range(void)
{
    TEST_START("probe_synchronizes_range");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    mock.regs[ADXL355_REG_RANGE] = ADXL355_RANGE_8G;
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);

    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");
    TEST_ASSERT(dev.range == ADXL355_RANGE_8G, "probe should cache hardware 8g range");
    TEST_END();
}

static void test_probe_rejects_reserved_range(void)
{
    TEST_START("probe_rejects_reserved_range");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    mock.regs[ADXL355_REG_RANGE] = 0x00;
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);

    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_ERR_INVALID_ARG,
                "probe should reject reserved range encoding");
    TEST_ASSERT(dev.initialized == false, "failed probe should remain uninitialized");
    TEST_ASSERT(dev.range == ADXL355_RANGE_2G, "failed probe should preserve cached range");
    TEST_END();
}

static void test_probe_reset_range_converts_one_g(void)
{
    TEST_START("probe_reset_range_converts_one_g");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    mock.regs[ADXL355_REG_RANGE] = ADXL355_RANGE_2G;
    adxl355_mock_bus_set_xyz_raw(&mock, 256410, 0, 0);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);

    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");
    adxl355_float_xyz_t accel;
    TEST_ASSERT(adxl355_read_g(&dev, &accel) == ADXL355_OK, "read_g should succeed");
    TEST_ASSERT(approx_eq(accel.x, 1.0f, 0.001f), "reset-range raw value should convert to 1g");
    TEST_END();
}

static void test_probe_bad_device(void)
{
    TEST_START("probe_bad_device");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    /* Don't set identity => probe should fail */
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_ERR_BAD_DEVICE, "bad device");
    TEST_END();
}

static void test_probe_ok(void)
{
    TEST_START("probe_ok");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe OK");
    TEST_ASSERT(dev.initialized == true, "dev.initialized should be true");
    TEST_END();
}

static size_t count_mock_writes(const adxl355_mock_bus_t *mock, uint8_t reg)
{
    size_t count = 0U;
    for (size_t i = 0U; i < mock->call_count && i < ADXL355_MOCK_MAX_CALLS; i++) {
        if (mock->calls[i].is_write && mock->calls[i].reg == reg) {
            count++;
        }
    }
    return count;
}

static void test_pre_probe_operations_return_state_error(void)
{
    TEST_START("pre_probe_operations_return_state_error");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    uint8_t status = 0xAAU;

    TEST_ASSERT(adxl355_set_range(&dev, ADXL355_RANGE_4G) == ADXL355_ERR_STATE,
                "set_range before probe should return state error");
    TEST_ASSERT(adxl355_read_status(&dev, &status) == ADXL355_ERR_STATE,
                "read_status before probe should return state error");
    TEST_ASSERT(adxl355_reset(&dev) == ADXL355_ERR_STATE,
                "reset before probe should return state error");
    TEST_ASSERT(mock.call_count == 0U, "pre-probe operations should not access the bus");
    TEST_ASSERT(status == 0xAAU, "pre-probe read should not modify output");
    TEST_END();
}

static void test_set_range_temporarily_enters_standby(void)
{
    TEST_START("set_range_temporarily_enters_standby");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    mock.regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;
    mock.call_count = 0U;
    TEST_ASSERT(adxl355_set_range(&dev, ADXL355_RANGE_4G) == ADXL355_OK,
                "range change in measurement should succeed");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_MEASUREMENT,
                "measurement mode should be restored");
    TEST_ASSERT(mock.regs[ADXL355_REG_RANGE] == ADXL355_RANGE_4G,
                "range register should be updated");
    TEST_ASSERT(dev.range == ADXL355_RANGE_4G, "range cache should be updated");
    TEST_ASSERT(count_mock_writes(&mock, ADXL355_REG_POWER_CTL) == 2U,
                "measurement configuration should write standby then restore");
    TEST_END();
}

static void test_set_range_in_standby_avoids_power_writes(void)
{
    TEST_START("set_range_in_standby_avoids_power_writes");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    mock.call_count = 0U;
    TEST_ASSERT(adxl355_set_range(&dev, ADXL355_RANGE_8G) == ADXL355_OK,
                "standby range change should succeed");
    TEST_ASSERT(count_mock_writes(&mock, ADXL355_REG_POWER_CTL) == 0U,
                "already-standby configuration should not rewrite power mode");
    TEST_END();
}

static void test_set_range_failure_restores_measurement(void)
{
    TEST_START("set_range_failure_restores_measurement");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    mock.regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;
    mock.fail_write_reg = ADXL355_REG_RANGE;
    TEST_ASSERT(adxl355_set_range(&dev, ADXL355_RANGE_4G) == ADXL355_ERR_BUS,
                "target write failure should return bus error");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_MEASUREMENT,
                "measurement mode should be restored after target failure");
    TEST_ASSERT(mock.regs[ADXL355_REG_RANGE] == ADXL355_RANGE_2G,
                "failed target write should leave hardware range unchanged");
    TEST_ASSERT(dev.range == ADXL355_RANGE_2G,
                "failed target write should leave cache unchanged");
    TEST_END();
}

static void test_set_range_restore_failure_keeps_range_cache_consistent(void)
{
    TEST_START("set_range_restore_failure_keeps_range_cache_consistent");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    mock.regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;
    mock.fail_write_reg = ADXL355_REG_POWER_CTL;
    mock.fail_write_occurrence = 2U;
    TEST_ASSERT(adxl355_set_range(&dev, ADXL355_RANGE_4G) == ADXL355_ERR_BUS,
                "restore failure should return bus error");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_STANDBY,
                "failed restore should leave hardware in standby");
    TEST_ASSERT(mock.regs[ADXL355_REG_RANGE] == ADXL355_RANGE_4G,
                "successful target write should update hardware range");
    TEST_ASSERT(dev.range == ADXL355_RANGE_4G,
                "cache should match successful hardware range write");
    TEST_END();
}

static void test_set_odr_temporarily_enters_standby(void)
{
    TEST_START("set_odr_temporarily_enters_standby");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    mock.regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;
    mock.regs[ADXL355_REG_FILTER] = 0x50U;
    mock.call_count = 0U;
    TEST_ASSERT(adxl355_set_odr(&dev, ADXL355_ODR_125_HZ) == ADXL355_OK,
                "ODR change in measurement should succeed");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_MEASUREMENT,
                "measurement mode should be restored after ODR change");
    TEST_ASSERT(mock.regs[ADXL355_REG_FILTER] == 0x55U,
                "ODR update should preserve HPF bits");
    TEST_ASSERT(count_mock_writes(&mock, ADXL355_REG_POWER_CTL) == 2U,
                "ODR configuration should write standby then restore");
    TEST_END();
}

static void test_set_range_writes_expected_register(void)
{
    TEST_START("set_range_writes_expected_register");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    adxl355_set_range(&dev, ADXL355_RANGE_2G);

    /* Verify the write was to the RANGE register */
    int found = 0;
    for (size_t i = 0; i < mock.call_count; i++) {
        if (mock.calls[i].is_write && mock.calls[i].reg == ADXL355_REG_RANGE) {
            found = 1;
            TEST_ASSERT(mock.calls[i].data == 0x01, "range register value should be 0x01 for 2G");
            break;
        }
    }
    TEST_ASSERT(found == 1, "write to RANGE register occurred");
    TEST_END();
}

static void test_set_range_preserves_unrelated_bits(void)
{
    TEST_START("set_range_preserves_unrelated_bits");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    mock.regs[ADXL355_REG_RANGE] = 0xC1;
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    TEST_ASSERT(adxl355_set_range(&dev, ADXL355_RANGE_4G) == ADXL355_OK,
                "set_range should succeed");
    TEST_ASSERT(mock.regs[ADXL355_REG_RANGE] == 0xC2,
                "RANGE should preserve I2C_HS and INT_POL bits");
    TEST_ASSERT(dev.range == ADXL355_RANGE_4G, "cached range should update after write");
    TEST_END();
}

static void test_set_range_read_error_prevents_write(void)
{
    TEST_START("set_range_read_error_prevents_write");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    mock.regs[ADXL355_REG_RANGE] = 0xC1;
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    size_t call_count_before = mock.call_count;
    mock.force_read_error = 1;
    TEST_ASSERT(adxl355_set_range(&dev, ADXL355_RANGE_4G) == ADXL355_ERR_BUS,
                "read failure should return bus error");
    TEST_ASSERT(mock.call_count == call_count_before, "read failure should prevent a write");
    TEST_ASSERT(mock.regs[ADXL355_REG_RANGE] == 0xC1, "RANGE register should remain unchanged");
    TEST_ASSERT(dev.range == ADXL355_RANGE_2G, "cached range should remain unchanged");
    TEST_END();
}

static void test_set_range_write_error_preserves_cache(void)
{
    TEST_START("set_range_write_error_preserves_cache");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    mock.regs[ADXL355_REG_RANGE] = 0xC1;
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    mock.force_write_error = 1;
    TEST_ASSERT(adxl355_set_range(&dev, ADXL355_RANGE_4G) == ADXL355_ERR_BUS,
                "write failure should return bus error");
    TEST_ASSERT(mock.regs[ADXL355_REG_RANGE] == 0xC1, "RANGE register should remain unchanged");
    TEST_ASSERT(dev.range == ADXL355_RANGE_2G, "cached range should remain unchanged");
    TEST_END();
}

static void test_read_raw_reads_9_bytes(void)
{
    TEST_START("read_raw_reads_9_bytes");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_mock_bus_set_xyz_raw(&mock, 10, -20, 30);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    adxl355_raw_xyz_t raw;
    adxl355_status_t status = adxl355_read_raw(&dev, &raw);
    TEST_ASSERT(status == ADXL355_OK, "read_raw should succeed");
    TEST_ASSERT(raw.x == 10, "x should be 10");
    TEST_ASSERT(raw.y == -20, "y should be -20");
    TEST_ASSERT(raw.z == 30, "z should be 30");
    TEST_END();
}

static void test_status_string(void)
{
    TEST_START("status_string");
    TEST_ASSERT(strcmp(adxl355_status_string(ADXL355_OK), "ADXL355_OK") == 0, "OK string");
    TEST_ASSERT(strcmp(adxl355_status_string(ADXL355_ERR_BUS), "ADXL355_ERR_BUS") == 0, "BUS string");
    TEST_ASSERT(adxl355_status_string((adxl355_status_t)-99) != NULL, "unknown returns something");
    TEST_END();
}

static void test_set_power_mode(void)
{
    TEST_START("set_power_mode");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    /* Write to power ctl should succeed */
    TEST_ASSERT(adxl355_set_power_mode(&dev, ADXL355_POWER_MEASUREMENT) == ADXL355_OK, "set measurement mode");
    TEST_ASSERT(adxl355_set_power_mode(&dev, ADXL355_POWER_STANDBY) == ADXL355_OK, "set standby mode");
    TEST_END();
}

static void test_reset(void)
{
    TEST_START("reset");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    TEST_ASSERT(adxl355_reset(&dev) == ADXL355_OK, "reset should succeed");

    /* Verify reset register was written */
    int found = 0;
    for (size_t i = 0; i < mock.call_count; i++) {
        if (mock.calls[i].is_write && mock.calls[i].reg == ADXL355_REG_RESET) {
            found = 1;
            TEST_ASSERT(mock.calls[i].data == ADXL355_RESET_CODE, "reset code 0x52");
            break;
        }
    }
    TEST_ASSERT(found == 1, "write to RESET register occurred");
    TEST_ASSERT(dev.range == ADXL355_RANGE_2G, "reset range should be 2g");
    TEST_END();
}

/* ---------------------------------------------------------------------------
 * Additional tests (Stage 3 coverage expansion)
 * --------------------------------------------------------------------------- */

typedef struct {
    uint8_t responses[8][2];
    size_t lengths[8];
    size_t response_count;
    size_t response_index;
} temperature_script_bus_t;

static int temperature_script_read(void *ctx, uint8_t reg, uint8_t *data, size_t len)
{
    temperature_script_bus_t *script = (temperature_script_bus_t *)ctx;
    if (reg != ADXL355_REG_TEMP2 || script->response_index >= script->response_count) {
        return -1;
    }
    size_t response_length = script->lengths[script->response_index];
    size_t copy_length = response_length < len ? response_length : len;
    memcpy(data, script->responses[script->response_index], copy_length);
    script->response_index++;
    return response_length <= (size_t)INT_MAX ? (int)response_length : -1;
}

static int temperature_script_write(void *ctx, uint8_t reg, const uint8_t *data, size_t len)
{
    (void)ctx;
    (void)reg;
    (void)data;
    return len <= (size_t)INT_MAX ? (int)len : -1;
}

static adxl355_t temperature_script_device(temperature_script_bus_t *script)
{
    adxl355_bus_t bus = {
        .read = temperature_script_read,
        .write = temperature_script_write,
        .delay_ms = NULL,
        .ctx = script,
    };
    adxl355_t dev;
    (void)adxl355_init(&dev, &bus);
    /* This focused transport only scripts TEMP2 reads; model a successful probe. */
    dev.initialized = true;
    return dev;
}

static void test_temperature_reserved_nibble_ignored(void)
{
    TEST_START("temperature_reserved_nibble_ignored");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    mock.regs[ADXL355_REG_TEMP2] = 0xF7;
    mock.regs[ADXL355_REG_TEMP1] = 0x5D;
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    int16_t raw;
    TEST_ASSERT(adxl355_read_temperature_raw(&dev, &raw) == ADXL355_OK,
                "temperature read should succeed");
    TEST_ASSERT(raw == 1885, "reserved TEMP2 high bits should be ignored");
    TEST_END();
}

static void test_temperature_short_read_returns_bus_error(void)
{
    TEST_START("temperature_short_read_returns_bus_error");
    temperature_script_bus_t script = {0};
    script.responses[0][0] = 0x07;
    script.lengths[0] = 1U;
    script.response_count = 1U;
    adxl355_t dev = temperature_script_device(&script);
    int16_t raw = 1234;

    TEST_ASSERT(adxl355_read_temperature_raw(&dev, &raw) == ADXL355_ERR_BUS,
                "short temperature read should return bus error");
    TEST_ASSERT(raw == 1234, "short read should not modify output");
    TEST_END();
}

static void test_temperature_retries_on_high_byte_rollover(void)
{
    TEST_START("temperature_retries_on_high_byte_rollover");
    temperature_script_bus_t script = {0};
    const uint8_t responses[][2] = {
        {0x07, 0xFF}, {0x08, 0x00},
        {0x08, 0x00}, {0x08, 0x00},
    };
    const size_t lengths[] = {2U, 1U, 2U, 1U};
    memcpy(script.responses, responses, sizeof(responses));
    memcpy(script.lengths, lengths, sizeof(lengths));
    script.response_count = 4U;
    adxl355_t dev = temperature_script_device(&script);
    int16_t raw = 0;

    TEST_ASSERT(adxl355_read_temperature_raw(&dev, &raw) == ADXL355_OK,
                "rollover should be retried");
    TEST_ASSERT(raw == 2048, "retry should return coherent second sample");
    TEST_END();
}

static void test_temperature_unstable_sample_returns_not_ready(void)
{
    TEST_START("temperature_unstable_sample_returns_not_ready");
    temperature_script_bus_t script = {0};
    const uint8_t responses[][2] = {
        {0x07, 0xFF}, {0x08, 0x00},
        {0x08, 0xFF}, {0x09, 0x00},
        {0x09, 0xFF}, {0x0A, 0x00},
    };
    const size_t lengths[] = {2U, 1U, 2U, 1U, 2U, 1U};
    memcpy(script.responses, responses, sizeof(responses));
    memcpy(script.lengths, lengths, sizeof(lengths));
    script.response_count = 6U;
    adxl355_t dev = temperature_script_device(&script);
    int16_t raw = 321;

    TEST_ASSERT(adxl355_read_temperature_raw(&dev, &raw) == ADXL355_ERR_NOT_READY,
                "unstable temperature should return not ready");
    TEST_ASSERT(raw == 321, "unstable read should not modify output");
    TEST_END();
}

static void test_temperature_raw(void)
{
    TEST_START("temperature_raw");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    /* Set TEMP2=0x01, TEMP1=0x90 => raw = 0x0190 */
    mock.regs[ADXL355_REG_TEMP2] = 0x01;
    mock.regs[ADXL355_REG_TEMP1] = 0x90;

    int16_t raw;
    adxl355_status_t status = adxl355_read_temperature_raw(&dev, &raw);
    TEST_ASSERT(status == ADXL355_OK, "read temperature raw should succeed");
    TEST_ASSERT(raw == 0x0190, "raw temperature should be 0x0190");
    TEST_END();
}

static void test_temperature_boundaries(void)
{
    TEST_START("temperature_boundaries");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");
    int16_t raw;
    float temp;

    mock.regs[ADXL355_REG_TEMP2] = 0x00;
    mock.regs[ADXL355_REG_TEMP1] = 0x00;
    TEST_ASSERT(adxl355_read_temperature_raw(&dev, &raw) == ADXL355_OK && raw == 0,
                "minimum temperature raw value should be 0");

    mock.regs[ADXL355_REG_TEMP2] = 0x0F;
    mock.regs[ADXL355_REG_TEMP1] = 0xFF;
    TEST_ASSERT(adxl355_read_temperature_raw(&dev, &raw) == ADXL355_OK && raw == 4095,
                "maximum temperature raw value should be 4095");
    TEST_ASSERT(adxl355_read_temperature_c(&dev, &temp) == ADXL355_OK,
                "maximum temperature conversion should succeed");
    TEST_ASSERT(approx_eq(temp, -219.1989f, 0.01f),
                "maximum raw temperature should match shared vector");
    TEST_END();
}

static void test_temperature_celsius(void)
{
    TEST_START("temperature_celsius");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    /* raw = 1885 (0x075D) => 25.0 C (datasheet nominal intercept) */
    mock.regs[ADXL355_REG_TEMP2] = 0x07;
    mock.regs[ADXL355_REG_TEMP1] = 0x5D;

    float temp;
    adxl355_status_t status = adxl355_read_temperature_c(&dev, &temp);
    TEST_ASSERT(status == ADXL355_OK, "read temperature C should succeed");
    TEST_ASSERT(approx_eq(temp, 25.0f, 0.01f), "raw=1885 should give ~25.0 C");
    TEST_END();
}

static void test_temperature_celsius_zero(void)
{
    TEST_START("temperature_celsius_zero");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    /* raw = 0 => expected = 25 + (0 - 1885) / -9.05 ≈ 233.29 C */
    mock.regs[ADXL355_REG_TEMP2] = 0x00;
    mock.regs[ADXL355_REG_TEMP1] = 0x00;

    float temp;
    adxl355_read_temperature_c(&dev, &temp);
    TEST_ASSERT(approx_eq(temp, 233.287f, 0.01f), "raw=0 should give ~233.29 C");
    TEST_END();
}

static void test_read_status(void)
{
    TEST_START("read_status");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    /* Set STATUS register with known pattern */
    mock.regs[ADXL355_REG_STATUS] = 0x1F; /* all 5 bits set */

    uint8_t status;
    adxl355_status_t result = adxl355_read_status(&dev, &status);
    TEST_ASSERT(result == ADXL355_OK, "read status should succeed");
    TEST_ASSERT(status == 0x1F, "status should be 0x1F");
    TEST_END();
}

static void test_read_status_data_rdy(void)
{
    TEST_START("read_status_data_rdy");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    /* Set only DATA_RDY bit */
    mock.regs[ADXL355_REG_STATUS] = ADXL355_STATUS_DATA_RDY;

    uint8_t status;
    adxl355_read_status(&dev, &status);
    TEST_ASSERT(status & ADXL355_STATUS_DATA_RDY, "DATA_RDY bit should be set");
    TEST_ASSERT(!(status & ADXL355_STATUS_FIFO_FULL), "FIFO_FULL bit should be clear");
    TEST_END();
}

static void test_read_fifo_entries(void)
{
    TEST_START("read_fifo_entries");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    /* Set FIFO_ENTRIES register */
    mock.regs[ADXL355_REG_FIFO_ENTRIES] = 0x2A;

    /* Read via raw bus access (no read_fifo_entries API in C, so verify bus read) */
    uint8_t val;
    bus.read(bus.ctx, ADXL355_REG_FIFO_ENTRIES, &val, 1);
    TEST_ASSERT(val == 0x2A, "FIFO_ENTRIES should be 0x2A");
    TEST_END();
}

static void test_filter_register_odr(void)
{
    TEST_START("filter_register_odr");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    /* Set FILTER with HPF=5 in bits 6:4, ODR=0 */
    mock.regs[ADXL355_REG_FILTER] = 0x50;

    /* Set ODR to 5 (HZ_125) */
    TEST_ASSERT(adxl355_set_odr(&dev, ADXL355_ODR_125_HZ) == ADXL355_OK, "set ODR");

    /* Read back FILTER register */
    uint8_t val;
    bus.read(bus.ctx, ADXL355_REG_FILTER, &val, 1);
    /* HPF bits 6:4 should be preserved (0x50), ODR bits 3:0 = 0x05 */
    TEST_ASSERT(val == 0x55, "FILTER should be 0x55 (HPF=5, ODR=5)");
    TEST_END();
}

static void test_filter_hpf_preserved(void)
{
    TEST_START("filter_hpf_preserved");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    /* Set FILTER with bits 6:4 = 111 (HPF=7), ODR=0 */
    mock.regs[ADXL355_REG_FILTER] = 0x70;

    /* Set ODR to 0 (4000 Hz) */
    adxl355_set_odr(&dev, ADXL355_ODR_4000_HZ);

    uint8_t val;
    bus.read(bus.ctx, ADXL355_REG_FILTER, &val, 1);
    TEST_ASSERT((val & ADXL355_FILTER_HPF_MASK) == 0x70, "HPF bits should be preserved");
    TEST_ASSERT((val & ADXL355_FILTER_ODR_MASK) == 0x00, "ODR bits should be 0");
    TEST_END();
}

static void test_bus_error_probe(void)
{
    TEST_START("bus_error_probe");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    mock.force_error = 1;
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_ERR_BUS, "probe should fail with bus error");
    TEST_END();
}

static void test_bus_error_read_raw(void)
{
    TEST_START("bus_error_read_raw");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    mock.force_error = 1;
    adxl355_raw_xyz_t raw;
    TEST_ASSERT(adxl355_read_raw(&dev, &raw) == ADXL355_ERR_BUS, "read_raw should fail with bus error");
    TEST_END();
}

static void test_bus_error_set_range(void)
{
    TEST_START("bus_error_set_range");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_probe(&dev);

    mock.force_error = 1;
    TEST_ASSERT(adxl355_set_range(&dev, ADXL355_RANGE_2G) == ADXL355_ERR_BUS,
                "set_range should fail with bus error");
    TEST_END();
}

static void test_decode_half_scale_positive(void)
{
    TEST_START("decode_half_scale_positive");
    int32_t v = adxl355_decode_raw20(64, 0, 0);
    TEST_ASSERT(v == 262144, "64,0,0 should decode to 262144");
    TEST_END();
}

static void test_decode_half_scale_negative(void)
{
    TEST_START("decode_half_scale_negative");
    int32_t v = adxl355_decode_raw20(192, 0, 0);
    TEST_ASSERT(v == -262144, "192,0,0 should decode to -262144");
    TEST_END();
}

/* ---------------------------------------------------------------------------
 * Main
 * --------------------------------------------------------------------------- */

static void test_transport_contract_single_register_exact_length(void)
{
    TEST_START("transport_contract_single_register_exact_length");
    const size_t returned_lengths[] = {0U, 2U};
    for (size_t i = 0U; i < 2U; i++) {
        adxl355_mock_bus_t mock;
        adxl355_mock_bus_init(&mock);
        adxl355_mock_bus_set_identity_ok(&mock);
        mock.short_read_reg = ADXL355_REG_DEVID_AD;
        mock.short_read_length = returned_lengths[i];
        adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
        adxl355_t dev;
        adxl355_init(&dev, &bus);
        TEST_ASSERT(adxl355_probe(&dev) == ADXL355_ERR_BUS,
                    "TR-1 zero/overlong response should be a bus error");
    }
    TEST_END();
}

static void test_transport_contract_temperature_exact_length(void)
{
    TEST_START("transport_contract_temperature_exact_length");
    for (size_t returned = 0U; returned <= 1U; returned++) {
        adxl355_mock_bus_t mock;
        adxl355_mock_bus_init(&mock);
        adxl355_mock_bus_set_identity_ok(&mock);
        adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
        adxl355_t dev;
        adxl355_init(&dev, &bus);
        TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");
        mock.short_read_reg = ADXL355_REG_TEMP2;
        mock.short_read_length = returned;
        int16_t raw = 1234;
        TEST_ASSERT(adxl355_read_temperature_raw(&dev, &raw) == ADXL355_ERR_BUS,
                    "TR-2 zero/truncated response should be a bus error");
        TEST_ASSERT(raw == 1234, "short read must not fabricate temperature output");
    }
    TEST_END();
}

static void test_transport_contract_xyz_exact_length(void)
{
    TEST_START("transport_contract_xyz_exact_length");
    const size_t returned_lengths[] = {0U, 8U};
    for (size_t i = 0U; i < 2U; i++) {
        adxl355_mock_bus_t mock;
        adxl355_mock_bus_init(&mock);
        adxl355_mock_bus_set_identity_ok(&mock);
        adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
        adxl355_t dev;
        adxl355_init(&dev, &bus);
        TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");
        mock.short_read_reg = ADXL355_REG_XDATA3;
        mock.short_read_length = returned_lengths[i];
        adxl355_raw_xyz_t raw = {11, 22, 33};
        TEST_ASSERT(adxl355_read_raw(&dev, &raw) == ADXL355_ERR_BUS,
                    "TR-9 zero/truncated response should be a bus error");
        TEST_ASSERT(raw.x == 11 && raw.y == 22 && raw.z == 33,
                    "short read must not fabricate acceleration output");
    }
    TEST_END();
}


static void test_calculate_offset_rounding_and_saturation(void)
{
    TEST_START("calculate_offset_rounding_and_saturation");
    int16_t offset = 123;
    TEST_ASSERT(adxl355_calculate_offset(1000, 1007, 0, false, &offset) == ADXL355_OK,
                "positive value below half count should succeed");
    TEST_ASSERT(offset == 0, "+7 raw LSB should round to zero");
    TEST_ASSERT(adxl355_calculate_offset(1000, 1008, 0, false, &offset) == ADXL355_OK,
                "positive half count should succeed");
    TEST_ASSERT(offset == -1, "+8 expected-minus-measured should program -1");
    TEST_ASSERT(adxl355_calculate_offset(1000, 993, 0, false, &offset) == ADXL355_OK,
                "negative value above half count should succeed");
    TEST_ASSERT(offset == 0, "-7 raw LSB should round to zero");
    TEST_ASSERT(adxl355_calculate_offset(1000, 992, 0, false, &offset) == ADXL355_OK,
                "negative half count should succeed");
    TEST_ASSERT(offset == 1, "-8 expected-minus-measured should program +1");
    TEST_ASSERT(adxl355_calculate_offset(1000, 1008, 100, false, &offset) == ADXL355_OK,
                "existing offset should be included");
    TEST_ASSERT(offset == 99, "helper should return the new absolute offset");

    offset = 77;
    TEST_ASSERT(adxl355_calculate_offset(-524288, 524287, 0, false, &offset) ==
                    ADXL355_ERR_INVALID_ARG,
                "strict overflow should be rejected");
    TEST_ASSERT(offset == 77, "rejected calculation must not modify output");
    TEST_ASSERT(adxl355_calculate_offset(-524288, 524287, 0, true, &offset) == ADXL355_OK,
                "negative overflow should saturate when requested");
    TEST_ASSERT(offset == INT16_MIN, "negative saturation should clamp to INT16_MIN");
    TEST_ASSERT(adxl355_calculate_offset(524287, -524288, 0, true, &offset) == ADXL355_OK,
                "positive overflow should saturate when requested");
    TEST_ASSERT(offset == INT16_MAX, "positive saturation should clamp to INT16_MAX");
    TEST_ASSERT(adxl355_calculate_offset(524288, 0, 0, false, &offset) ==
                    ADXL355_ERR_INVALID_ARG,
                "out-of-range raw input should be rejected");
    TEST_END();
}

static void test_offset_read_write_and_state_restore(void)
{
    TEST_START("offset_read_write_and_state_restore");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");

    mock.regs[ADXL355_REG_OFFSET_Y_H] = 0xFE;
    mock.regs[ADXL355_REG_OFFSET_Y_L] = 0xDC;
    int16_t offset = 0;
    TEST_ASSERT(adxl355_read_offset(&dev, ADXL355_AXIS_Y, &offset) == ADXL355_OK,
                "signed offset read should succeed");
    TEST_ASSERT(offset == -292, "0xFEDC should decode as -292");

    mock.regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;
    mock.call_count = 0U;
    TEST_ASSERT(adxl355_write_offset(&dev, ADXL355_AXIS_X, -1234) == ADXL355_OK,
                "signed offset write should succeed");
    TEST_ASSERT(mock.regs[ADXL355_REG_OFFSET_X_H] == 0xFB &&
                    mock.regs[ADXL355_REG_OFFSET_X_L] == 0x2E,
                "offset should be written big-endian in one register burst");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_MEASUREMENT,
                "measurement mode should be restored");
    TEST_ASSERT(mock.call_count == 4U, "write should read power, enter standby, write offset, restore");
    TEST_ASSERT(mock.calls[2].is_write && mock.calls[2].reg == ADXL355_REG_OFFSET_X_H &&
                    mock.calls[2].len == 2U,
                "offset write should use one two-byte transaction");
    TEST_END();
}

static void test_offset_failures_are_state_safe(void)
{
    TEST_START("offset_failures_are_state_safe");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");
    mock.regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;
    mock.fail_write_reg = ADXL355_REG_OFFSET_Z_H;
    TEST_ASSERT(adxl355_write_offset(&dev, ADXL355_AXIS_Z, 100) == ADXL355_ERR_BUS,
                "target write failure should be reported");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_MEASUREMENT,
                "target failure should restore measurement mode");
    TEST_ASSERT(mock.regs[ADXL355_REG_OFFSET_Z_H] == 0U &&
                    mock.regs[ADXL355_REG_OFFSET_Z_L] == 0U,
                "target failure must not modify offset registers");

    adxl355_mock_bus_init(&mock);
    adxl355_mock_bus_set_identity_ok(&mock);
    bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_init(&dev, &bus);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "second probe should succeed");
    mock.regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;
    mock.fail_write_reg = ADXL355_REG_POWER_CTL;
    mock.fail_write_occurrence = 2U;
    TEST_ASSERT(adxl355_write_offset(&dev, ADXL355_AXIS_Z, 100) == ADXL355_ERR_BUS,
                "restore failure should be reported");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_STANDBY,
                "restore failure should leave hardware in safe standby");
    TEST_ASSERT(mock.regs[ADXL355_REG_OFFSET_Z_H] == 0x00U &&
                    mock.regs[ADXL355_REG_OFFSET_Z_L] == 0x64U,
                "successful target write remains applied when restore fails");
    TEST_END();
}

static void test_offset_argument_and_lifecycle_validation(void)
{
    TEST_START("offset_argument_and_lifecycle_validation");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    int16_t offset = 44;
    TEST_ASSERT(adxl355_read_offset(&dev, ADXL355_AXIS_X, &offset) == ADXL355_ERR_STATE,
                "pre-probe read should fail without bus access");
    TEST_ASSERT(adxl355_write_offset(&dev, ADXL355_AXIS_X, 0) == ADXL355_ERR_STATE,
                "pre-probe write should fail without bus access");
    TEST_ASSERT(mock.call_count == 0U, "pre-probe offset operations must not touch bus");

    adxl355_mock_bus_set_identity_ok(&mock);
    TEST_ASSERT(adxl355_probe(&dev) == ADXL355_OK, "probe should succeed");
    TEST_ASSERT(adxl355_read_offset(&dev, (adxl355_axis_t)99, &offset) ==
                    ADXL355_ERR_INVALID_ARG,
                "invalid axis should be rejected");
    TEST_ASSERT(adxl355_read_offset(&dev, ADXL355_AXIS_X, NULL) == ADXL355_ERR_NULL,
                "null output should be rejected");
    TEST_END();
}


static void prepare_data_ready_fixture(adxl355_mock_bus_t *mock,
                                       adxl355_t *dev,
                                       adxl355_bus_t *bus)
{
    adxl355_mock_bus_init(mock);
    adxl355_mock_bus_set_identity_ok(mock);
    mock->regs[ADXL355_REG_RANGE] = (uint8_t)(0xA0U | ADXL355_RANGE_4G);
    mock->regs[ADXL355_REG_POWER_CTL] = 0x82U;
    mock->regs[ADXL355_REG_INT_MAP] = 0x88U;
    mock->regs[ADXL355_REG_SYNC] = 0U;
    *bus = adxl355_mock_bus_get_interface(mock);
    (void)adxl355_init(dev, bus);
    (void)adxl355_probe(dev);
    mock->regs[ADXL355_REG_POWER_CTL] = 0x82U;
    mock->call_count = 0U;
}

static void test_data_ready_defaults_and_configuration(void)
{
    TEST_START("data_ready_defaults_and_configuration");
    adxl355_data_ready_config_t config;
    TEST_ASSERT(adxl355_data_ready_config_default(&config) == ADXL355_OK,
                "default data-ready configuration should succeed");
    TEST_ASSERT(config.dedicated_drdy_enabled && !config.route_to_int1 &&
                    !config.route_to_int2 &&
                    config.interrupt_polarity == ADXL355_INTERRUPT_ACTIVE_LOW,
                "default should use dedicated active-high DRDY only");

    adxl355_mock_bus_t mock;
    adxl355_bus_t bus;
    adxl355_t dev;
    prepare_data_ready_fixture(&mock, &dev, &bus);
    config.dedicated_drdy_enabled = false;
    config.route_to_int1 = true;
    config.route_to_int2 = true;
    config.interrupt_polarity = ADXL355_INTERRUPT_ACTIVE_HIGH;

    TEST_ASSERT(adxl355_configure_data_ready(&dev, &config) == ADXL355_OK,
                "data-ready configuration should succeed");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == 0x86U,
                "DRDY_OFF and measurement mode should be preserved exactly");
    TEST_ASSERT(mock.regs[ADXL355_REG_RANGE] == 0xE2U,
                "INT_POL should change without altering I2C/range/reserved bits");
    TEST_ASSERT(mock.regs[ADXL355_REG_INT_MAP] == 0x99U,
                "DATA_RDY routes should preserve unrelated interrupt mappings");

    size_t status_reads = 0U;
    for (size_t index = 0U; index < mock.call_count &&
                           index < ADXL355_MOCK_MAX_CALLS; index++) {
        if (!mock.calls[index].is_write && mock.calls[index].reg == ADXL355_REG_STATUS) {
            status_reads++;
        }
    }
    TEST_ASSERT(status_reads == 0U,
                "configuration must not clear DATA_RDY by reading STATUS");

    adxl355_data_ready_config_t observed;
    TEST_ASSERT(adxl355_get_data_ready_config(&dev, &observed) == ADXL355_OK,
                "configured state should be readable");
    TEST_ASSERT(!observed.dedicated_drdy_enabled && observed.route_to_int1 &&
                    observed.route_to_int2 &&
                    observed.interrupt_polarity == ADXL355_INTERRUPT_ACTIVE_HIGH,
                "readback should distinguish DRDY from mapped DATA_RDY");
    TEST_END();
}

static void test_data_ready_external_timing_and_validation(void)
{
    TEST_START("data_ready_external_timing_and_validation");
    adxl355_mock_bus_t mock;
    adxl355_bus_t bus;
    adxl355_t dev;
    prepare_data_ready_fixture(&mock, &dev, &bus);
    mock.regs[ADXL355_REG_SYNC] = ADXL355_SYNC_EXT_SYNC_MASK;

    adxl355_data_ready_config_t config = {
        true, true, false, ADXL355_INTERRUPT_ACTIVE_LOW
    };
    TEST_ASSERT(adxl355_configure_data_ready(&dev, &config) == ADXL355_ERR_UNSUPPORTED,
                "external synchronization should be rejected");
    adxl355_data_ready_config_t sentinel = {
        false, false, true, ADXL355_INTERRUPT_ACTIVE_HIGH
    };
    TEST_ASSERT(adxl355_get_data_ready_config(&dev, &sentinel) == ADXL355_ERR_UNSUPPORTED,
                "readback should reject multiplexed timing modes");
    TEST_ASSERT(!sentinel.dedicated_drdy_enabled && !sentinel.route_to_int1 &&
                    sentinel.route_to_int2,
                "failed readback must not modify output");

    mock.regs[ADXL355_REG_SYNC] = 0U;
    config.interrupt_polarity = (adxl355_interrupt_polarity_t)7;
    TEST_ASSERT(adxl355_configure_data_ready(&dev, &config) == ADXL355_ERR_INVALID_ARG,
                "invalid polarity should be rejected");
    TEST_ASSERT(adxl355_data_ready_config_default(NULL) == ADXL355_ERR_NULL,
                "NULL default output should be rejected");
    TEST_END();
}

static void test_data_ready_failure_rollback(void)
{
    TEST_START("data_ready_failure_rollback");
    adxl355_mock_bus_t mock;
    adxl355_bus_t bus;
    adxl355_t dev;
    prepare_data_ready_fixture(&mock, &dev, &bus);
    const uint8_t original_power = mock.regs[ADXL355_REG_POWER_CTL];
    const uint8_t original_range = mock.regs[ADXL355_REG_RANGE];
    const uint8_t original_map = mock.regs[ADXL355_REG_INT_MAP];
    adxl355_data_ready_config_t config = {
        false, true, true, ADXL355_INTERRUPT_ACTIVE_HIGH
    };

    mock.fail_write_reg = ADXL355_REG_INT_MAP;
    mock.fail_write_occurrence = 1U;
    TEST_ASSERT(adxl355_configure_data_ready(&dev, &config) == ADXL355_ERR_BUS,
                "target failure with successful rollback should remain a bus error");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == original_power &&
                    mock.regs[ADXL355_REG_RANGE] == original_range &&
                    mock.regs[ADXL355_REG_INT_MAP] == original_map,
                "target failure should restore exact prior state");

    prepare_data_ready_fixture(&mock, &dev, &bus);
    mock.fail_write_reg = ADXL355_REG_INT_MAP;
    mock.fail_write_occurrence = 0U;
    TEST_ASSERT(adxl355_configure_data_ready(&dev, &config) == ADXL355_ERR_RESTORE,
                "rollback failure should be distinct");
    TEST_ASSERT((mock.regs[ADXL355_REG_POWER_CTL] & 0x01U) == 0U,
                "best-effort rollback should restore measurement mode");
    TEST_END();
}

static void prepare_self_test_fixture(adxl355_mock_bus_t *mock,
                                      adxl355_t *dev,
                                      adxl355_bus_t *bus)
{
    adxl355_mock_bus_init(mock);
    adxl355_mock_bus_set_identity_ok(mock);
    mock->regs[ADXL355_REG_RANGE] = (uint8_t)(UINT8_C(0x80) | ADXL355_RANGE_4G_VAL);
    mock->regs[ADXL355_REG_FILTER] = UINT8_C(0xA5);
    mock->regs[ADXL355_REG_POWER_CTL] = UINT8_C(0x04);
    adxl355_raw_xyz_t baseline = {100, -200, 300};
    adxl355_raw_xyz_t stimulated = {77023, -77123, 384915};
    adxl355_mock_bus_set_self_test_xyz(mock, baseline, stimulated);
    *bus = adxl355_mock_bus_get_interface(mock);
    TEST_ASSERT(adxl355_init(dev, bus) == ADXL355_OK, "self-test fixture init should succeed");
    TEST_ASSERT(adxl355_probe(dev) == ADXL355_OK, "self-test fixture probe should succeed");
}

static adxl355_self_test_config_t small_self_test_config(void)
{
    adxl355_self_test_config_t config;
    (void)adxl355_self_test_config_default(&config);
    config.sample_count = 4U;
    config.settle_samples = 1U;
    config.max_ready_polls = 4U;
    config.poll_delay_ms = 1U;
    return config;
}

static void test_self_test_default_and_validation(void)
{
    TEST_START("self_test_default_and_validation");
    adxl355_self_test_config_t config;
    TEST_ASSERT(adxl355_self_test_config_default(NULL) == ADXL355_ERR_NULL,
                "null default config should be rejected");
    TEST_ASSERT(adxl355_self_test_config_default(&config) == ADXL355_OK,
                "default config should succeed");
    TEST_ASSERT(config.sample_count == 32U && config.settle_samples == 4U,
                "default sample and settle counts should be bounded");
    TEST_ASSERT(config.max_ready_polls == 500U && config.poll_delay_ms == 1U,
                "default polling should be bounded");
    TEST_ASSERT(!config.enforce_thresholds,
                "datasheet typical values must not become default pass/fail thresholds");

    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
    adxl355_self_test_result_t result;
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_ERR_STATE,
                "pre-probe self-test should fail without bus access");
    TEST_ASSERT(mock.call_count == 0U, "pre-probe self-test must not touch bus");

    prepare_self_test_fixture(&mock, &dev, &bus);
    config.sample_count = 0U;
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_ERR_INVALID_ARG,
                "zero samples should be rejected");
    config = small_self_test_config();
    config.enforce_thresholds = true;
    config.thresholds.min_abs_delta_g.x = NAN;
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_ERR_INVALID_ARG,
                "non-finite threshold should be rejected");
    mock.regs[ADXL355_REG_SELF_TEST] = ADXL355_SELF_TEST_ST1;
    config = small_self_test_config();
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_ERR_STATE,
                "pre-existing self-test mode should be rejected");
    TEST_END();
}

static void test_self_test_measures_typical_response_and_restores_state(void)
{
    TEST_START("self_test_measures_typical_response_and_restores_state");
    adxl355_mock_bus_t mock;
    adxl355_t dev;
    adxl355_bus_t bus;
    prepare_self_test_fixture(&mock, &dev, &bus);
    const uint8_t original_range = mock.regs[ADXL355_REG_RANGE];
    const uint8_t original_filter = mock.regs[ADXL355_REG_FILTER];
    const uint8_t original_power = mock.regs[ADXL355_REG_POWER_CTL];
    const uint8_t original_self_test = mock.regs[ADXL355_REG_SELF_TEST];
    const adxl355_range_t original_cached_range = dev.range;
    adxl355_self_test_config_t config = small_self_test_config();
    adxl355_self_test_result_t result;

    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_OK,
                "self-test measurement should succeed");
    TEST_ASSERT(result.samples == config.sample_count, "result should record sample count");
    TEST_ASSERT(approx_eq(result.delta_g.x, 0.2999997f, 0.00002f),
                "X response should measure the 0.3 g typical fixture value");
    TEST_ASSERT(approx_eq(result.delta_g.y, -0.2999997f, 0.00002f),
                "Y signed response should be preserved");
    TEST_ASSERT(approx_eq(result.delta_g.z, 1.4999985f, 0.00002f),
                "Z response should measure the 1.5 g typical fixture value");
    TEST_ASSERT(approx_eq(result.abs_delta_g.y, 0.2999997f, 0.00002f),
                "absolute response should be available for policy checks");
    TEST_ASSERT(!result.thresholds_evaluated && result.thresholds_passed,
                "default run should report measurement without normative thresholds");
    TEST_ASSERT(mock.regs[ADXL355_REG_RANGE] == original_range &&
                    mock.regs[ADXL355_REG_FILTER] == original_filter &&
                    mock.regs[ADXL355_REG_POWER_CTL] == original_power &&
                    mock.regs[ADXL355_REG_SELF_TEST] == original_self_test,
                "all relevant registers should be restored exactly");
    TEST_ASSERT(dev.range == original_cached_range, "cached range should be restored");

    bool saw_mode = false;
    bool saw_enabled = false;
    for (size_t index = 0U; index < mock.call_count && index < ADXL355_MOCK_MAX_CALLS; index++) {
        if (mock.calls[index].is_write && mock.calls[index].reg == ADXL355_REG_SELF_TEST) {
            const uint8_t mode =
                (uint8_t)(mock.calls[index].data & ADXL355_SELF_TEST_MASK);
            saw_mode = saw_mode || mode == ADXL355_SELF_TEST_ST1;
            saw_enabled = saw_enabled || mode == ADXL355_SELF_TEST_MASK;
        }
    }
    TEST_ASSERT(saw_mode, "sequence should enter ST1-only mode before baseline");
    TEST_ASSERT(saw_enabled, "sequence should add ST2 after the ST1-only baseline");
    TEST_END();
}

static void test_self_test_threshold_policy(void)
{
    TEST_START("self_test_threshold_policy");
    adxl355_mock_bus_t mock;
    adxl355_t dev;
    adxl355_bus_t bus;
    prepare_self_test_fixture(&mock, &dev, &bus);
    adxl355_self_test_config_t config = small_self_test_config();
    config.enforce_thresholds = true;
    config.thresholds.min_abs_delta_g = (adxl355_float_xyz_t){0.10f, 0.10f, 0.50f};
    config.thresholds.max_abs_delta_g = (adxl355_float_xyz_t){0.60f, 0.60f, 3.00f};
    adxl355_self_test_result_t result;
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_OK,
                "caller fixture policy should pass representative response");
    TEST_ASSERT(result.thresholds_evaluated && result.thresholds_passed,
                "passing caller thresholds should be recorded");

    config.thresholds.min_abs_delta_g.x = 0.31f;
    config.thresholds.max_abs_delta_g.x = 0.60f;
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_ERR_THRESHOLD,
                "caller threshold violation should be distinct");
    TEST_ASSERT(result.thresholds_evaluated && !result.thresholds_passed,
                "failed result should remain populated");
    TEST_ASSERT(result.abs_delta_g.x > 0.29f,
                "threshold failure should retain measured response");
    TEST_ASSERT(mock.regs[ADXL355_REG_SELF_TEST] == 0U,
                "threshold failure should still restore self-test register");
    TEST_END();
}

static void test_self_test_timeout_and_short_read_restore(void)
{
    TEST_START("self_test_timeout_and_short_read_restore");
    adxl355_mock_bus_t mock;
    adxl355_t dev;
    adxl355_bus_t bus;
    prepare_self_test_fixture(&mock, &dev, &bus);
    adxl355_self_test_config_t config = small_self_test_config();
    config.sample_count = 1U;
    config.settle_samples = 0U;
    config.max_ready_polls = 2U;
    adxl355_self_test_result_t result;
    const uint8_t original_power = mock.regs[ADXL355_REG_POWER_CTL];

    mock.regs[ADXL355_REG_STATUS] = 0U;
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_ERR_TIMEOUT,
                "missing DATA_RDY should produce a bounded timeout");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == original_power &&
                    mock.regs[ADXL355_REG_SELF_TEST] == 0U,
                "timeout should restore power and self-test state");

    mock.regs[ADXL355_REG_STATUS] = ADXL355_STATUS_DATA_RDY;
    mock.short_read_reg = ADXL355_REG_XDATA3;
    mock.short_read_length = 8U;
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_ERR_BUS,
                "short XYZ response should be reported as transport failure");
    TEST_ASSERT(mock.regs[ADXL355_REG_POWER_CTL] == original_power &&
                    mock.regs[ADXL355_REG_SELF_TEST] == 0U,
                "short response should restore hardware state");
    TEST_END();
}

static void test_self_test_target_and_restore_failures(void)
{
    TEST_START("self_test_target_and_restore_failures");
    adxl355_mock_bus_t mock;
    adxl355_t dev;
    adxl355_bus_t bus;
    prepare_self_test_fixture(&mock, &dev, &bus);
    adxl355_self_test_config_t config = small_self_test_config();
    config.sample_count = 1U;
    config.settle_samples = 0U;
    adxl355_self_test_result_t result;
    const uint8_t original_range = mock.regs[ADXL355_REG_RANGE];
    const uint8_t original_filter = mock.regs[ADXL355_REG_FILTER];
    const uint8_t original_power = mock.regs[ADXL355_REG_POWER_CTL];

    mock.fail_write_reg = ADXL355_REG_SELF_TEST;
    mock.fail_write_occurrence = 3U;
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_ERR_BUS,
                "ST1/ST2 enable failure should preserve operation error");
    TEST_ASSERT(mock.regs[ADXL355_REG_RANGE] == original_range &&
                    mock.regs[ADXL355_REG_FILTER] == original_filter &&
                    mock.regs[ADXL355_REG_POWER_CTL] == original_power &&
                    mock.regs[ADXL355_REG_SELF_TEST] == 0U,
                "target failure should restore all state");

    prepare_self_test_fixture(&mock, &dev, &bus);
    mock.fail_write_reg = ADXL355_REG_POWER_CTL;
    mock.fail_write_occurrence = 4U;
    TEST_ASSERT(adxl355_run_self_test(&dev, &config, &result) == ADXL355_ERR_RESTORE,
                "restore failure should take precedence");
    TEST_ASSERT(mock.regs[ADXL355_REG_SELF_TEST] == 0U,
                "restore failure must still disable ST1/ST2");
    TEST_ASSERT((mock.regs[ADXL355_REG_POWER_CTL] & (1U << ADXL355_POWER_MODE_BIT)) != 0U,
                "failed final power restore should leave safe standby");
    TEST_ASSERT(dev.range == ADXL355_RANGE_4G, "cached range should still be restored");
    TEST_END();
}


static void prepare_fifo_fixture(adxl355_mock_bus_t *mock,
                                 adxl355_t *dev,
                                 adxl355_bus_t *bus)
{
    adxl355_mock_bus_init(mock);
    adxl355_mock_bus_set_identity_ok(mock);
    *bus = adxl355_mock_bus_get_interface(mock);
    (void)adxl355_init(dev, bus);
    (void)adxl355_probe(dev);
}

static void test_fifo_shared_decode_vectors(void)
{
    TEST_START("fifo_shared_decode_vectors");
    for (size_t i = 0U; i < FIFO_VALID_VECTOR_COUNT; i++) {
        adxl355_raw_xyz_t sample = {INT32_C(99), INT32_C(99), INT32_C(99)};
        adxl355_status_t status = adxl355_decode_fifo_sample(
            FIFO_VALID_VECTORS[i].bytes, ADXL355_FIFO_BYTES_PER_SAMPLE, &sample);
        TEST_ASSERT(status == ADXL355_OK, FIFO_VALID_VECTORS[i].name);
        TEST_ASSERT(sample.x == FIFO_VALID_VECTORS[i].x,
                    "FIFO x must match shared vector");
        TEST_ASSERT(sample.y == FIFO_VALID_VECTORS[i].y,
                    "FIFO y must match shared vector");
        TEST_ASSERT(sample.z == FIFO_VALID_VECTORS[i].z,
                    "FIFO z must match shared vector");
    }
    for (size_t i = 0U; i < FIFO_INVALID_VECTOR_COUNT; i++) {
        adxl355_raw_xyz_t sample = {INT32_C(11), INT32_C(22), INT32_C(33)};
        adxl355_status_t expected = ADXL355_ERR_FIFO_FORMAT;
        if (FIFO_INVALID_VECTORS[i].expected_error == FIFO_VECTOR_ERROR_LENGTH) {
            expected = ADXL355_ERR_INVALID_ARG;
        } else if (FIFO_INVALID_VECTORS[i].expected_error == FIFO_VECTOR_ERROR_EMPTY) {
            expected = ADXL355_ERR_FIFO_EMPTY;
        }
        adxl355_status_t status = adxl355_decode_fifo_sample(
            FIFO_INVALID_VECTORS[i].bytes,
            FIFO_INVALID_VECTORS[i].length,
            &sample);
        TEST_ASSERT(status == expected, FIFO_INVALID_VECTORS[i].name);
        TEST_ASSERT(sample.x == 11 && sample.y == 22 && sample.z == 33,
                    "failed FIFO decode must not modify output");
    }
    TEST_END();
}

static void test_fifo_read_bounded_and_partial_semantics(void)
{
    TEST_START("fifo_read_bounded_and_partial_semantics");
    adxl355_mock_bus_t mock;
    adxl355_bus_t bus;
    adxl355_t dev;
    prepare_fifo_fixture(&mock, &dev, &bus);

    uint8_t payload[18];
    memcpy(payload, FIFO_VALID_VECTORS[1].bytes, 9U);
    memcpy(&payload[9], FIFO_VALID_VECTORS[2].bytes, 9U);
    adxl355_mock_bus_set_fifo_payload(&mock, payload, sizeof(payload), 6U);

    adxl355_raw_xyz_t samples[2];
    adxl355_fifo_read_result_t result;
    TEST_ASSERT(adxl355_read_fifo_samples(&dev, samples, 1U, &result) == ADXL355_OK,
                "bounded FIFO read should succeed");
    TEST_ASSERT(result.available_locations == 6U && result.consumed_locations == 3U &&
                    result.remaining_locations == 3U && result.samples_read == 1U,
                "bounded FIFO metadata should preserve remaining locations");
    TEST_ASSERT(samples[0].x == 1 && samples[0].y == -1 && samples[0].z == 262144,
                "first bounded sample should decode");

    TEST_ASSERT(adxl355_read_fifo_samples(&dev, samples, 2U, &result) == ADXL355_OK,
                "second bounded read should consume remaining sample");
    TEST_ASSERT(result.available_locations == 3U && result.samples_read == 1U &&
                    result.remaining_locations == 0U,
                "second read should report one remaining sample");

    prepare_fifo_fixture(&mock, &dev, &bus);
    uint8_t partial_payload[18];
    memcpy(partial_payload, FIFO_VALID_VECTORS[0].bytes, 9U);
    memcpy(&partial_payload[9], FIFO_INVALID_VECTORS[2].bytes, 9U);
    adxl355_mock_bus_set_fifo_payload(&mock, partial_payload, sizeof(partial_payload), 6U);
    TEST_ASSERT(adxl355_read_fifo_samples(&dev, samples, 2U, &result) ==
                    ADXL355_ERR_FIFO_EMPTY,
                "empty marker after one sample should fail");
    TEST_ASSERT(result.samples_read == 1U && result.consumed_locations == 6U &&
                    result.remaining_locations == 0U,
                "partial FIFO result should retain valid prefix and physical consumption");
    TEST_END();
}

static void test_fifo_read_errors_and_transport_lengths(void)
{
    TEST_START("fifo_read_errors_and_transport_lengths");
    adxl355_mock_bus_t mock;
    adxl355_bus_t bus;
    adxl355_t dev;
    adxl355_raw_xyz_t samples[1];
    adxl355_fifo_read_result_t result;

    prepare_fifo_fixture(&mock, &dev, &bus);
    TEST_ASSERT(adxl355_read_fifo_samples(&dev, samples, 1U, &result) ==
                    ADXL355_ERR_FIFO_EMPTY,
                "zero FIFO entries should be empty");

    prepare_fifo_fixture(&mock, &dev, &bus);
    mock.regs[ADXL355_REG_STATUS] = ADXL355_STATUS_FIFO_OVR;
    adxl355_mock_bus_set_fifo_payload(&mock, FIFO_VALID_VECTORS[0].bytes, 9U, 3U);
    TEST_ASSERT(adxl355_read_fifo_samples(&dev, samples, 1U, &result) ==
                    ADXL355_ERR_FIFO_OVERRUN,
                "overrun should abort before FIFO_DATA read");
    TEST_ASSERT(mock.fifo_offset == 0U && result.consumed_locations == 0U,
                "overrun must not consume FIFO data");

    prepare_fifo_fixture(&mock, &dev, &bus);
    adxl355_mock_bus_set_fifo_payload(&mock, FIFO_VALID_VECTORS[0].bytes, 9U, 4U);
    TEST_ASSERT(adxl355_read_fifo_samples(&dev, samples, 1U, &result) == ADXL355_OK,
                "one trailing location should remain valid and unread");
    TEST_ASSERT(result.samples_read == 1U && result.remaining_locations == 1U,
                "valid FIFO remainder should be reported");
    mock.regs[ADXL355_REG_FIFO_ENTRIES] = 0x80U;
    uint8_t locations = 99U;
    TEST_ASSERT(adxl355_read_fifo_entries(&dev, &locations) == ADXL355_ERR_FIFO_FORMAT,
                "reserved FIFO_ENTRIES bit should be rejected");
    TEST_ASSERT(locations == 99U, "failed FIFO count read must not modify output");

    prepare_fifo_fixture(&mock, &dev, &bus);
    adxl355_mock_bus_set_fifo_payload(&mock, FIFO_VALID_VECTORS[0].bytes, 9U, 3U);
    mock.short_read_reg = ADXL355_REG_FIFO_DATA;
    mock.short_read_length = 8U;
    TEST_ASSERT(adxl355_read_fifo_samples(&dev, samples, 1U, &result) == ADXL355_ERR_BUS,
                "truncated FIFO transfer should normalize to bus error");
    TEST_ASSERT(result.samples_read == 0U, "truncated transfer has no decoded prefix");
    TEST_ASSERT(result.consumption_indeterminate,
                "failed FIFO_DATA transfer must mark consumption indeterminate");

    prepare_fifo_fixture(&mock, &dev, &bus);
    adxl355_mock_bus_set_fifo_payload(&mock, FIFO_VALID_VECTORS[0].bytes, 9U, 3U);
    mock.short_read_reg = ADXL355_REG_FIFO_DATA;
    mock.short_read_length = 10U;
    TEST_ASSERT(adxl355_read_fifo_samples(&dev, samples, 1U, &result) == ADXL355_ERR_BUS,
                "overlong FIFO transfer should normalize to bus error");
    TEST_ASSERT(result.consumption_indeterminate,
                "overlong FIFO_DATA transfer must mark consumption indeterminate");
    TEST_ASSERT(adxl355_read_fifo_samples(&dev, samples, 0U, &result) ==
                    ADXL355_ERR_INVALID_ARG,
                "zero capacity should be rejected");
    TEST_END();
}

int main(void)
{
    printf("ADXL355 C Test Suite\n");
    printf("====================\n");

    test_decode_raw20_zero();
    test_decode_raw20_positive_one();
    test_decode_raw20_positive_max();
    test_decode_raw20_negative_min();
    test_decode_raw20_negative_one();
    test_decode_half_scale_positive();
    test_decode_half_scale_negative();
    test_raw_to_g_2g();
    test_raw_to_g_4g();
    test_raw_to_g_8g();
    test_raw_to_mps2();
    test_init_null_args();
    test_init_defaults_to_2g();
    test_probe_bad_device();
    test_probe_synchronizes_range();
    test_probe_rejects_reserved_range();
    test_probe_reset_range_converts_one_g();
    test_probe_ok();
    test_pre_probe_operations_return_state_error();
    test_set_range_temporarily_enters_standby();
    test_set_range_in_standby_avoids_power_writes();
    test_set_range_failure_restores_measurement();
    test_set_range_restore_failure_keeps_range_cache_consistent();
    test_set_odr_temporarily_enters_standby();
    test_data_ready_defaults_and_configuration();
    test_data_ready_external_timing_and_validation();
    test_data_ready_failure_rollback();
    test_set_range_writes_expected_register();
    test_set_range_preserves_unrelated_bits();
    test_set_range_read_error_prevents_write();
    test_set_range_write_error_preserves_cache();
    test_read_raw_reads_9_bytes();
    test_status_string();
    test_set_power_mode();
    test_reset();
    test_temperature_reserved_nibble_ignored();
    test_temperature_short_read_returns_bus_error();
    test_temperature_retries_on_high_byte_rollover();
    test_temperature_unstable_sample_returns_not_ready();
    test_temperature_raw();
    test_temperature_boundaries();
    test_temperature_celsius();
    test_temperature_celsius_zero();
    test_read_status();
    test_read_status_data_rdy();
    test_read_fifo_entries();
    test_fifo_shared_decode_vectors();
    test_fifo_read_bounded_and_partial_semantics();
    test_fifo_read_errors_and_transport_lengths();
    test_filter_register_odr();
    test_filter_hpf_preserved();
    test_bus_error_probe();
    test_bus_error_read_raw();
    test_bus_error_set_range();
    test_transport_contract_single_register_exact_length();
    test_transport_contract_temperature_exact_length();
    test_transport_contract_xyz_exact_length();
    test_calculate_offset_rounding_and_saturation();
    test_offset_read_write_and_state_restore();
    test_offset_failures_are_state_safe();
    test_offset_argument_and_lifecycle_validation();
    test_self_test_default_and_validation();
    test_self_test_measures_typical_response_and_restores_state();
    test_self_test_threshold_policy();
    test_self_test_timeout_and_short_read_restore();
    test_self_test_target_and_restore_failures();

    printf("\n====================\n");
    printf("Results: %d/%d passed, %d failed\n",
           g_tests_pass, g_tests_run, g_tests_fail);

    return g_tests_fail > 0 ? EXIT_FAILURE : EXIT_SUCCESS;
}
