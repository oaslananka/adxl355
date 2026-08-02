#include "adxl355/adxl355.h"

#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    const uint8_t *input;
    size_t size;
    size_t cursor;
    uint8_t registers[128];
} fuzz_bus_t;

static uint8_t next_byte(fuzz_bus_t *bus)
{
    if (bus->size == 0U) {
        return 0U;
    }
    const uint8_t value = bus->input[bus->cursor % bus->size];
    bus->cursor++;
    return value;
}

static int fuzz_read(void *ctx, uint8_t reg, uint8_t *data, size_t len)
{
    fuzz_bus_t *bus = (fuzz_bus_t *)ctx;
    const uint8_t mode = (uint8_t)(next_byte(bus) % 5U);
    for (size_t index = 0U; index < len; index++) {
        const size_t address = (size_t)reg + index;
        data[index] = address < sizeof(bus->registers)
                          ? bus->registers[address]
                          : next_byte(bus);
    }
    if (len > (size_t)INT_MAX) {
        return -1;
    }
    switch (mode) {
        case 0U:
            return (int)len;
        case 1U:
            return -1;
        case 2U:
            return 0;
        case 3U:
            return len == 0U ? 0 : (int)(len - 1U);
        default:
            return len == (size_t)INT_MAX ? -1 : (int)(len + 1U);
    }
}

static int fuzz_write(void *ctx, uint8_t reg, const uint8_t *data, size_t len)
{
    fuzz_bus_t *bus = (fuzz_bus_t *)ctx;
    const uint8_t mode = (uint8_t)(next_byte(bus) % 4U);
    for (size_t index = 0U; index < len; index++) {
        const size_t address = (size_t)reg + index;
        if (address < sizeof(bus->registers)) {
            bus->registers[address] = data[index];
        }
    }
    if (len > (size_t)INT_MAX) {
        return -1;
    }
    switch (mode) {
        case 0U:
            return (int)len;
        case 1U:
            return -1;
        case 2U:
            return len == 0U ? 0 : (int)(len - 1U);
        default:
            return len == (size_t)INT_MAX ? -1 : (int)(len + 1U);
    }
}

static void fuzz_delay(void *ctx, uint32_t milliseconds)
{
    fuzz_bus_t *bus = (fuzz_bus_t *)ctx;
    bus->cursor += (size_t)(milliseconds & UINT32_C(0x0F));
}

static void initialize_registers(fuzz_bus_t *bus)
{
    memset(bus->registers, 0, sizeof(bus->registers));
    bus->registers[ADXL355_REG_DEVID_AD] = ADXL355_DEVID_AD;
    bus->registers[ADXL355_REG_DEVID_MST] = ADXL355_DEVID_MST;
    bus->registers[ADXL355_REG_PARTID] = ADXL355_PARTID_VALUE;
    bus->registers[ADXL355_REG_RANGE] = ADXL355_RANGE_2G_VAL;
    bus->registers[ADXL355_REG_POWER_CTL] = ADXL355_POWER_STANDBY_VAL;
    bus->registers[ADXL355_REG_STATUS] = ADXL355_STATUS_DATA_RDY;
    for (size_t index = 0U; index < 9U; index++) {
        bus->registers[ADXL355_REG_XDATA3 + index] = next_byte(bus);
    }
    bus->registers[ADXL355_REG_TEMP2] = (uint8_t)(next_byte(bus) & UINT8_C(0x0F));
    bus->registers[ADXL355_REG_TEMP1] = next_byte(bus);
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    if (data == NULL || size == 0U || size > 4096U) {
        return 0;
    }

    fuzz_bus_t bus_state = {
        .input = data,
        .size = size,
        .cursor = 0U,
        .registers = {0U},
    };
    initialize_registers(&bus_state);

    (void)adxl355_decode_raw20(data[0], data[size > 1U ? 1U : 0U], data[size > 2U ? 2U : 0U]);
    (void)adxl355_raw_to_g((int32_t)((uint32_t)data[0] << 12), ADXL355_RANGE_2G);
    (void)adxl355_raw_to_mps2(-(int32_t)data[0], ADXL355_RANGE_8G);

    adxl355_bus_t bus = {
        .read = fuzz_read,
        .write = fuzz_write,
        .delay_ms = fuzz_delay,
        .ctx = &bus_state,
    };
    adxl355_t device;
    if (adxl355_init(&device, &bus) != ADXL355_OK) {
        return 0;
    }

    const adxl355_status_t probe = adxl355_probe(&device);
    if (probe == ADXL355_OK) {
        adxl355_raw_xyz_t raw;
        adxl355_float_xyz_t acceleration;
        int16_t temperature_raw;
        float temperature_c;
        uint8_t status;
        adxl355_range_t range;
        int16_t offset;

        (void)adxl355_read_raw(&device, &raw);
        (void)adxl355_read_g(&device, &acceleration);
        (void)adxl355_read_mps2(&device, &acceleration);
        (void)adxl355_read_temperature_raw(&device, &temperature_raw);
        (void)adxl355_read_temperature_c(&device, &temperature_c);
        (void)adxl355_read_status(&device, &status);
        (void)adxl355_get_range(&device, &range);
        (void)adxl355_set_range(&device, (adxl355_range_t)(1U + (next_byte(&bus_state) % 3U)));
        (void)adxl355_set_power_mode(
            &device,
            (next_byte(&bus_state) & 1U) != 0U
                ? ADXL355_POWER_STANDBY
                : ADXL355_POWER_MEASUREMENT);
        (void)adxl355_set_odr(&device, (adxl355_odr_t)(next_byte(&bus_state) % 11U));
        (void)adxl355_read_offset(
            &device,
            (adxl355_axis_t)(next_byte(&bus_state) % 3U),
            &offset);
        (void)adxl355_write_offset(
            &device,
            (adxl355_axis_t)(next_byte(&bus_state) % 3U),
            (int16_t)(((uint16_t)next_byte(&bus_state) << 8) | next_byte(&bus_state)));
        (void)adxl355_reset(&device);
    }
    return 0;
}

#ifdef ADXL355_FUZZ_STANDALONE
int main(int argc, char **argv)
{
    uint8_t buffer[4096];
    if (argc < 2) {
        static const uint8_t seed[] = {0xAD, 0x1D, 0xED, 0x01, 0x7F, 0xFF, 0xF0};
        return LLVMFuzzerTestOneInput(seed, sizeof(seed));
    }
    for (int index = 1; index < argc; index++) {
        FILE *handle = fopen(argv[index], "rb");
        if (handle == NULL) {
            return EXIT_FAILURE;
        }
        const size_t length = fread(buffer, 1U, sizeof(buffer), handle);
        if (ferror(handle) != 0 || fclose(handle) != 0) {
            return EXIT_FAILURE;
        }
        (void)LLVMFuzzerTestOneInput(buffer, length);
    }
    return EXIT_SUCCESS;
}
#endif
