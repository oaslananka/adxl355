"""
ADXL355 scaling constants.

Based on ADXL354/ADXL355 Rev.D datasheet.
"""

# Scale factors (g per LSB) for each range setting
# Datasheet Rev.D, Table 2: sensitivity ±2g = 256,000 LSB/g (3.9 µg/LSB)
SCALE_2G_G_PER_LSB: float = 0.0000039
# Sensitivity ±4g = 128,000 LSB/g (7.8 µg/LSB)
SCALE_4G_G_PER_LSB: float = 0.0000078
# Sensitivity ±8g = 64,000 LSB/g (15.6 µg/LSB)
SCALE_8G_G_PER_LSB: float = 0.0000156

# Standard gravity (m/s²)
STANDARD_GRAVITY_M_S2: float = 9.80665

# Expected identity register values (datasheet Rev.D, Tables 23-25)
DEVID_AD: int = 0xAD
DEVID_MST: int = 0x1D
PARTID: int = 0xED

# Software reset code (datasheet Rev.D, Table 45)
RESET_CODE: int = 0x52

# I2C addresses (datasheet Rev.D, Table 8)
# ASEL pin = GND: 0x1D, ASEL pin = VDDIO: 0x53
ADXL355_I2C_ADDRESS_DEFAULT: int = 0x1D
ADXL355_I2C_ADDRESS_ALTERNATE: int = 0x53


# Temperature sensor constants (datasheet Rev.D, Table 29 and sensor section)
TEMP2_DATA_MASK: int = 0x0F
TEMP_READ_ATTEMPTS: int = 3
TEMP_INTERCEPT_LSB: float = 1885.0
TEMP_INTERCEPT_C: float = 25.0
TEMP_SLOPE_LSB_PER_C: float = -9.05
