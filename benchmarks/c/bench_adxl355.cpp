// CodSpeed benchmarks for the ADXL355 C core.
//
// Every benchmark runs against the repository's in-memory mock register file
// (c/tests/test_mock_bus.c), so the measurements cover driver CPU cost only:
// transport framing and length validation, decode, conversion, and the
// bounded configuration/FIFO/self-test state machines. No hardware is used.

#include <benchmark/benchmark.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

extern "C"
{
#include "adxl355/adxl355.h"
#include "adxl355/adxl355_registers.h"
#include "test_mock_bus.h"
}

namespace
{

constexpr std::size_t kBatchSamples = 1024;

void require_ok(benchmark::State &state, adxl355_status_t status)
{
    if (status != ADXL355_OK)
    {
        state.SkipWithError(adxl355_status_string(status));
    }
}

void encode_axis(uint8_t *data, int32_t raw, uint8_t marker)
{
    const uint32_t value = static_cast<uint32_t>(raw) & 0xFFFFFU;
    data[0] = static_cast<uint8_t>((value >> 12) & 0xFFU);
    data[1] = static_cast<uint8_t>((value >> 4) & 0xFFU);
    data[2] = static_cast<uint8_t>(((value & 0x0FU) << 4) | marker);
}

std::vector<int32_t> raw_samples()
{
    std::vector<int32_t> samples(kBatchSamples);
    const int32_t step = (1 << 20) / static_cast<int32_t>(kBatchSamples);
    for (std::size_t i = 0; i < kBatchSamples; ++i)
    {
        samples[i] = -524288 + static_cast<int32_t>(i) * step + static_cast<int32_t>(i % 7U);
    }
    return samples;
}

/** Mock bus plus probed device handle; the mock must outlive the device. */
struct Fixture
{
    adxl355_mock_bus_t mock{};
    adxl355_t dev{};

    explicit Fixture(benchmark::State &state)
    {
        adxl355_mock_bus_init(&mock);
        adxl355_mock_bus_set_identity_ok(&mock);
        adxl355_mock_bus_set_xyz_raw(&mock, 123456, -98765, 256000);
        mock.regs[ADXL355_REG_TEMP2] = 0x07U; /* 1885 LSB, nominal 25 degC */
        mock.regs[ADXL355_REG_TEMP1] = 0x5DU;
        const adxl355_bus_t bus = adxl355_mock_bus_get_interface(&mock);
        require_ok(state, adxl355_init(&dev, &bus));
        require_ok(state, adxl355_probe(&dev));
    }

    Fixture(const Fixture &) = delete;
    Fixture &operator=(const Fixture &) = delete;
};

/** A full FIFO: 32 well-formed XYZ samples (96 axis locations). */
std::array<uint8_t, ADXL355_FIFO_MAX_SAMPLES * ADXL355_FIFO_BYTES_PER_SAMPLE> fifo_payload()
{
    std::array<uint8_t, ADXL355_FIFO_MAX_SAMPLES * ADXL355_FIFO_BYTES_PER_SAMPLE> payload{};
    for (std::size_t i = 0; i < ADXL355_FIFO_MAX_SAMPLES; ++i)
    {
        uint8_t *sample = &payload[i * ADXL355_FIFO_BYTES_PER_SAMPLE];
        const int32_t base = static_cast<int32_t>(i) * 1000;
        encode_axis(&sample[0], 100000 + base, 0x01U); /* x-axis marker */
        encode_axis(&sample[3], -200000 + base, 0x00U);
        encode_axis(&sample[6], 300000 - base, 0x00U);
    }
    return payload;
}

}  // namespace

/* ---------------------------------------------------------------------------
 * Stateless decode / conversion helpers
 * --------------------------------------------------------------------------- */

static void BM_DecodeRaw20Batch(benchmark::State &state)
{
    std::vector<std::array<uint8_t, 3>> frames(kBatchSamples);
    const std::vector<int32_t> samples = raw_samples();
    for (std::size_t i = 0; i < kBatchSamples; ++i)
    {
        encode_axis(frames[i].data(), samples[i], 0U);
    }
    for (auto _ : state)
    {
        int64_t acc = 0;
        for (const auto &frame : frames)
        {
            acc += adxl355_decode_raw20(frame[0], frame[1], frame[2]);
        }
        benchmark::DoNotOptimize(acc);
    }
}
BENCHMARK(BM_DecodeRaw20Batch);

static void BM_RawToGBatch(benchmark::State &state, adxl355_range_t range)
{
    const std::vector<int32_t> samples = raw_samples();
    for (auto _ : state)
    {
        float acc = 0.0f;
        for (const int32_t raw : samples)
        {
            acc += adxl355_raw_to_g(raw, range);
        }
        benchmark::DoNotOptimize(acc);
    }
}
BENCHMARK_CAPTURE(BM_RawToGBatch, 2g, ADXL355_RANGE_2G);
BENCHMARK_CAPTURE(BM_RawToGBatch, 4g, ADXL355_RANGE_4G);
BENCHMARK_CAPTURE(BM_RawToGBatch, 8g, ADXL355_RANGE_8G);

static void BM_RawToMps2Batch(benchmark::State &state, adxl355_range_t range)
{
    const std::vector<int32_t> samples = raw_samples();
    for (auto _ : state)
    {
        float acc = 0.0f;
        for (const int32_t raw : samples)
        {
            acc += adxl355_raw_to_mps2(raw, range);
        }
        benchmark::DoNotOptimize(acc);
    }
}
BENCHMARK_CAPTURE(BM_RawToMps2Batch, 2g, ADXL355_RANGE_2G);
BENCHMARK_CAPTURE(BM_RawToMps2Batch, 4g, ADXL355_RANGE_4G);
BENCHMARK_CAPTURE(BM_RawToMps2Batch, 8g, ADXL355_RANGE_8G);

static void BM_DecodeFifoSampleBatch(benchmark::State &state)
{
    const auto payload = fifo_payload();
    for (auto _ : state)
    {
        int64_t acc = 0;
        for (std::size_t i = 0; i < ADXL355_FIFO_MAX_SAMPLES; ++i)
        {
            adxl355_raw_xyz_t sample{};
            const adxl355_status_t status =
                adxl355_decode_fifo_sample(&payload[i * ADXL355_FIFO_BYTES_PER_SAMPLE],
                                           ADXL355_FIFO_BYTES_PER_SAMPLE, &sample);
            acc += status + sample.x + sample.y + sample.z;
        }
        benchmark::DoNotOptimize(acc);
    }
}
BENCHMARK(BM_DecodeFifoSampleBatch);

static void BM_CalculateOffsetBatch(benchmark::State &state)
{
    const std::vector<int32_t> samples = raw_samples();
    for (auto _ : state)
    {
        int64_t acc = 0;
        for (const int32_t measured : samples)
        {
            int16_t offset = 0;
            const adxl355_status_t status = adxl355_calculate_offset(measured, 0, 0, true, &offset);
            acc += status + offset;
        }
        benchmark::DoNotOptimize(acc);
    }
}
BENCHMARK(BM_CalculateOffsetBatch);

/* ---------------------------------------------------------------------------
 * Device lifecycle and configuration
 * --------------------------------------------------------------------------- */

static void BM_Probe(benchmark::State &state)
{
    Fixture fx(state);
    for (auto _ : state)
    {
        benchmark::DoNotOptimize(adxl355_probe(&fx.dev));
    }
}
BENCHMARK(BM_Probe);

static void BM_ResetAndReprobe(benchmark::State &state)
{
    Fixture fx(state);
    for (auto _ : state)
    {
        benchmark::DoNotOptimize(adxl355_reset(&fx.dev));
        benchmark::DoNotOptimize(adxl355_probe(&fx.dev));
    }
}
BENCHMARK(BM_ResetAndReprobe);

static void BM_SetRangeCycle(benchmark::State &state)
{
    Fixture fx(state);
    for (auto _ : state)
    {
        benchmark::DoNotOptimize(adxl355_set_range(&fx.dev, ADXL355_RANGE_4G));
        benchmark::DoNotOptimize(adxl355_set_range(&fx.dev, ADXL355_RANGE_8G));
        benchmark::DoNotOptimize(adxl355_set_range(&fx.dev, ADXL355_RANGE_2G));
    }
}
BENCHMARK(BM_SetRangeCycle);

static void BM_SetOdrSweep(benchmark::State &state)
{
    Fixture fx(state);
    for (auto _ : state)
    {
        for (int odr = ADXL355_ODR_4000_HZ; odr <= ADXL355_ODR_3_906_HZ; ++odr)
        {
            benchmark::DoNotOptimize(adxl355_set_odr(&fx.dev, static_cast<adxl355_odr_t>(odr)));
        }
    }
}
BENCHMARK(BM_SetOdrSweep);

static void BM_ConfigureDataReady(benchmark::State &state)
{
    Fixture fx(state);
    adxl355_data_ready_config_t routed{};
    adxl355_data_ready_config_t dedicated{};
    require_ok(state, adxl355_data_ready_config_default(&dedicated));
    routed = dedicated;
    routed.route_to_int1 = true;
    routed.interrupt_polarity = ADXL355_INTERRUPT_ACTIVE_HIGH;
    for (auto _ : state)
    {
        benchmark::DoNotOptimize(adxl355_configure_data_ready(&fx.dev, &routed));
        benchmark::DoNotOptimize(adxl355_configure_data_ready(&fx.dev, &dedicated));
    }
}
BENCHMARK(BM_ConfigureDataReady);

static void BM_WriteReadOffsetXYZ(benchmark::State &state)
{
    Fixture fx(state);
    for (auto _ : state)
    {
        int32_t acc = 0;
        for (int axis = ADXL355_AXIS_X; axis <= ADXL355_AXIS_Z; ++axis)
        {
            const auto a = static_cast<adxl355_axis_t>(axis);
            int16_t offset = 0;
            acc += adxl355_write_offset(&fx.dev, a, static_cast<int16_t>(-1234 + axis));
            acc += adxl355_read_offset(&fx.dev, a, &offset);
            acc += offset;
        }
        benchmark::DoNotOptimize(acc);
    }
}
BENCHMARK(BM_WriteReadOffsetXYZ);

/* ---------------------------------------------------------------------------
 * Data readout through the transport
 * --------------------------------------------------------------------------- */

static void BM_ReadRaw(benchmark::State &state)
{
    Fixture fx(state);
    for (auto _ : state)
    {
        adxl355_raw_xyz_t out{};
        benchmark::DoNotOptimize(adxl355_read_raw(&fx.dev, &out));
        benchmark::DoNotOptimize(out);
    }
}
BENCHMARK(BM_ReadRaw);

static void BM_ReadMps2(benchmark::State &state)
{
    Fixture fx(state);
    for (auto _ : state)
    {
        adxl355_float_xyz_t out{};
        benchmark::DoNotOptimize(adxl355_read_mps2(&fx.dev, &out));
        benchmark::DoNotOptimize(out);
    }
}
BENCHMARK(BM_ReadMps2);

static void BM_ReadTemperatureC(benchmark::State &state)
{
    Fixture fx(state);
    for (auto _ : state)
    {
        float out = 0.0f;
        benchmark::DoNotOptimize(adxl355_read_temperature_c(&fx.dev, &out));
        benchmark::DoNotOptimize(out);
    }
}
BENCHMARK(BM_ReadTemperatureC);

/** Polling acquisition loop: N back-to-back g-unit samples. */
static void BM_ReadGBurst(benchmark::State &state)
{
    Fixture fx(state);
    const auto samples = static_cast<std::size_t>(state.range(0));
    for (auto _ : state)
    {
        float acc = 0.0f;
        for (std::size_t i = 0; i < samples; ++i)
        {
            adxl355_float_xyz_t out{};
            (void)adxl355_read_g(&fx.dev, &out);
            acc += out.x + out.y + out.z;
        }
        benchmark::DoNotOptimize(acc);
    }
}
BENCHMARK(BM_ReadGBurst)->Arg(64)->Arg(1024);

/** Drain a full 32-sample FIFO into caller-owned storage. */
static void BM_ReadFifoSamplesFull(benchmark::State &state)
{
    Fixture fx(state);
    const auto payload = fifo_payload();
    std::array<adxl355_raw_xyz_t, ADXL355_FIFO_MAX_SAMPLES> samples{};
    adxl355_mock_bus_set_fifo_payload(&fx.mock, payload.data(), payload.size(),
                                      static_cast<uint8_t>(ADXL355_FIFO_MAX_LOCATIONS));
    for (auto _ : state)
    {
        /* Refill the mock FIFO by rewinding it; cheaper than copying the payload. */
        fx.mock.fifo_offset = 0U;
        fx.mock.regs[ADXL355_REG_FIFO_ENTRIES] = static_cast<uint8_t>(ADXL355_FIFO_MAX_LOCATIONS);
        adxl355_fifo_read_result_t result{};
        const adxl355_status_t status =
            adxl355_read_fifo_samples(&fx.dev, samples.data(), samples.size(), &result);
        benchmark::DoNotOptimize(result);
        require_ok(state, status);
        benchmark::ClobberMemory();
    }
}
BENCHMARK(BM_ReadFifoSamplesFull);

/** Complete bounded self-test with the default 32-sample configuration. */
static void BM_RunSelfTest(benchmark::State &state)
{
    Fixture fx(state);
    adxl355_mock_bus_set_self_test_xyz(&fx.mock, adxl355_raw_xyz_t{1000, -1000, 64000},
                                       adxl355_raw_xyz_t{20000, -20000, 100000});
    adxl355_self_test_config_t config{};
    require_ok(state, adxl355_self_test_config_default(&config));
    for (auto _ : state)
    {
        adxl355_self_test_result_t result{};
        const adxl355_status_t status = adxl355_run_self_test(&fx.dev, &config, &result);
        benchmark::DoNotOptimize(result);
        require_ok(state, status);
    }
}
BENCHMARK(BM_RunSelfTest);

BENCHMARK_MAIN();
