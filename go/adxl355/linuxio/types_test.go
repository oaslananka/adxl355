package linuxio

import (
	"errors"
	"testing"
)

func TestSPIConfigValidation(t *testing.T) {
	valid := DefaultSPIConfig()
	if err := validateSPIConfig(valid); err != nil {
		t.Fatalf("default SPI config rejected: %v", err)
	}
	cases := []SPIConfig{
		{Bus: -1, Device: 0, Mode: 0, SpeedHz: 1_000_000},
		{Bus: 0, Device: 256, Mode: 0, SpeedHz: 1_000_000},
		{Bus: 0, Device: 0, Mode: 1, SpeedHz: 1_000_000},
		{Bus: 0, Device: 0, Mode: 0, SpeedHz: 99_999},
		{Bus: 0, Device: 0, Mode: 0, SpeedHz: 10_000_001},
	}
	for _, config := range cases {
		if !errors.Is(validateSPIConfig(config), ErrInvalidConfig) {
			t.Fatalf("invalid SPI config accepted: %+v", config)
		}
	}
}

func TestI2CConfigValidation(t *testing.T) {
	valid := DefaultI2CConfig()
	if err := validateI2CConfig(valid); err != nil {
		t.Fatalf("default I2C config rejected: %v", err)
	}
	for _, speed := range []uint32{100_000, 400_000, 1_000_000, 3_400_000} {
		config := valid
		config.BusHz = speed
		if err := validateI2CConfig(config); err != nil {
			t.Fatalf("documented speed %d rejected: %v", speed, err)
		}
	}
	cases := []I2CConfig{
		{Bus: -1, Address: 0x1D, BusHz: 400_000},
		{Bus: 1, Address: 0x20, BusHz: 400_000},
		{Bus: 1, Address: 0x1D, BusHz: 123_456},
	}
	for _, config := range cases {
		if !errors.Is(validateI2CConfig(config), ErrInvalidConfig) {
			t.Fatalf("invalid I2C config accepted: %+v", config)
		}
	}
}

func TestRegisterAndLengthValidation(t *testing.T) {
	if err := validateRegister(MaximumRegisterAddress); err != nil {
		t.Fatalf("last bounded register rejected: %v", err)
	}
	if !errors.Is(validateRegister(MaximumRegisterAddress+1), ErrInvalidConfig) {
		t.Fatal("register outside map should be rejected")
	}
	for _, length := range []int{0, MaximumTransferLength + 1} {
		if !errors.Is(validateLength(length), ErrInvalidConfig) {
			t.Fatalf("invalid length %d accepted", length)
		}
	}
}

func TestOpErrorUnwrap(t *testing.T) {
	err := &OpError{Transport: "spi", Operation: "open", Path: "/dev/spidev0.0", Err: ErrClosed}
	if !errors.Is(err, ErrClosed) {
		t.Fatal("OpError should unwrap its cause")
	}
	if got := err.Error(); got != "adxl355 spi open /dev/spidev0.0: linux transport is closed" {
		t.Fatalf("unexpected error string: %q", got)
	}
}
