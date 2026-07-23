#include <adxl355/adxl355.hpp>
#include <cstdio>
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
    bool fail_writes{false};
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
        if (fail_reads) {
            return -1;
        }
        std::memcpy(data, &regs[reg], len);
        return 0;
    }

    int write(void *ctx, uint8_t reg, const uint8_t *data, size_t len) override {
        (void)ctx;
        write_count++;
        if (fail_writes) {
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
        return 0;
    }

    void delayMs(void *ctx, uint32_t ms) override {
        (void)ctx;
        (void)ms;
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
    auto *mock = bus.get();
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
    test_set_range_preserves_unrelated_bits();
    test_set_range_read_error_prevents_write();
    test_set_range_write_error_preserves_state();

    std::printf("\nResults: %d/%d passed\n", tests_pass, tests_run);
    return (tests_pass == tests_run) ? 0 : 1;
}
