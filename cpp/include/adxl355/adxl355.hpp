#ifndef ADXL355_HPP
#define ADXL355_HPP

#include <adxl355/adxl355.h>

#include <stddef.h>
#include <stdint.h>

#ifndef ADXL355_CPP_NO_EXCEPTIONS
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#endif

namespace adxl355 {

/** Stable C++ status values mapped directly to the C core. */
enum class Status : int {
    Ok = ADXL355_OK,
    Null = ADXL355_ERR_NULL,
    Bus = ADXL355_ERR_BUS,
    Timeout = ADXL355_ERR_TIMEOUT,
    InvalidArgument = ADXL355_ERR_INVALID_ARG,
    BadDevice = ADXL355_ERR_BAD_DEVICE,
    NotReady = ADXL355_ERR_NOT_READY,
    Unsupported = ADXL355_ERR_UNSUPPORTED,
    InvalidState = ADXL355_ERR_STATE,
    Threshold = ADXL355_ERR_THRESHOLD,
    Restore = ADXL355_ERR_RESTORE,
};

constexpr Status statusFromC(adxl355_status_t status) noexcept {
    return static_cast<Status>(status);
}

constexpr adxl355_status_t statusToC(Status status) noexcept {
    return static_cast<adxl355_status_t>(status);
}

inline const char *statusString(Status status) noexcept {
    return adxl355_status_string(statusToC(status));
}

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

enum class Range : uint8_t {
    G2 = ADXL355_RANGE_2G,
    G4 = ADXL355_RANGE_4G,
    G8 = ADXL355_RANGE_8G,
};

enum class PowerMode : uint8_t {
    Standby = ADXL355_POWER_STANDBY,
    Measurement = ADXL355_POWER_MEASUREMENT,
};

/** Output data rate / filter encodings shared with the C core. */
enum class Odr : uint8_t {
    Hz4000 = ADXL355_ODR_4000_HZ,
    Hz2000 = ADXL355_ODR_2000_HZ,
    Hz1000 = ADXL355_ODR_1000_HZ,
    Hz500 = ADXL355_ODR_500_HZ,
    Hz250 = ADXL355_ODR_250_HZ,
    Hz125 = ADXL355_ODR_125_HZ,
    Hz62_5 = ADXL355_ODR_62_5_HZ,
    Hz31_25 = ADXL355_ODR_31_25_HZ,
    Hz15_625 = ADXL355_ODR_15_625_HZ,
    Hz7_813 = ADXL355_ODR_7_813_HZ,
    Hz3_906 = ADXL355_ODR_3_906_HZ,
};

// ---------------------------------------------------------------------------
// Data and result types
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

/** Value plus stable status for exception-free calls. */
template <typename T>
struct Result {
    Status status;
    T value;

    constexpr Result() noexcept
        : status(Status::Ok), value()
    {}

    constexpr Result(Status result_status, const T &result_value) noexcept
        : status(result_status), value(result_value)
    {}

    constexpr bool ok() const noexcept {
        return status == Status::Ok;
    }

    constexpr explicit operator bool() const noexcept {
        return ok();
    }
};

// ---------------------------------------------------------------------------
// Bus abstraction wrapper
// ---------------------------------------------------------------------------

/**
 * Abstract bus interface for the ADXL355.
 *
 * Implementations used with NoexceptDevice must not throw. Exact-length read and
 * write semantics are enforced by the C core.
 */
class BusInterface {
public:
    virtual ~BusInterface() = default;

    /// Read `len` bytes and return exactly `len` on success, negative on failure.
    virtual int read(void *ctx, uint8_t reg, uint8_t *data, size_t len) = 0;

    /// Write all `len` bytes and return exactly `len`, or negative on failure.
    virtual int write(void *ctx, uint8_t reg, const uint8_t *data, size_t len) = 0;

    /// Blocking delay in milliseconds.
    virtual void delayMs(void *ctx, uint32_t ms) = 0;
};

// ---------------------------------------------------------------------------
// Exception-free, stack-owned wrapper
// ---------------------------------------------------------------------------

/**
 * Non-owning C++ wrapper for builds without exceptions or dynamic allocation.
 *
 * The caller owns the BusInterface for the complete device lifetime. Methods
 * return Status or Result<T>; no method throws or allocates. Copy and move are
 * disabled so the C callback context remains stable.
 */
class NoexceptDevice {
public:
    explicit NoexceptDevice(BusInterface &bus_iface) noexcept
        : bus_iface_(&bus_iface)
    {
        adxl355_bus_t bus{};
        bus.read = busThunkRead;
        bus.write = busThunkWrite;
        bus.delay_ms = busThunkDelay;
        bus.ctx = this;
        init_status_ = statusFromC(adxl355_init(&dev_, &bus));
    }

    NoexceptDevice(const NoexceptDevice &) = delete;
    NoexceptDevice &operator=(const NoexceptDevice &) = delete;
    NoexceptDevice(NoexceptDevice &&) = delete;
    NoexceptDevice &operator=(NoexceptDevice &&) = delete;
    ~NoexceptDevice() = default;

    Status initStatus() const noexcept {
        return init_status_;
    }

    Status probe() noexcept {
        return call(adxl355_probe(&dev_));
    }

    Status reset() noexcept {
        return call(adxl355_reset(&dev_));
    }

    Status setRange(Range range) noexcept {
        return call(adxl355_set_range(&dev_, static_cast<adxl355_range_t>(range)));
    }

    Result<Range> getRange() noexcept {
        adxl355_range_t range = ADXL355_RANGE_2G;
        const Status status = call(adxl355_get_range(&dev_, &range));
        return Result<Range>(status, static_cast<Range>(range));
    }

    Status setPowerMode(PowerMode mode) noexcept {
        return call(adxl355_set_power_mode(
            &dev_, static_cast<adxl355_power_mode_t>(mode)));
    }

    Status setOdr(Odr odr) noexcept {
        return call(adxl355_set_odr(&dev_, static_cast<adxl355_odr_t>(odr)));
    }

    Result<RawXYZ> readRaw() noexcept {
        adxl355_raw_xyz_t raw{};
        const Status status = call(adxl355_read_raw(&dev_, &raw));
        return Result<RawXYZ>(status, RawXYZ{raw.x, raw.y, raw.z});
    }

    Result<AccelXYZ> readG() noexcept {
        adxl355_float_xyz_t accel{};
        const Status status = call(adxl355_read_g(&dev_, &accel));
        return Result<AccelXYZ>(status, AccelXYZ{accel.x, accel.y, accel.z});
    }

    Result<AccelXYZ> readMps2() noexcept {
        adxl355_float_xyz_t accel{};
        const Status status = call(adxl355_read_mps2(&dev_, &accel));
        return Result<AccelXYZ>(status, AccelXYZ{accel.x, accel.y, accel.z});
    }

    Result<float> readTemperatureC() noexcept {
        float temperature = 0.0F;
        const Status status = call(adxl355_read_temperature_c(&dev_, &temperature));
        return Result<float>(status, temperature);
    }

    Result<uint8_t> readStatus() noexcept {
        uint8_t status_register = 0U;
        const Status status = call(adxl355_read_status(&dev_, &status_register));
        return Result<uint8_t>(status, status_register);
    }

    static int32_t decodeRaw20(uint8_t b0, uint8_t b1, uint8_t b2) noexcept {
        return adxl355_decode_raw20(b0, b1, b2);
    }

    static float rawToG(int32_t raw, Range range) noexcept {
        return adxl355_raw_to_g(raw, static_cast<adxl355_range_t>(range));
    }

    static float rawToMps2(int32_t raw, Range range) noexcept {
        return adxl355_raw_to_mps2(raw, static_cast<adxl355_range_t>(range));
    }

private:
    adxl355_t dev_{};
    BusInterface *bus_iface_{nullptr};
    Status init_status_{Status::Null};

    Status call(adxl355_status_t status) const noexcept {
        if (init_status_ != Status::Ok) {
            return init_status_;
        }
        return statusFromC(status);
    }

    static int busThunkRead(void *ctx, uint8_t reg, uint8_t *data, size_t len) noexcept {
        auto *self = static_cast<NoexceptDevice *>(ctx);
#ifndef ADXL355_CPP_NO_EXCEPTIONS
        try {
            return self->bus_iface_->read(self->bus_iface_, reg, data, len);
        } catch (...) {
            return -1;
        }
#else
        return self->bus_iface_->read(self->bus_iface_, reg, data, len);
#endif
    }

    static int busThunkWrite(
        void *ctx, uint8_t reg, const uint8_t *data, size_t len) noexcept
    {
        auto *self = static_cast<NoexceptDevice *>(ctx);
#ifndef ADXL355_CPP_NO_EXCEPTIONS
        try {
            return self->bus_iface_->write(self->bus_iface_, reg, data, len);
        } catch (...) {
            return -1;
        }
#else
        return self->bus_iface_->write(self->bus_iface_, reg, data, len);
#endif
    }

    static void busThunkDelay(void *ctx, uint32_t ms) noexcept {
        auto *self = static_cast<NoexceptDevice *>(ctx);
#ifndef ADXL355_CPP_NO_EXCEPTIONS
        try {
            self->bus_iface_->delayMs(self->bus_iface_, ms);
        } catch (...) {
            // Delay callbacks cannot return a status. A throwing implementation
            // violates the NoexceptDevice bus contract, so the exception is
            // contained and the subsequent device operation determines status.
        }
#else
        self->bus_iface_->delayMs(self->bus_iface_, ms);
#endif
    }
};

#ifndef ADXL355_CPP_NO_EXCEPTIONS
// ---------------------------------------------------------------------------
// Exception types and owning wrapper
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

/** Owning RAII wrapper that maps stable C statuses to typed C++ exceptions. */
class Device {
public:
    explicit Device(std::unique_ptr<BusInterface> bus_iface)
        : bus_iface_(std::move(bus_iface))
    {
        adxl355_bus_t bus{};
        bus.read = busThunkRead;
        bus.write = busThunkWrite;
        bus.delay_ms = busThunkDelay;
        bus.ctx = this;
        check(adxl355_init(&dev_, &bus), "init");
    }

    Device(const Device &) = delete;
    Device &operator=(const Device &) = delete;

    Device(Device &&other) noexcept
        : dev_(other.dev_), bus_iface_(std::move(other.bus_iface_))
    {
        dev_.bus.ctx = this;
    }

    Device &operator=(Device &&) = delete;
    ~Device() = default;

    void probe() {
        check(adxl355_probe(&dev_), "probe");
    }

    void reset() {
        check(adxl355_reset(&dev_), "reset");
    }

    void setRange(Range range) {
        check(adxl355_set_range(&dev_, static_cast<adxl355_range_t>(range)), "set_range");
    }

    Range getRange() {
        adxl355_range_t range = ADXL355_RANGE_2G;
        check(adxl355_get_range(&dev_, &range), "get_range");
        return static_cast<Range>(range);
    }

    void setPowerMode(PowerMode mode) {
        check(
            adxl355_set_power_mode(&dev_, static_cast<adxl355_power_mode_t>(mode)),
            "set_power_mode");
    }

    void setOdr(Odr odr) {
        check(adxl355_set_odr(&dev_, static_cast<adxl355_odr_t>(odr)), "set_odr");
    }

    RawXYZ readRaw() {
        adxl355_raw_xyz_t raw{};
        check(adxl355_read_raw(&dev_, &raw), "read_raw");
        return {raw.x, raw.y, raw.z};
    }

    AccelXYZ readG() {
        adxl355_float_xyz_t accel{};
        check(adxl355_read_g(&dev_, &accel), "read_g");
        return {accel.x, accel.y, accel.z};
    }

    AccelXYZ readMps2() {
        adxl355_float_xyz_t accel{};
        check(adxl355_read_mps2(&dev_, &accel), "read_mps2");
        return {accel.x, accel.y, accel.z};
    }

    float readTemperatureC() {
        float temperature = 0.0F;
        check(adxl355_read_temperature_c(&dev_, &temperature), "read_temperature_c");
        return temperature;
    }

    uint8_t readStatus() {
        uint8_t status_register = 0U;
        check(adxl355_read_status(&dev_, &status_register), "read_status");
        return status_register;
    }

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

    static int busThunkRead(void *ctx, uint8_t reg, uint8_t *data, size_t len) {
        auto *self = static_cast<Device *>(ctx);
        return self->bus_iface_->read(self->bus_iface_.get(), reg, data, len);
    }

    static int busThunkWrite(void *ctx, uint8_t reg, const uint8_t *data, size_t len) {
        auto *self = static_cast<Device *>(ctx);
        return self->bus_iface_->write(self->bus_iface_.get(), reg, data, len);
    }

    static void busThunkDelay(void *ctx, uint32_t ms) {
        auto *self = static_cast<Device *>(ctx);
        self->bus_iface_->delayMs(self->bus_iface_.get(), ms);
    }

    static void check(adxl355_status_t status, const char *context) {
        if (status == ADXL355_OK) {
            return;
        }
        switch (status) {
            case ADXL355_ERR_BUS:
                throw BusError(std::string(context) + ": bus error");
            case ADXL355_ERR_BAD_DEVICE:
                throw DeviceNotFoundError(std::string(context) + ": bad device");
            case ADXL355_ERR_INVALID_ARG:
                throw InvalidArgumentError(std::string(context) + ": invalid argument");
            case ADXL355_ERR_STATE:
                throw InvalidStateError(
                    std::string(context) + ": device has not been probed");
            default:
                throw Error(
                    std::string(context) + ": " + adxl355_status_string(status));
        }
    }
};
#endif

} // namespace adxl355

#endif // ADXL355_HPP
