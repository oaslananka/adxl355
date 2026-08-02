#include <adxl355/adxl355.hpp>

#include <cstddef>
#include <cstdint>

class ConsumerBus final : public adxl355::BusInterface {
public:
    int read(void *, uint8_t, uint8_t *, size_t) override { return -1; }
    int write(void *, uint8_t, const uint8_t *, size_t) override { return -1; }
    void delayMs(void *, uint32_t) override {}
};

int main()
{
    ConsumerBus bus;
    adxl355::NoexceptDevice device(bus);
    return device.initStatus() == adxl355::Status::Ok ? 0 : 1;
}
