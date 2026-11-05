#include <adxl355/adxl355.hpp>

#include <climits>
#include <cmath>
#include <cstdio>
#include <cstring>

static int tests_run = 0;
static int tests_pass = 0;

#define TEST(cond, msg) do {                                        \
    tests_run++;                                                    \
    if (!(cond)) {                                                  \
        std::fprintf(stderr, "  FAIL: %s\n", msg);                  \
    } else {                                                        \
        tests_pass++;                                               \
    }                                                               \
} while (0)

class NoexceptMockBus final : public adxl355::BusInterface {
public:
    uint8_t regs[128]{};
    bool fail_reads{false};
    bool fail_writes{false};
    size_t read_count{0U};
    size_t write_count{0U};

    NoexceptMockBus() {
        regs[ADXL355_REG_DEVID_AD] = ADXL355_DEVID_AD;
        regs[ADXL355_REG_DEVID_MST] = ADXL355_DEVID_MST;
        regs[ADXL355_REG_PARTID] = ADXL355_PARTID_VALUE;
        regs[ADXL355_REG_RANGE] = ADXL355_RANGE_2G;
        regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_STANDBY_VAL;
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
        if (fail_reads || len > static_cast<size_t>(INT_MAX)) {
            return -1;
        }
        std::memcpy(data, &regs[reg], len);
        return static_cast<int>(len);
    }

    int write(void *ctx, uint8_t reg, const uint8_t *data, size_t len) override {
        (void)ctx;
        write_count++;
        if (fail_writes || len > static_cast<size_t>(INT_MAX)) {
            return -1;
        }
        std::memcpy(&regs[reg], data, len);
        if (reg == ADXL355_REG_RESET && len > 0U && data[0] == ADXL355_RESET_CODE) {
            regs[ADXL355_REG_RANGE] = ADXL355_RANGE_2G;
        }
        return static_cast<int>(len);
    }

    void delayMs(void *ctx, uint32_t ms) override {
        (void)ctx;
        (void)ms;
    }
};

int main() {
    std::printf("ADXL355 C++ Exception-Free Test Suite\n");
    std::printf("====================================\n");

    NoexceptMockBus bus;
    adxl355::NoexceptDevice device(bus);
    TEST(device.initStatus() == adxl355::Status::Ok, "stack-owned init succeeds");

    const size_t reads_before = bus.read_count;
    const size_t writes_before = bus.write_count;
    TEST(device.setOdr(adxl355::Odr::Hz125) == adxl355::Status::InvalidState,
         "pre-probe ODR returns InvalidState");
    TEST(bus.read_count == reads_before && bus.write_count == writes_before,
         "pre-probe status path does not access bus");

    TEST(device.probe() == adxl355::Status::Ok, "probe returns Ok");
    bus.regs[ADXL355_REG_POWER_CTL] = ADXL355_POWER_MEASUREMENT;
    bus.regs[ADXL355_REG_FILTER] = 0xA0U;
    TEST(device.setOdr(adxl355::Odr::Hz125) == adxl355::Status::Ok,
         "ODR configuration returns Ok");
    TEST(bus.regs[ADXL355_REG_FILTER] == 0x25U,
         "ODR configuration preserves documented FILTER HPF bits");
    TEST(bus.regs[ADXL355_REG_POWER_CTL] == ADXL355_POWER_MEASUREMENT,
         "ODR configuration restores measurement mode");

    bus.setRawX(256410);
    const auto raw = device.readRaw();
    TEST(raw.ok() && raw.value.x == 256410, "readRaw returns Result value");
    const auto acceleration = device.readG();
    TEST(acceleration.ok() && std::fabs(acceleration.value.x - 1.0F) < 0.001F,
         "readG uses C core conversion and cached range");

    const auto range = device.getRange();
    TEST(range.ok() && range.value == adxl355::Range::G2,
         "noexcept getRange returns cached probe range");
    TEST(static_cast<bool>(range), "noexcept Result explicit bool reports success");
    TEST(device.setRange(adxl355::Range::G4) == adxl355::Status::Ok,
         "noexcept setRange accepts 4g");
    TEST(device.getRange().value == adxl355::Range::G4,
         "noexcept getRange observes new range");
    TEST(device.setRange(adxl355::Range::G2) == adxl355::Status::Ok,
         "noexcept setRange restores original 2g range");
    TEST(device.setPowerMode(adxl355::PowerMode::Standby) == adxl355::Status::Ok,
         "noexcept standby power mode accepted");
    TEST((bus.regs[ADXL355_REG_POWER_CTL] & 1U) == 1U,
         "noexcept standby sets the control bit");
    TEST(device.setPowerMode(adxl355::PowerMode::Measurement) == adxl355::Status::Ok,
         "noexcept measurement power mode accepted");
    TEST((bus.regs[ADXL355_REG_POWER_CTL] & 1U) == 0U,
         "noexcept measurement clears the control bit");

    const auto accel_mps2 = device.readMps2();
    TEST(accel_mps2.ok() &&
             std::fabs(accel_mps2.value.x - acceleration.value.x * 9.80665F) < 0.002F,
         "noexcept readMps2 matches g conversion");
    TEST(std::isfinite(device.readTemperatureC().value),
         "noexcept temperature is finite");
    bus.regs[ADXL355_REG_STATUS] = 0x52U;
    const auto status = device.readStatus();
    TEST(status.ok() && status.value == 0x52U,
         "noexcept readStatus returns register value");
    TEST(adxl355::NoexceptDevice::decodeRaw20(0U, 0U, 16U) == 1,
         "noexcept decodeRaw20 agrees with core");
    TEST(std::fabs(adxl355::NoexceptDevice::rawToG(256410, adxl355::Range::G2) -
                   acceleration.value.x) < 0.001F,
         "noexcept rawToG agrees with readG");
    TEST(std::fabs(adxl355::NoexceptDevice::rawToMps2(256410, adxl355::Range::G2) -
                   accel_mps2.value.x) < 0.002F,
         "noexcept rawToMps2 agrees with readMps2");
    TEST(device.setRange(static_cast<adxl355::Range>(0)) ==
             adxl355::Status::InvalidArgument,
         "noexcept invalid range returns InvalidArgument");
    TEST(device.reset() == adxl355::Status::Ok,
         "noexcept reset restores configuration without exceptions");

    bus.fail_reads = true;
    const auto failed = device.readRaw();
    TEST(failed.status == adxl355::Status::Bus, "transport failure maps to Bus status");
    TEST(std::strcmp(adxl355::statusString(failed.status), "ADXL355_ERR_BUS") == 0,
         "status string maps through C core");

    std::printf("\nResults: %d/%d passed\n", tests_pass, tests_run);
    return tests_pass == tests_run ? 0 : 1;
}
