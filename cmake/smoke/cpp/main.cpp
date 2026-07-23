#include <adxl355/adxl355.hpp>

int main()
{
    return adxl355::Device::decodeRaw20(0U, 0U, 0U) == 0 ? 0 : 1;
}
