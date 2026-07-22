#include "linux_spi_transfer.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int tests_run;
static int tests_failed;

#define ASSERT_TRUE(condition, message) do {                         \
    tests_run++;                                                     \
    if (!(condition)) {                                             \
        fprintf(stderr, "FAIL [%s:%d] %s\n", __FILE__, __LINE__, message); \
        tests_failed++;                                             \
    }                                                               \
} while (0)

static void test_one_byte_read(void)
{
    adxl355_linux_spi_read_transfer_t transfer;

    ASSERT_TRUE(adxl355_linux_spi_prepare_read(ADXL355_REG_TEMP2, 1U, &transfer) == 0,
                "one-byte read should be supported");
    ASSERT_TRUE(transfer.length == 2U, "one-byte payload requires two wire bytes");
    ASSERT_TRUE(transfer.tx[0] == ADXL355_SPI_READ_CMD(ADXL355_REG_TEMP2),
                "first byte should be encoded read command");
    ASSERT_TRUE(transfer.tx[1] == 0U, "payload phase should transmit a dummy byte");
}

static void test_nine_byte_read(void)
{
    adxl355_linux_spi_read_transfer_t transfer;

    ASSERT_TRUE(adxl355_linux_spi_prepare_read(ADXL355_REG_XDATA3, 9U, &transfer) == 0,
                "nine-byte read should be supported");
    ASSERT_TRUE(transfer.length == 10U, "nine-byte payload requires one ten-byte transaction");
    ASSERT_TRUE(transfer.tx[0] == 0x11U, "XDATA3 read command should be 0x11");
    for (size_t i = 1U; i < transfer.length; ++i) {
        ASSERT_TRUE(transfer.tx[i] == 0U, "all payload-phase transmit bytes should be dummy bytes");
    }
}

static void test_payload_excludes_command_phase(void)
{
    adxl355_linux_spi_read_transfer_t transfer;
    uint8_t payload[9] = {0};
    const uint8_t expected[9] = {1U, 2U, 3U, 4U, 5U, 6U, 7U, 8U, 9U};

    ASSERT_TRUE(adxl355_linux_spi_prepare_read(ADXL355_REG_XDATA3, 9U, &transfer) == 0,
                "prepare should succeed");
    transfer.rx[0] = 0xEEU;
    memcpy(&transfer.rx[1], expected, sizeof(expected));

    ASSERT_TRUE(adxl355_linux_spi_copy_read_payload(&transfer, payload, sizeof(payload)) == 0,
                "payload copy should succeed");
    ASSERT_TRUE(memcmp(payload, expected, sizeof(expected)) == 0,
                "returned payload should skip command-phase receive byte");
}

static void test_invalid_lengths_are_rejected(void)
{
    adxl355_linux_spi_read_transfer_t transfer;
    uint8_t payload[1];

    ASSERT_TRUE(adxl355_linux_spi_prepare_read(ADXL355_REG_XDATA3, 0U, &transfer) != 0,
                "zero-length reads should be rejected");
    ASSERT_TRUE(adxl355_linux_spi_prepare_read(
                    ADXL355_REG_XDATA3, ADXL355_LINUX_SPI_MAX_PAYLOAD + 1U, &transfer) != 0,
                "oversized reads should be rejected");
    ASSERT_TRUE(adxl355_linux_spi_prepare_read(ADXL355_REG_XDATA3, 1U, NULL) != 0,
                "null transfer should be rejected");
    ASSERT_TRUE(adxl355_linux_spi_copy_read_payload(NULL, payload, sizeof(payload)) != 0,
                "null transfer payload copy should be rejected");
}

int main(void)
{
    test_one_byte_read();
    test_nine_byte_read();
    test_payload_excludes_command_phase();
    test_invalid_lengths_are_rejected();

    printf("Linux SPI transfer tests: %d assertions, %d failures\n", tests_run, tests_failed);
    return tests_failed == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
