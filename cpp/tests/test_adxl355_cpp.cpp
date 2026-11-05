#include <adxl355/adxl355.hpp>
#include <cstdio>
#include <climits>
#include <cstring>
#include <cmath>
#include <memory>

static int tests_run = 0;
static int tests_pass = 0;

#define TEST(cond, msg) do {                                        \
    tests_run++;                                                    \
    if (!(cond)) {                                                  \
        std::fprintf(stderr, "  FAIL: %s\n", msg);                  \
    } else {                                                        \
        tests_pass++;                                               \
    }                                                               \
} while(0)

// ---------------------------------------------------------------------------
// Mock bus
// ---------------------------------------------------------------------------

class MockBus : public adxl355::BusInterface {
public:
    uint8_t regs[128]{};
    bool fail_reads{false};
    bool throw_reads{false};
    bool fail_writes{false};
    bool throw_writes{false};
    bool throw_delays{false};
    size_t short_read_length{static_cast<size_t>(-1)};
    int fail_write_reg{-1};
    size_t fail_write_occurrence{0};
    size_t fail_write_matches{0};
    size_t read_count{0};
    size_t write_count{0};

    MockBus() {
        regs[ADXL355_REG_DEVID_AD]  = ADXL355_DEVID_AD;
        regs[ADXL355_REG_DEVID_MST] = ADXL355_DEVID_MST;
        regs[ADXL355_REG_PARTID]    = ADXL355_PARTID_VALUE;
        regs[ADXL355_REG_RANGE]     = ADXL355_RANGE_2G;
    }

    void setRawX(int32_t raw) {
        const uint32_t value = static_cast<uint32_t>(raw) & 0xFFFFFU;
        regs[ADXL355_REG_XDATA3] = static_cast<uint8_t>((value >> 12U) & 0xFFU);
        regs[ADXL355_REG_XDATA2] = static_cast<uint8_t>((value >> 4U) & 0xFFU);
        regs[ADXL355_REG_XDATA1] = static_cast<uint8_t>((value & 0x0FU) << 4U);
    }

    int read(void *ctx, uint8_t reg, uint8_t *data, size_t len) override {
        (void)ctx;
        read_count++;
        if (throw_reads) {
            throw std::runtime_error("read failure");
        }
        const size_t first = static_cast<size_t>(reg);
        if (fail_reads || data == nullptr || first >= sizeof(regs) ||
            len > sizeof(regs) - first) {
            return -1;
        }
        const size_t reported_len = short_read_length == static_cast<size_t>(-1)
                                        ? len
                                        : short_read_length;
        const size_t copy_len = reported_len < len ? reported_len : len;
        std::memcpy(data, &regs[reg], copy_len);
        return reported_len <= static_cast<size_t>(INT_MAX)
                   ? static_cast<int>(reported_len)
                   : -1;
    }

    int write(void *ctx, uint8_t reg, const uint8_t *data, size_t len) override {
        (void)ctx;
        write_count++;
        if (throw_writes) {
            throw std::runtime_error("write failure");
        }
        const size_t first = static_cast<size_t>(reg);
        if (fail_writes || data == nullptr || first >= sizeof(regs) ||
            len > sizeof(regs) - first) {
            return -1;
        }
        if (fail_write_reg >= 0 && reg == static_cast<uint8_t>(fail_write_reg)) {
            fail_write_matches++;
            if (fail_write_occurrence == 0U || fail_write_matches == fail_write_occurrence) {
                return -1;
            }
        }
        std::memcpy(&regs[reg], data, len);
        if (reg == ADXL355_REG_RESET && len > 0 && data[0] == ADXL355_RESET_CODE) {
            regs[ADXL355_REG_RANGE] = ADXL355_RANGE_2G;
        }
        return len <= static_cast<size_t>(INT_MAX) ? static_cast<int>(len) : -1;
    }

    void delayMs(void *ctx, uint32_t ms) override {
        (void)ctx;
        (void)ms;
        if (throw_delays) {
            throw std::runtime_error("delay failure");
        }
    }
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void test_decode_raw20() {
    auto result = adxl355::Device::decodeRaw20(0, 0, 0);
    TEST(result == 0, "decode zero");

    result = adxl355::Device::decodeRaw20(0, 0, 16);
    TEST(result == 1, "decode positive one");

    result = adxl355::Device::decodeRaw20(127, 255, 240);
    TEST(result == 524287, "decode positive max");

    result = adxl355::Device::decodeRaw20(128, 0, 0);
    TEST(result == -524288, "decode negative min");

    result = adxl355::Device::decodeRaw20(255, 255, 240);
    TEST(result == -1, "decode negative one");
}

void test_raw_to_g() {
    float g = adxl355::Device::rawToG(524287, adxl355::Range::G2);
    float expected = 524287.0f * 0.0000039f;
    TEST(std::fabs(g - expected) < 1e-6f, "raw to g 2g");
}

void test_probe() {
    auto bus = std::make_unique<MockBus>();
    adxl355::Device dev(std::move(bus));

    try {
        dev.probe();
        TEST(true, "probe succeeded");
    } catch (...) {
        TEST(false, "probe failed");
    }
}

void test_probe_synchronizes_range() {
    auto bus = std::make_unique<MockBus>();
    bus->regs[ADXL355_REG_RANGE] = ADXL355_RANGE_8G;
    adxl355::Device dev(std::move(bus));

    try {
        dev.probe();
        TEST(dev.getRange() == adxl355::Range::G8, "probe synchronizes 8g range");
    } catch (const adxl355::Error &) {
        TEST(false, "probe range synchronization failed");
    }
}

void test_reset_restores_2g_range() {
    auto bus = std::make_unique<MockBus>();
    adxl355::Device dev(std::move(bus));

    try {
        dev.probe();
        dev.setRange(adxl355::Range::G8);
        dev.reset();
        TEST(dev.getRange() == adxl355::Range::G2, "reset restores 2g range");
    } catch (const adxl355::Error &) {
        TEST(false, "reset range verification failed");
    }
}

void test_pre_probe_calls_throw_invalid_state() {
    auto bus = std::make_unique<MockBus>();
    const auto *mock = bus.get();
    adxl355::Device dev(std::move(bus));

    try {
        dev.setRange(adxl355::Range::G4);
        TEST(false, "setRange before probe should throw");
    } catch (const adxl355::InvalidStateError &) {
        TEST(mock->read_count == 0U && mock->write_count == 0U,
             "pre-probe state failure should not access the bus");
    }
}

void test_cpp_range_configuration_restores_measurement() {
    auto bus = std::make_unique<MockBus>();
    auto *mock = bus.get();
    adxl355::Device dev(std::move(bus));
    dev.probe();
    mock->regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;

    dev.setRange(adxl355::Range::G4);
    TEST(mock->regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_MEASUREMENT,
         "C++ range configuration restores measurement mode");
    TEST(mock->regs[ADXL355_REG_RANGE] == ADXL355_RANGE_4G,
         "C++ range configuration updates range");
}

void test_cpp_odr_configuration_restores_measurement() {
    auto bus = std::make_unique<MockBus>();
    auto *mock = bus.get();
    adxl355::Device dev(std::move(bus));
    dev.probe();
    mock->regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;
    mock->regs[ADXL355_REG_FILTER] = 0xA0U;

    dev.setOdr(adxl355::Odr::Hz125);
    TEST(mock->regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_MEASUREMENT,
         "C++ ODR configuration restores measurement mode");
    TEST(mock->regs[ADXL355_REG_FILTER] == 0x25U,
         "C++ ODR configuration preserves documented FILTER HPF bits");
}

void test_set_range_preserves_unrelated_bits() {
    auto bus = std::make_unique<MockBus>();
    auto *mock = bus.get();
    mock->regs[ADXL355_REG_RANGE] = 0xC1;
    adxl355::Device dev(std::move(bus));

    try {
        dev.probe();
        const size_t reads_before = mock->read_count;
        dev.setRange(adxl355::Range::G4);
        TEST(mock->read_count == reads_before + 2U, "setRange reads RANGE before writing");
        TEST(mock->regs[ADXL355_REG_RANGE] == 0xC2,
             "setRange preserves I2C_HS and INT_POL bits");
    } catch (const adxl355::Error &) {
        TEST(false, "setRange preserve-bits path failed");
    }
}

void test_set_range_read_error_prevents_write() {
    auto bus = std::make_unique<MockBus>();
    auto *mock = bus.get();
    mock->regs[ADXL355_REG_RANGE] = 0xC1;
    mock->setRawX(256410);
    adxl355::Device dev(std::move(bus));
    dev.probe();

    const size_t writes_before = mock->write_count;
    mock->fail_reads = true;
    try {
        dev.setRange(adxl355::Range::G4);
        TEST(false, "setRange should throw on read failure");
    } catch (const adxl355::BusError &) {
        TEST(mock->write_count == writes_before, "read failure prevents RANGE write");
        TEST(mock->regs[ADXL355_REG_RANGE] == 0xC1, "read failure preserves RANGE register");
        mock->fail_reads = false;
        const auto accel = dev.readG();
        TEST(std::fabs(accel.x - 1.0F) < 0.001F, "read failure preserves cached 2g range");
    }
}

void test_set_range_write_error_preserves_state() {
    auto bus = std::make_unique<MockBus>();
    auto *mock = bus.get();
    mock->regs[ADXL355_REG_RANGE] = 0xC1;
    mock->setRawX(256410);
    adxl355::Device dev(std::move(bus));
    dev.probe();

    mock->fail_writes = true;
    try {
        dev.setRange(adxl355::Range::G4);
        TEST(false, "setRange should throw on write failure");
    } catch (const adxl355::BusError &) {
        TEST(mock->regs[ADXL355_REG_RANGE] == 0xC1, "write failure preserves RANGE register");
        mock->fail_writes = false;
        const auto accel = dev.readG();
        TEST(std::fabs(accel.x - 1.0F) < 0.001F, "write failure preserves cached 2g range");
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------


void test_cpp_short_read_throws_bus_error() {
    auto bus = std::make_unique<MockBus>();
    auto *mock = bus.get();
    adxl355::Device dev(std::move(bus));
    dev.probe();
    mock->short_read_length = 8U;

    try {
        (void)dev.readRaw();
        TEST(false, "TR-9 truncated read should throw BusError");
    } catch (const adxl355::BusError &) {
        TEST(true, "C++ wrapper maps short reads to BusError");
    }
}

void test_extended_read_and_control_api() {
    auto bus = std::make_unique<MockBus>();
    auto *mock = bus.get();
    mock->setRawX(256410);
    mock->regs[ADXL355_REG_STATUS] = 0xA5U;
    adxl355::Device dev(std::move(bus));
    dev.probe();

    const auto raw = dev.readRaw();
    TEST(raw.x == 256410 && raw.y == 0 && raw.z == 0,
         "C++ raw XYZ accessors return all three axes");
    const auto accel_g = dev.readG();
    const auto accel_mps2 = dev.readMps2();
    TEST(std::fabs(accel_g.x - 1.0F) < 0.001F,
         "C++ readG returns calibrated X acceleration");
    TEST(std::fabs(accel_mps2.x - accel_g.x * 9.80665F) < 0.002F,
         "C++ readMps2 agrees with readG conversion");
    TEST(std::isfinite(dev.readTemperatureC()), "C++ temperature returns finite Celsius");
    TEST(dev.readStatus() == 0xA5U, "C++ readStatus preserves the status register");

    TEST(std::fabs(adxl355::Device::rawToMps2(256410, adxl355::Range::G2) -
                   accel_mps2.x) < 0.002F,
         "C++ static rawToMps2 matches device conversion");
    TEST(std::strcmp(adxl355::Device::statusString(ADXL355_ERR_BUS),
                     "ADXL355_ERR_BUS") == 0,
         "C++ statusString matches C error mapping");

    dev.setPowerMode(adxl355::PowerMode::Standby);
    TEST((mock->regs[ADXL355_REG_POWER_CTL] & 1U) == 1U,
         "C++ standby sets power mode bit");
    dev.setPowerMode(adxl355::PowerMode::Measurement);
    TEST((mock->regs[ADXL355_REG_POWER_CTL] & 1U) == 0U,
         "C++ measurement clears power mode bit");
}

void test_probe_rejects_bad_identity_and_invalid_range() {
    auto bad_bus = std::make_unique<MockBus>();
    bad_bus->regs[ADXL355_REG_PARTID] = 0x00U;
    adxl355::Device invalid(std::move(bad_bus));
    try {
        invalid.probe();
        TEST(false, "C++ bad part ID should throw");
    } catch (const adxl355::DeviceNotFoundError &) {
        TEST(true, "C++ invalid identity maps to DeviceNotFoundError");
    }

    auto bus = std::make_unique<MockBus>();
    auto *mock = bus.get();
    adxl355::Device dev(std::move(bus));
    dev.probe();
    const auto original = mock->regs[ADXL355_REG_RANGE];
    try {
        dev.setRange(static_cast<adxl355::Range>(0));
        TEST(false, "C++ invalid range should throw");
    } catch (const adxl355::InvalidArgumentError &) {
        TEST(mock->regs[ADXL355_REG_RANGE] == original,
             "C++ invalid range preserves current configuration");
    }
}

void test_move_preserves_bus_callback_owner() {
    auto bus = std::make_unique<MockBus>();
    auto *mock = bus.get();
    mock->regs[ADXL355_REG_STATUS] = 0x7EU;
    adxl355::Device original(std::move(bus));
    original.probe();
    adxl355::Device moved(std::move(original));

    TEST(moved.readStatus() == 0x7EU,
         "C++ moved device reads through rebound callback context");
    const size_t writes_before = mock->write_count;
    moved.setPowerMode(adxl355::PowerMode::Standby);
    TEST(mock->write_count == writes_before + 1U,
         "C++ moved device writes through rebound callback context");
}

void test_noexcept_bus_contains_native_exceptions() {
    MockBus bus;
    adxl355::NoexceptDevice dev(bus);
    TEST(dev.initStatus() == adxl355::Status::Ok,
         "exception-containing adapter initialized");
    bus.throw_reads = true;
    TEST(dev.probe() == adxl355::Status::Bus,
         "exception in read callback maps to Bus without escaping noexcept");
    bus.throw_reads = false;
    TEST(dev.probe() == adxl355::Status::Ok,
         "exception-containing adapter can recover after failed read");
    bus.throw_writes = true;
    TEST(dev.setPowerMode(adxl355::PowerMode::Standby) == adxl355::Status::Bus,
         "exception in write callback maps to Bus without escaping noexcept");
    bus.throw_writes = false;
    bus.throw_delays = true;
    TEST(dev.reset() == adxl355::Status::Ok,
         "exception in void delay callback stays contained by noexcept adapter");
}

int main() {
    std::printf("ADXL355 C++ Test Suite\n");
    std::printf("======================\n");

    test_decode_raw20();
    test_raw_to_g();
    test_probe();
    test_probe_synchronizes_range();
    test_reset_restores_2g_range();
    test_pre_probe_calls_throw_invalid_state();
    test_cpp_range_configuration_restores_measurement();
    test_cpp_odr_configuration_restores_measurement();
    test_cpp_short_read_throws_bus_error();
    test_set_range_preserves_unrelated_bits();
    test_set_range_read_error_prevents_write();
    test_set_range_write_error_preserves_state();
    test_extended_read_and_control_api();
    test_probe_rejects_bad_identity_and_invalid_range();
    test_move_preserves_bus_callback_owner();
    test_noexcept_bus_contains_native_exceptions();

    std::printf("\nResults: %d/%d passed\n", tests_pass, tests_run);
    return (tests_pass == tests_run) ? 0 : 1;
}
