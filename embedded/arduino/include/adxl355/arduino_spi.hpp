#ifndef ADXL355_ARDUINO_SPI_HPP
#define ADXL355_ARDUINO_SPI_HPP

#include <Arduino.h>
#include <SPI.h>
#include <adxl355/adxl355.hpp>

#include <limits.h>
#include <stddef.h>
#include <stdint.h>

namespace adxl355 {
namespace arduino {

/**
 * Thin Arduino SPI adapter for NoexceptDevice or Device.
 *
 * The adapter owns no heap memory. It uses SPI Mode 0 and keeps chip select high
 * outside a transaction. Call begin() once from setup() before probe().
 */
class SpiBus final : public BusInterface {
public:
    explicit SpiBus(
        SPIClass &spi,
        uint8_t chip_select_pin,
        uint32_t speed_hz = 1000000UL) noexcept
        : spi_(spi),
          chip_select_pin_(chip_select_pin),
          settings_(speed_hz, MSBFIRST, SPI_MODE0)
    {}

    void begin() noexcept {
        pinMode(chip_select_pin_, OUTPUT);
        digitalWrite(chip_select_pin_, HIGH);
        spi_.begin();
    }

    int read(void *ctx, uint8_t reg, uint8_t *data, size_t len) override {
        (void)ctx;
        if (data == nullptr || len > static_cast<size_t>(INT_MAX)) {
            return -1;
        }
        spi_.beginTransaction(settings_);
        digitalWrite(chip_select_pin_, LOW);
        (void)spi_.transfer(static_cast<uint8_t>((reg << 1U) | 0x01U));
        for (size_t index = 0U; index < len; index++) {
            data[index] = spi_.transfer(0U);
        }
        digitalWrite(chip_select_pin_, HIGH);
        spi_.endTransaction();
        return static_cast<int>(len);
    }

    int write(void *ctx, uint8_t reg, const uint8_t *data, size_t len) override {
        (void)ctx;
        if (data == nullptr || len > static_cast<size_t>(INT_MAX)) {
            return -1;
        }
        spi_.beginTransaction(settings_);
        digitalWrite(chip_select_pin_, LOW);
        (void)spi_.transfer(static_cast<uint8_t>(reg << 1U));
        for (size_t index = 0U; index < len; index++) {
            (void)spi_.transfer(data[index]);
        }
        digitalWrite(chip_select_pin_, HIGH);
        spi_.endTransaction();
        return static_cast<int>(len);
    }

    void delayMs(void *ctx, uint32_t milliseconds) override {
        (void)ctx;
        delay(milliseconds);
    }

private:
    SPIClass &spi_;
    uint8_t chip_select_pin_;
    SPISettings settings_;
};

} // namespace arduino
} // namespace adxl355

#endif
