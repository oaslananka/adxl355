#include <adxl355/adxl355.h>

#include <string.h>

int main(void)
{
    return strcmp(adxl355_status_string(ADXL355_OK), "ADXL355_OK") == 0 ? 0 : 1;
}
