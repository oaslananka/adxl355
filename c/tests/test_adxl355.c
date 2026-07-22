#include "adxl355/adxl355.h"
#include "test_mock_bus.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

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
    return response_length == len ? 0 : -1;
}

static int temperature_script_write(void *ctx, uint8_t reg, const uint8_t *data, size_t len)
{
    (void)ctx;
    (void)reg;
    (void)data;
    (void)len;
    return 0;
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
    return dev;
}

static void test_temperature_reserved_nibble_ignored(void)
{
    TEST_START("temperature_reserved_nibble_ignored");
    adxl355_mock_bus_t mock;
    adxl355_mock_bus_init(&mock);
    mock.regs[ADXL355_REG_TEMP2] = 0xF7;
    mock.regs[ADXL355_REG_TEMP1] = 0x5D;
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);

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
    adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
    adxl355_t dev;
    adxl355_init(&dev, &bus);
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
    test_filter_register_odr();
    test_filter_hpf_preserved();
    test_bus_error_probe();
    test_bus_error_read_raw();
    test_bus_error_set_range();

    printf("\n====================\n");
    printf("Results: %d/%d passed, %d failed\n",
           g_tests_pass, g_tests_run, g_tests_fail);

    return g_tests_fail > 0 ? EXIT_FAILURE : EXIT_SUCCESS;
}
