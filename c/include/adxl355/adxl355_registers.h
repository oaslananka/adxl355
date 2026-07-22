#ifndef ADXL355_REGISTERS_H
#define ADXL355_REGISTERS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Register addresses */
#define ADXL355_REG_DEVID_AD      0x00U
#define ADXL355_REG_DEVID_MST     0x01U
#define ADXL355_REG_PARTID        0x02U
#define ADXL355_REG_REVID         0x03U
#define ADXL355_REG_STATUS        0x04U
#define ADXL355_REG_FIFO_ENTRIES  0x05U
#define ADXL355_REG_TEMP2         0x06U
#define ADXL355_REG_TEMP1         0x07U
#define ADXL355_REG_XDATA3        0x08U
#define ADXL355_REG_XDATA2        0x09U
#define ADXL355_REG_XDATA1        0x0AU
#define ADXL355_REG_YDATA3        0x0BU
#define ADXL355_REG_YDATA2        0x0CU
#define ADXL355_REG_YDATA1        0x0DU
#define ADXL355_REG_ZDATA3        0x0EU
#define ADXL355_REG_ZDATA2        0x0FU
#define ADXL355_REG_ZDATA1        0x10U
#define ADXL355_REG_FIFO_DATA     0x11U
#define ADXL355_REG_OFFSET_X_H    0x1EU
#define ADXL355_REG_OFFSET_X_L    0x1FU
#define ADXL355_REG_OFFSET_Y_H    0x20U
#define ADXL355_REG_OFFSET_Y_L    0x21U
#define ADXL355_REG_OFFSET_Z_H    0x22U
#define ADXL355_REG_OFFSET_Z_L    0x23U
#define ADXL355_REG_ACT_EN        0x24U
#define ADXL355_REG_ACT_THRESH_H  0x25U
#define ADXL355_REG_ACT_THRESH_L  0x26U
#define ADXL355_REG_ACT_COUNT     0x27U
#define ADXL355_REG_FILTER        0x28U
#define ADXL355_REG_FIFO_SAMPLES  0x29U
#define ADXL355_REG_INT_MAP       0x2AU
#define ADXL355_REG_SYNC          0x2BU
#define ADXL355_REG_RANGE         0x2CU
#define ADXL355_REG_POWER_CTL     0x2DU
#define ADXL355_REG_SELF_TEST     0x2EU
#define ADXL355_REG_RESET         0x2FU

/* Expected device ID values (datasheet Rev.D, Table 23-25) */
#define ADXL355_DEVID_AD         0xADU
#define ADXL355_DEVID_MST        0x1DU
#define ADXL355_PARTID_VALUE     0xEDU

/* Reset command (datasheet Rev.D, Table 45) */
#define ADXL355_RESET_CODE       0x52U

/* Power control register bits (datasheet Rev.D, Table 43) */
#define ADXL355_POWER_MODE_BIT   0U
/* bit 0 = 1: standby, bit 0 = 0: measurement */
#define ADXL355_POWER_STANDBY_VAL   1U
#define ADXL355_POWER_MEASUREMENT_VAL 0U
#define ADXL355_POWER_TEMP_OFF_BIT  1U
#define ADXL355_POWER_DRDY_OFF_BIT  2U

/* Range register (datasheet Rev.D, Table 42) */
#define ADXL355_RANGE_SEL_MASK   0x03U
/* Range field values: 0x01=2g, 0x02=4g, 0x03=8g */
#define ADXL355_RANGE_2G_VAL     0x01U
#define ADXL355_RANGE_4G_VAL     0x02U
#define ADXL355_RANGE_8G_VAL     0x03U
#define ADXL355_RANGE_INT_POL_BIT 6U
#define ADXL355_RANGE_I2C_HS_BIT  7U

/* Status register bits (datasheet Rev.D, Table 27) */
#define ADXL355_STATUS_NVM_BUSY    (1U << 4)
#define ADXL355_STATUS_ACTIVITY    (1U << 3)
#define ADXL355_STATUS_FIFO_OVR    (1U << 2)
#define ADXL355_STATUS_FIFO_FULL   (1U << 1)
#define ADXL355_STATUS_DATA_RDY    (1U << 0)

/* Filter register (datasheet Rev.D, Table 38) */
/* bits 3:0 = ODR_LPF, bits 6:4 = HPF_CORNER, bit 7 = reserved */
#define ADXL355_FILTER_ODR_MASK   0x0FU
#define ADXL355_FILTER_ODR_SHIFT  0U
#define ADXL355_FILTER_HPF_MASK   0x70U
#define ADXL355_FILTER_HPF_SHIFT  4U

/* Activity enable bits (datasheet Rev.D, Table 35) */
#define ADXL355_ACT_EN_Z          (1U << 3)
#define ADXL355_ACT_EN_Y          (1U << 2)
#define ADXL355_ACT_EN_X          (1U << 1)

/* SPI command byte helpers (datasheet Rev.D, SPI Protocol section) */
#define ADXL355_SPI_READ_CMD(reg)   (((reg) << 1) | 0x01U)
#define ADXL355_SPI_WRITE_CMD(reg)  ((reg) << 1)

/* I2C addresses (datasheet Rev.D, Table 8) */
#define ADXL355_I2C_ADDR_DEFAULT   0x1DU
#define ADXL355_I2C_ADDR_ALTERNATE 0x53U

#ifdef __cplusplus
}
#endif

#endif /* ADXL355_REGISTERS_H */
