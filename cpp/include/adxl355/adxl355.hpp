#ifndef ADXL355_HPP
#define ADXL355_HPP

#include <adxl355/adxl355.h>

#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

namespace adxl355 {

// ---------------------------------------------------------------------------
// Exception types
// ---------------------------------------------------------------------------

class Error : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

class BusError : public Error {
public:
    explicit BusError(const std::string &msg = "Bus communication error")
        : Error(msg) {}
};

class DeviceNotFoundError : public Error {
public:
    explicit DeviceNotFoundError(const std::string &msg = "Device not found")
        : Error(msg) {}
};

class InvalidArgumentError : public Error {
public:
    explicit InvalidArgumentError(const std::string &msg = "Invalid argument")
        : Error(msg) {}
};

class InvalidStateError : public Error {
public:
    explicit InvalidStateError(const std::string &msg = "Invalid device state")
        : Error(msg) {}
};

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

enum class Range : uint8_t {
    G2 = ADXL355_RANGE_2G,
    G4 = ADXL355_RANGE_4G,
    G8 = ADXL355_RANGE_8G,
};

enum class PowerMode : uint8_t {
    Standby     = ADXL355_POWER_STANDBY,
    Measurement = ADXL355_POWER_MEASUREMENT,
};

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

struct RawXYZ {
    int32_t x;
    int32_t y;
    int32_t z;
};

struct AccelXYZ {
    float x;
    float y;
    float z;
};

// ---------------------------------------------------------------------------
// Bus abstraction wrapper
// ---------------------------------------------------------------------------

/**
 * Abstract bus interface for the ADXL355.
 *
 * Derive from this class and implement read/write/delay.
 * Pass an instance to Device::createBus().
 */
class BusInterface {
public:
    virtual ~BusInterface() = default;

    /// Read `len` bytes and return exactly `len` on success, negative on failure.
    /// Zero, partial, and overlong counts are rejected by the C core.
    virtual int read(void *ctx, uint8_t reg, uint8_t *data, size_t len) = 0;

    /// Write all `len` bytes and return exactly `len`, or negative on failure.
    virtual int write(void *ctx, uint8_t reg, const uint8_t *data, size_t len) = 0;

    /// Blocking delay in milliseconds.
    virtual void delayMs(void *ctx, uint32_t ms) = 0;
};

// ---------------------------------------------------------------------------
// ADXL355 Device
// ---------------------------------------------------------------------------

/**
 * RAII wrapper over the ADXL355 C core driver.
 *
 * Usage:
 *   auto bus = std::make_unique<MyBus>();
 *   Device dev(std::move(bus));
 *   dev.init();
 *   dev.probe();
 *   dev.setRange(Range::G2);
 *   auto raw = dev.readRaw();
 */
class Device {
public:
    /// Create a device with a custom bus implementation.
    explicit Device(std::unique_ptr<BusInterface> bus_iface)
        : bus_iface_(std::move(bus_iface))
    {
        adxl355_bus_t bus;
        bus.read     = bus_thunk_read;
        bus.write    = bus_thunk_write;
        bus.delay_ms = bus_thunk_delay;
        bus.ctx      = this;

        check(adxl355_init(&dev_, &bus), "init");
    }

    /// No copy.
    Device(const Device &) = delete;
    Device &operator=(const Device &) = delete;

    /// Move.
    Device(Device &&other) noexcept
        : dev_(other.dev_), bus_iface_(std::move(other.bus_iface_))
    {
        // Update the bus context pointer to point to this new object
        dev_.bus.ctx = this;
    }

    ~Device() = default;

    // ------------------------------------------------------------------
    // Core API
    // ------------------------------------------------------------------

    void probe() {
        check(adxl355_probe(&dev_), "probe");
    }

    void reset() {
        check(adxl355_reset(&dev_), "reset");
    }

    void setRange(Range range) {
        check(adxl355_set_range(&dev_, static_cast<adxl355_range_t>(range)),
              "set_range");
    }

    Range getRange() {
        adxl355_range_t r;
        check(adxl355_get_range(&dev_, &r), "get_range");
        return static_cast<Range>(r);
    }

    void setPowerMode(PowerMode mode) {
        check(adxl355_set_power_mode(&dev_,
              static_cast<adxl355_power_mode_t>(mode)), "set_power_mode");
    }

    // ------------------------------------------------------------------
    // Data readout
    // ------------------------------------------------------------------

    RawXYZ readRaw() {
        adxl355_raw_xyz_t raw;
        check(adxl355_read_raw(&dev_, &raw), "read_raw");
        return {raw.x, raw.y, raw.z};
    }

    AccelXYZ readG() {
        adxl355_float_xyz_t accel;
        check(adxl355_read_g(&dev_, &accel), "read_g");
        return {accel.x, accel.y, accel.z};
    }

    AccelXYZ readMps2() {
        adxl355_float_xyz_t accel;
        check(adxl355_read_mps2(&dev_, &accel), "read_mps2");
        return {accel.x, accel.y, accel.z};
    }

    float readTemperatureC() {
        float t;
        check(adxl355_read_temperature_c(&dev_, &t), "read_temperature_c");
        return t;
    }

    uint8_t readStatus() {
        uint8_t s;
        check(adxl355_read_status(&dev_, &s), "read_status");
        return s;
    }

    // ------------------------------------------------------------------
    // Static conversion functions
    // ------------------------------------------------------------------

    static int32_t decodeRaw20(uint8_t b0, uint8_t b1, uint8_t b2) {
        return adxl355_decode_raw20(b0, b1, b2);
    }

    static float rawToG(int32_t raw, Range range) {
        return adxl355_raw_to_g(raw, static_cast<adxl355_range_t>(range));
    }

    static float rawToMps2(int32_t raw, Range range) {
        return adxl355_raw_to_mps2(raw, static_cast<adxl355_range_t>(range));
    }

    static const char *statusString(int status) {
        return adxl355_status_string(static_cast<adxl355_status_t>(status));
    }

private:
    adxl355_t dev_{};
    std::unique_ptr<BusInterface> bus_iface_;

    // ------------------------------------------------------------------
    // Bus thunks (C → C++ bridge)
    // ------------------------------------------------------------------

    static int bus_thunk_read(void *ctx, uint8_t reg, uint8_t *data, size_t len) {
        auto *self = static_cast<Device *>(ctx);
        return self->bus_iface_->read(self->bus_iface_.get(), reg, data, len);
    }

    static int bus_thunk_write(void *ctx, uint8_t reg, const uint8_t *data, size_t len) {
        auto *self = static_cast<Device *>(ctx);
        return self->bus_iface_->write(self->bus_iface_.get(), reg, data, len);
    }

    static void bus_thunk_delay(void *ctx, uint32_t ms) {
        auto *self = static_cast<Device *>(ctx);
        self->bus_iface_->delayMs(self->bus_iface_.get(), ms);
    }

    // ------------------------------------------------------------------
    // Error handling
    // ------------------------------------------------------------------

    static void check(adxl355_status_t status, const char *context) {
        if (status != ADXL355_OK) {
            switch (status) {
                case ADXL355_ERR_BUS:
                    throw BusError(std::string(context) + ": bus error");
                case ADXL355_ERR_BAD_DEVICE:
                    throw DeviceNotFoundError(std::string(context) + ": bad device");
                case ADXL355_ERR_INVALID_ARG:
                    throw InvalidArgumentError(std::string(context) + ": invalid argument");
                case ADXL355_ERR_STATE:
                    throw InvalidStateError(std::string(context) + ": device has not been probed");
                default:
                    throw Error(std::string(context) + ": " +
                                adxl355_status_string(status));
            }
        }
    }
};

} // namespace adxl355

#endif // ADXL355_HPP
