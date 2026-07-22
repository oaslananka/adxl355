/**
 * linux_spi.c
 *
 * ADXL355 Linux SPI example using spidev.
 *
 * Build:
 *   gcc -o linux_spi linux_spi.c -ladxl355
 *
 * Usage:
 *   ./linux_spi [bus] [cs] [speed_hz]
 *   Defaults: bus=0, cs=0, speed=1000000
 */

#include "adxl355/adxl355.h"
#include "linux_spi_transfer.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/spi/spidev.h>

/* ── SPI context ────────────────────────────────────────────────────────── */

typedef struct {
    int fd;
    uint32_t speed_hz;
} spi_ctx_t;

static int spi_open(spi_ctx_t *ctx, int bus, int cs, uint32_t speed_hz)
{
    char path[32];
    snprintf(path, sizeof(path), "/dev/spidev%d.%d", bus, cs);
    ctx->fd = open(path, O_RDWR);
    if (ctx->fd < 0) {
        perror("open spidev");
        return -1;
    }

    uint8_t  mode = SPI_MODE_0;
    uint8_t  bits = 8;
    uint32_t speed = speed_hz;

    if (ioctl(ctx->fd, SPI_IOC_WR_MODE, &mode) < 0)     { perror("mode"); close(ctx->fd); return -1; }
    if (ioctl(ctx->fd, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0) { perror("bits"); close(ctx->fd); return -1; }
    if (ioctl(ctx->fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed) < 0) { perror("speed"); close(ctx->fd); return -1; }

    ctx->speed_hz = speed;
    return 0;
}

/* ── Bus callbacks ──────────────────────────────────────────────────────── */

static int spi_read(void *ctx, uint8_t reg, uint8_t *data, size_t len)
{
    spi_ctx_t *spi = (spi_ctx_t *)ctx;
    adxl355_linux_spi_read_transfer_t transfer;

    if (adxl355_linux_spi_prepare_read(reg, len, &transfer) != 0) {
        fprintf(stderr, "spi_read: unsupported payload length %zu\n", len);
        return -1;
    }

    struct spi_ioc_transfer tr = {0};
    tr.tx_buf        = (unsigned long)(uintptr_t)transfer.tx;
    tr.rx_buf        = (unsigned long)(uintptr_t)transfer.rx;
    tr.len           = (uint32_t)transfer.length;
    tr.speed_hz      = spi->speed_hz;
    tr.bits_per_word = 8;

    if (ioctl(spi->fd, SPI_IOC_MESSAGE(1), &tr) < 0) {
        perror("spi_read ioctl");
        return -1;
    }

    return adxl355_linux_spi_copy_read_payload(&transfer, data, len);
}

static int spi_write(void *ctx, uint8_t reg, const uint8_t *data, size_t len)
{
    spi_ctx_t *spi = (spi_ctx_t *)ctx;

    /* ADXL355 SPI write: first byte is the register address (read flag clear),
     * subsequent bytes are data. All in one transfer. */
    uint8_t *buf = malloc(len + 1);
    if (!buf) return -1;
    buf[0] = reg << 1;  /* SPI write command */
    memcpy(buf + 1, data, len);

    struct spi_ioc_transfer tr = {0};
    tr.tx_buf        = (unsigned long)buf;
    tr.len           = (uint32_t)(len + 1);
    tr.speed_hz      = spi->speed_hz;
    tr.bits_per_word = 8;

    int ret = ioctl(spi->fd, SPI_IOC_MESSAGE(1), &tr);
    free(buf);
    return ret < 0 ? -1 : 0;
}

static void spi_delay(void *ctx, uint32_t ms)
{
    (void)ctx;
    usleep(ms * 1000);
}

/* ── Main ───────────────────────────────────────────────────────────────── */

int main(int argc, char **argv)
{
    int      bus      = argc > 1 ? atoi(argv[1]) : 0;
    int      cs       = argc > 2 ? atoi(argv[2]) : 0;
    uint32_t speed_hz = argc > 3 ? (uint32_t)atoi(argv[3]) : 1000000;

    spi_ctx_t spi_ctx;
    if (spi_open(&spi_ctx, bus, cs, speed_hz) != 0) {
        fprintf(stderr, "Failed to open SPI %d.%d\n", bus, cs);
        return 1;
    }

    adxl355_bus_t bus_if = {
        .read     = spi_read,
        .write    = spi_write,
        .delay_ms = spi_delay,
        .ctx      = &spi_ctx,
    };

    adxl355_t dev;
    adxl355_status_t status;

    status = adxl355_init(&dev, &bus_if);
    if (status != ADXL355_OK) {
        fprintf(stderr, "Init failed: %s\n", adxl355_status_string(status));
        close(spi_ctx.fd);
        return 1;
    }

    status = adxl355_probe(&dev);
    if (status != ADXL355_OK) {
        fprintf(stderr, "Probe failed: %s\n", adxl355_status_string(status));
        close(spi_ctx.fd);
        return 1;
    }
    printf("ADXL355 detected on SPI %d.%d @ %u Hz\n", bus, cs, speed_hz);

    adxl355_set_power_mode(&dev, ADXL355_POWER_MEASUREMENT);

    /* Read temperature */
    float temp_c;
    if (adxl355_read_temperature_c(&dev, &temp_c) == ADXL355_OK) {
        printf("Temperature: %.2f °C\n", temp_c);
    }

    /* Read acceleration */
    adxl355_float_xyz_t accel;
    if (adxl355_read_g(&dev, &accel) == ADXL355_OK) {
        printf("Accel (g): x=%.6f  y=%.6f  z=%.6f\n", accel.x, accel.y, accel.z);
    }

    if (adxl355_read_mps2(&dev, &accel) == ADXL355_OK) {
        printf("Accel (m/s²): x=%.4f  y=%.4f  z=%.4f\n", accel.x, accel.y, accel.z);
    }

    close(spi_ctx.fd);
    printf("Done.\n");
    return 0;
}
