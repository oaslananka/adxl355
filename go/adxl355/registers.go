package adxl355

// Register addresses for the ADXL355.
// Based on ADXL354/ADXL355 Rev.D datasheet.
const (
	RegDEVID_AD     = 0x00
	RegDEVID_MST    = 0x01
	RegPARTID       = 0x02
	RegREVID        = 0x03
	RegSTATUS       = 0x04
	RegFIFO_ENTRIES = 0x05
	RegTEMP2        = 0x06
	RegTEMP1        = 0x07
	RegXDATA3       = 0x08
	RegXDATA2       = 0x09
	RegXDATA1       = 0x0A
	RegYDATA3       = 0x0B
	RegYDATA2       = 0x0C
	RegYDATA1       = 0x0D
	RegZDATA3       = 0x0E
	RegZDATA2       = 0x0F
	RegZDATA1       = 0x10
	RegFIFO_DATA    = 0x11
	RegOFFSET_X_H   = 0x1E
	RegOFFSET_X_L   = 0x1F
	RegOFFSET_Y_H   = 0x20
	RegOFFSET_Y_L   = 0x21
	RegOFFSET_Z_H   = 0x22
	RegOFFSET_Z_L   = 0x23
	RegACT_EN       = 0x24
	RegACT_THRESH_H = 0x25
	RegACT_THRESH_L = 0x26
	RegACT_COUNT    = 0x27
	RegFILTER       = 0x28
	RegFIFO_SAMPLES = 0x29
	RegINT_MAP      = 0x2A
	RegSYNC         = 0x2B
	RegRANGE        = 0x2C
	RegPOWER_CTL    = 0x2D
	RegSELF_TEST    = 0x2E
	RegRESET        = 0x2F
)

// Expected identity register values (datasheet Rev.D, Tables 23-25).
const (
	DEVID_AD_VALUE  = 0xAD
	DEVID_MST_VALUE = 0x1D
	PARTID_VALUE    = 0xED
)

// Reset code (datasheet Rev.D, Table 45).
const RESET_CODE = 0x52

// Temperature sensor constants (datasheet Rev.D, Table 29 and sensor section).
const (
	Temp2DataMask    = 0x0F
	TempReadAttempts = 3
	TempInterceptLSB = 1885.0
	TempInterceptC   = 25.0
	TempSlopeLSBPerC = -9.05
)

// STATUS register bit positions (datasheet Rev.D, Table 27).
const (
	StatusNVM_BUSY  = 4
	StatusACTIVITY  = 3
	StatusFIFO_OVR  = 2
	StatusFIFO_FULL = 1
	StatusDATA_RDY  = 0
)

// FILTER register masks (datasheet Rev.D, Table 38).
const (
	FilterODR_MASK  = 0x0F
	FilterODR_SHIFT = 0
	FilterHPF_MASK  = 0x70
	FilterHPF_SHIFT = 4
)

// RANGE register mask (datasheet Rev.D, Table 42).
const RangeSEL_MASK = 0x03

// SPI command helpers (datasheet Rev.D, SPI Protocol section).
func SPIReadCmd(reg uint8) uint8  { return (reg << 1) | 0x01 }
func SPIWriteCmd(reg uint8) uint8 { return reg << 1 }

// I2C addresses (datasheet Rev.D, Table 8).
const (
	I2CDefaultAddr   = 0x1D
	I2CAlternateAddr = 0x53
)

// Acceleration range (datasheet Rev.D, Table 42).
type Range int

const (
	Range2G Range = 0x01
	Range4G Range = 0x02
	Range8G Range = 0x03
)

// Scale factors (g per LSB).
const (
	Scale2GGPerLSB = 0.0000039
	Scale4GGPerLSB = 0.0000078
	Scale8GGPerLSB = 0.0000156
)

// Standard gravity in m/s².
const StandardGravityMS2 = 9.80665

// Power mode (datasheet Rev.D, Table 43: bit 0 = 1 => standby).
type PowerMode int

const (
	PowerStandby     PowerMode = 1
	PowerMeasurement PowerMode = 0
)

// Output data rate.
type ODR int

const (
	ODR4000Hz   ODR = 0
	ODR2000Hz   ODR = 1
	ODR1000Hz   ODR = 2
	ODR500Hz    ODR = 3
	ODR250Hz    ODR = 4
	ODR125Hz    ODR = 5
	ODR62_5Hz   ODR = 6
	ODR31_25Hz  ODR = 7
	ODR15_625Hz ODR = 8
	ODR7_813Hz  ODR = 9
	ODR3_906Hz  ODR = 10
)
