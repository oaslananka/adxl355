#include "linux_spi_transfer.h"

#include <string.h>

int adxl355_linux_spi_prepare_read(uint8_t reg,
                                   size_t payload_length,
                                   adxl355_linux_spi_read_transfer_t *transfer)
{
    if (transfer == NULL || payload_length == 0U ||
        payload_length > ADXL355_LINUX_SPI_MAX_PAYLOAD) {
        return -1;
    }

    memset(transfer, 0, sizeof(*transfer));
    transfer->tx[0] = (uint8_t)ADXL355_SPI_READ_CMD(reg);
    transfer->length = payload_length + 1U;
    return 0;
}

int adxl355_linux_spi_copy_read_payload(const adxl355_linux_spi_read_transfer_t *transfer,
                                        uint8_t *payload,
                                        size_t payload_length)
{
    if (transfer == NULL || payload == NULL || payload_length == 0U ||
        payload_length > ADXL355_LINUX_SPI_MAX_PAYLOAD ||
        transfer->length != payload_length + 1U) {
        return -1;
    }

    memcpy(payload, &transfer->rx[1], payload_length);
    return 0;
}
