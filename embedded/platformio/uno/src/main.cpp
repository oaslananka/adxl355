#include <Arduino.h>
#include <SPI.h>
#include <adxl355/arduino_spi.hpp>

namespace {
constexpr uint8_t ChipSelectPin = 10U;
adxl355::arduino::SpiBus bus(SPI, ChipSelectPin, 1000000UL);
adxl355::NoexceptDevice device(bus);
volatile adxl355::Status last_status = adxl355::Status::InvalidState;
}

void setup() {
    bus.begin();
    last_status = device.probe();
    if (last_status == adxl355::Status::Ok) {
        last_status = device.setOdr(adxl355::Odr::Hz125);
    }
}

void loop() {
    delay(1000UL);
}
