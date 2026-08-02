// Package linuxio provides maintained Linux spidev and i2c-dev transports for
// the portable adxl355.Transport contract.
package linuxio

import (
	"errors"
	"fmt"
)

const (
	// MinimumSPISpeedHz is the ADXL355 datasheet minimum supported SPI clock.
	MinimumSPISpeedHz uint32 = 100_000
	// MaximumSPISpeedHz is the ADXL355 datasheet maximum supported SPI clock.
	MaximumSPISpeedHz uint32 = 10_000_000
	// MaximumRegisterAddress is the final address in the ADXL355 Rev.D register map.
	MaximumRegisterAddress byte = 0x2F
	// MaximumTransferLength bounds one register payload to a 4096-byte spidev
	// transaction after adding the command byte.
	MaximumTransferLength = 4095
)

var (
	// ErrClosed reports an operation attempted after Close.
	ErrClosed = errors.New("linux transport is closed")
	// ErrInvalidConfig reports an invalid bus, address, mode, speed, register,
	// or transfer length.
	ErrInvalidConfig = errors.New("invalid linux transport configuration")
	// ErrShortTransfer reports a kernel transaction that completed fewer or
	// more bytes/messages than requested without returning an errno.
	ErrShortTransfer = errors.New("non-exact linux device transfer")
	// ErrUnsupported reports construction on a non-Linux platform.
	ErrUnsupported = errors.New("linux device transport is unsupported on this platform")
)

// OpError preserves a stable operation/path context and the underlying errno or
// sentinel error. Use errors.Is and errors.As to inspect it.
type OpError struct {
	Transport string
	Operation string
	Path      string
	Err       error
}

func (e *OpError) Error() string {
	return fmt.Sprintf("adxl355 %s %s %s: %v", e.Transport, e.Operation, e.Path, e.Err)
}

// Unwrap exposes the underlying errno or stable transport sentinel.
func (e *OpError) Unwrap() error { return e.Err }

// SPIConfig selects one Linux spidev node. ADXL355 supports only Mode 0.
type SPIConfig struct {
	Bus     int
	Device  int
	Mode    uint8
	SpeedHz uint32
}

// DefaultSPIConfig returns /dev/spidev0.0, Mode 0, at 1 MHz.
func DefaultSPIConfig() SPIConfig {
	return SPIConfig{Bus: 0, Device: 0, Mode: 0, SpeedHz: 1_000_000}
}

// I2CConfig selects one Linux i2c-dev adapter and ADXL355 address. BusHz records
// the externally configured adapter clock; i2c-dev does not set it per device.
type I2CConfig struct {
	Bus     int
	Address uint16
	BusHz   uint32
}

// DefaultI2CConfig returns /dev/i2c-1, address 0x1D, at a declared 400 kHz.
func DefaultI2CConfig() I2CConfig {
	return I2CConfig{Bus: 1, Address: 0x1D, BusHz: 400_000}
}

func validateNodeIndex(value int) bool { return value >= 0 && value <= 255 }

func validateRegister(reg byte) error {
	if reg > MaximumRegisterAddress {
		return fmt.Errorf("%w: register 0x%02X outside ADXL355 map 0x00..0x%02X", ErrInvalidConfig, reg, MaximumRegisterAddress)
	}
	return nil
}

func validateLength(length int) error {
	if length < 1 || length > MaximumTransferLength {
		return fmt.Errorf(
			"%w: transfer length %d outside 1..%d",
			ErrInvalidConfig,
			length,
			MaximumTransferLength,
		)
	}
	return nil
}

func validateSPIConfig(config SPIConfig) error {
	if !validateNodeIndex(config.Bus) || !validateNodeIndex(config.Device) {
		return fmt.Errorf("%w: SPI bus/device must be in 0..255", ErrInvalidConfig)
	}
	if config.Mode != 0 {
		return fmt.Errorf("%w: ADXL355 requires SPI Mode 0", ErrInvalidConfig)
	}
	if config.SpeedHz < MinimumSPISpeedHz || config.SpeedHz > MaximumSPISpeedHz {
		return fmt.Errorf(
			"%w: SPI speed %d outside %d..%d Hz",
			ErrInvalidConfig,
			config.SpeedHz,
			MinimumSPISpeedHz,
			MaximumSPISpeedHz,
		)
	}
	return nil
}

func validateI2CConfig(config I2CConfig) error {
	if !validateNodeIndex(config.Bus) {
		return fmt.Errorf("%w: I2C bus must be in 0..255", ErrInvalidConfig)
	}
	if config.Address != 0x1D && config.Address != 0x53 {
		return fmt.Errorf("%w: I2C address must be 0x1D or 0x53", ErrInvalidConfig)
	}
	switch config.BusHz {
	case 100_000, 400_000, 1_000_000, 3_400_000:
		return nil
	default:
		return fmt.Errorf(
			"%w: declared I2C bus speed must be 100000, 400000, 1000000, or 3400000 Hz",
			ErrInvalidConfig,
		)
	}
}
