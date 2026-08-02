//go:build !linux || (!amd64 && !arm64)

package linuxio

import (
	"fmt"

	"github.com/oaslananka/adxl355/go/adxl355"
)

// SPITransport is unavailable outside Linux.
type SPITransport struct{}

var _ adxl355.Transport = (*SPITransport)(nil)

// OpenSPI reports ErrUnsupported outside Linux after validating the config.
func OpenSPI(config SPIConfig) (*SPITransport, error) {
	path := fmt.Sprintf("/dev/spidev%d.%d", config.Bus, config.Device)
	if err := validateSPIConfig(config); err != nil {
		return nil, &OpError{Transport: "spi", Operation: "validate", Path: path, Err: err}
	}
	return nil, &OpError{Transport: "spi", Operation: "open", Path: path, Err: ErrUnsupported}
}

// Close is a no-op for an unavailable non-Linux transport.
func (*SPITransport) Close() error { return nil }

// ReadRegister reports ErrUnsupported outside Linux.
func (*SPITransport) ReadRegister(_ byte, _ int) ([]byte, error) {
	return nil, &OpError{Transport: "spi", Operation: "read", Path: "spidev", Err: ErrUnsupported}
}

// WriteRegister reports ErrUnsupported outside Linux.
func (*SPITransport) WriteRegister(_ byte, _ []byte) error {
	return &OpError{Transport: "spi", Operation: "write", Path: "spidev", Err: ErrUnsupported}
}

// DelayMs is a no-op for an unavailable non-Linux transport.
func (*SPITransport) DelayMs(uint32) {}

// I2CTransport is unavailable outside Linux.
type I2CTransport struct{}

var _ adxl355.Transport = (*I2CTransport)(nil)

// OpenI2C reports ErrUnsupported outside Linux after validating the config.
func OpenI2C(config I2CConfig) (*I2CTransport, error) {
	path := fmt.Sprintf("/dev/i2c-%d", config.Bus)
	if err := validateI2CConfig(config); err != nil {
		return nil, &OpError{Transport: "i2c", Operation: "validate", Path: path, Err: err}
	}
	return nil, &OpError{Transport: "i2c", Operation: "open", Path: path, Err: ErrUnsupported}
}

// Close is a no-op for an unavailable non-Linux transport.
func (*I2CTransport) Close() error { return nil }

// ReadRegister reports ErrUnsupported outside Linux.
func (*I2CTransport) ReadRegister(_ byte, _ int) ([]byte, error) {
	return nil, &OpError{Transport: "i2c", Operation: "read", Path: "i2c-dev", Err: ErrUnsupported}
}

// WriteRegister reports ErrUnsupported outside Linux.
func (*I2CTransport) WriteRegister(_ byte, _ []byte) error {
	return &OpError{Transport: "i2c", Operation: "write", Path: "i2c-dev", Err: ErrUnsupported}
}

// DelayMs is a no-op for an unavailable non-Linux transport.
func (*I2CTransport) DelayMs(uint32) {}

// DeclaredBusHz returns zero for an unavailable non-Linux transport.
func (*I2CTransport) DeclaredBusHz() uint32 { return 0 }
