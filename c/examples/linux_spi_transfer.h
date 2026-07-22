#ifndef ADXL355_LINUX_SPI_TRANSFER_H
#define ADXL355_LINUX_SPI_TRANSFER_H

#include "adxl355/adxl355_registers.h"

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ADXL355_LINUX_SPI_MAX_PAYLOAD 32U

typedef struct {
    uint8_t tx[ADXL355_LINUX_SPI_MAX_PAYLOAD + 1U];
    uint8_t rx[ADXL355_LINUX_SPI_MAX_PAYLOAD + 1U];
    size_t  length;
} adxl355_linux_spi_read_transfer_t;

int adxl355_linux_spi_prepare_read(uint8_t reg,
                                   size_t payload_length,
                                   adxl355_linux_spi_read_transfer_t *transfer);

int adxl355_linux_spi_copy_read_payload(const adxl355_linux_spi_read_transfer_t *transfer,
                                        uint8_t *payload,
                                        size_t payload_length);

#ifdef __cplusplus
}
#endif

#endif /* ADXL355_LINUX_SPI_TRANSFER_H */
