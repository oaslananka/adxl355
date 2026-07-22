"""
Hardware adapter implementations for ADXL355.

spidev: Linux SPI via the spidev package (Mode 0: CPOL=0, CPHA=0)
smbus2: Linux I2C via the smbus2 package

These are optional dependencies – install with:
    pip install adxl355[spi]
    pip install adxl355[i2c]
"""
