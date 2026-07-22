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

    MockBus() {
        regs[ADXL355_REG_DEVID_AD]  = ADXL355_DEVID_AD;
        regs[ADXL355_REG_DEVID_MST] = ADXL355_DEVID_MST;
        regs[ADXL355_REG_PARTID]    = ADXL355_PARTID_VALUE;
        regs[ADXL355_REG_RANGE]     = ADXL355_RANGE_2G;
    }

    int read(void *ctx, uint8_t reg, uint8_t *data, size_t len) override {
        (void)ctx;
        std::memcpy(data, &regs[reg], len);
        return 0;
    }

    int write(void *ctx, uint8_t reg, const uint8_t *data, size_t len) override {
        (void)ctx;
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

    std::printf("\nResults: %d/%d passed\n", tests_pass, tests_run);
    return (tests_pass == tests_run) ? 0 : 1;
}
