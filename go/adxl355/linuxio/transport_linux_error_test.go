//go:build linux && (amd64 || arm64)

package linuxio

import (
	"errors"
	"testing"

	"golang.org/x/sys/unix"
)

// These tests exercise real Linux errno handling only through invalid file
// descriptors or an impossible pathname. No physical SPI/I2C node is opened.
func TestUnixSystemRejectsInvalidDescriptors(t *testing.T) {
	sys := unixSystem{}

	if _, err := sys.open("/dev/adxl355-not-present/nested", unix.O_RDONLY, 0); !errors.Is(err, unix.ENOENT) {
		t.Fatalf("open nonexistent path: got %v, want ENOENT", err)
	}
	if err := sys.close(-1); !errors.Is(err, unix.EBADF) {
		t.Fatalf("close invalid fd: got %v, want EBADF", err)
	}
	if err := sys.configureSPI(-1, 0, 8, 1_000_000); !errors.Is(err, unix.EBADF) {
		t.Fatalf("configure SPI invalid fd: got %v, want EBADF", err)
	}
	if n, err := sys.transferSPI(-1, []byte{0x01, 0x00}, make([]byte, 2), 1_000_000); n != 0 || !errors.Is(err, unix.EBADF) {
		t.Fatalf("SPI transfer invalid fd: got (%d, %v), want EBADF", n, err)
	}
	if functions, err := sys.i2cFunctions(-1); functions != 0 || !errors.Is(err, unix.EBADF) {
		t.Fatalf("query I2C functions invalid fd: got (%#x, %v), want EBADF", functions, err)
	}
	if err := sys.selectI2CAddress(-1, 0x1D); !errors.Is(err, unix.EBADF) {
		t.Fatalf("select I2C address invalid fd: got %v, want EBADF", err)
	}
	operations := []i2cOperation{
		{address: 0x1D, data: []byte{0x00}},
		{address: 0x1D, read: true, data: make([]byte, 3)},
	}
	if n, err := sys.transferI2C(-1, operations); n != 0 || !errors.Is(err, unix.EBADF) {
		t.Fatalf("I2C transfer invalid fd: got (%d, %v), want EBADF", n, err)
	}
}

// Public wrappers should reject an invalid configuration before accessing any
// Linux device. The fake records attempted calls to make this guarantee clear.
func TestPublicOpenRejectsInvalidConfigBeforeHardware(t *testing.T) {
	spi := SPIConfig{Bus: -1, Device: 0, Mode: 0, SpeedHz: 1_000_000}
	if _, err := OpenSPI(spi); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("OpenSPI invalid config: got %v, want ErrInvalidConfig", err)
	}
	i2c := I2CConfig{Bus: -1, Address: 0x1D, BusHz: 400_000}
	if _, err := OpenI2C(i2c); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("OpenI2C invalid config: got %v, want ErrInvalidConfig", err)
	}
	fake := &fakeSystem{}
	if _, err := openSPI(spi, fake); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("openSPI invalid config: got %v", err)
	}
	if _, err := openI2C(i2c, fake); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("openI2C invalid config: got %v", err)
	}
	if fake.openPath != "" || fake.closeCount != 0 {
		t.Fatalf("invalid config touched system: path=%q closes=%d", fake.openPath, fake.closeCount)
	}
}

func TestOpenLinuxTransportsWrapOpenAndSetupFailures(t *testing.T) {
	t.Run("spi open", func(t *testing.T) {
		fake := &fakeSystem{openError: unix.ENOENT}
		_, err := openSPI(DefaultSPIConfig(), fake)
		if !errors.Is(err, unix.ENOENT) || fake.closeCount != 0 {
			t.Fatalf("openSPI failed: err=%v closes=%d", err, fake.closeCount)
		}
	})
	t.Run("i2c open", func(t *testing.T) {
		fake := &fakeSystem{openError: unix.EACCES}
		_, err := openI2C(DefaultI2CConfig(), fake)
		if !errors.Is(err, unix.EACCES) || fake.closeCount != 0 {
			t.Fatalf("openI2C failed: err=%v closes=%d", err, fake.closeCount)
		}
	})
	t.Run("i2c capability query", func(t *testing.T) {
		fake := &fakeSystem{functionsError: unix.EIO}
		_, err := openI2C(DefaultI2CConfig(), fake)
		if !errors.Is(err, unix.EIO) || fake.closeCount != 1 {
			t.Fatalf("I2C query failed: err=%v closes=%d", err, fake.closeCount)
		}
	})
	t.Run("i2c address select", func(t *testing.T) {
		fake := &fakeSystem{functions: i2cFuncI2C, selectError: unix.EBUSY}
		_, err := openI2C(DefaultI2CConfig(), fake)
		if !errors.Is(err, unix.EBUSY) || fake.closeCount != 1 {
			t.Fatalf("I2C select failed: err=%v closes=%d", err, fake.closeCount)
		}
	})
}

func TestSPIRejectsInvalidRegisterLengthAndWriteTransfer(t *testing.T) {
	fake := &fakeSystem{}
	transport, err := openSPI(DefaultSPIConfig(), fake)
	if err != nil {
		t.Fatal(err)
	}
	defer transport.Close()

	if _, err := transport.ReadRegister(MaximumRegisterAddress+1, 1); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("SPI invalid read register: %v", err)
	}
	if _, err := transport.ReadRegister(0, 0); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("SPI invalid read length: %v", err)
	}
	if err := transport.WriteRegister(MaximumRegisterAddress+1, []byte{0}); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("SPI invalid write register: %v", err)
	}
	if err := transport.WriteRegister(0, nil); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("SPI invalid write length: %v", err)
	}
	if len(fake.spiTX) != 0 {
		t.Fatalf("invalid SPI requests unexpectedly transferred %v", fake.spiTX)
	}

	fake.spiResult = 1 // command plus one payload byte must transfer atomically
	if err := transport.WriteRegister(0x2D, []byte{0x01}); !errors.Is(err, ErrShortTransfer) {
		t.Fatalf("SPI short write: %v", err)
	}
	fake.spiResult = 0
	fake.spiError = unix.EIO
	if err := transport.WriteRegister(0x2D, []byte{0x01}); !errors.Is(err, unix.EIO) {
		t.Fatalf("SPI write syscall failure: %v", err)
	}
	transport.DelayMs(0)
	if err := transport.Close(); err != nil {
		t.Fatal(err)
	}
	if err := transport.WriteRegister(0x2D, []byte{0x01}); !errors.Is(err, ErrClosed) {
		t.Fatalf("SPI write after close: %v", err)
	}
}

func TestI2CRejectsInvalidRegisterLengthAndTransfer(t *testing.T) {
	fake := &fakeSystem{functions: i2cFuncI2C}
	transport, err := openI2C(DefaultI2CConfig(), fake)
	if err != nil {
		t.Fatal(err)
	}
	defer transport.Close()

	if _, err := transport.ReadRegister(MaximumRegisterAddress+1, 1); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("I2C invalid read register: %v", err)
	}
	if _, err := transport.ReadRegister(0, 0); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("I2C invalid read length: %v", err)
	}
	if err := transport.WriteRegister(MaximumRegisterAddress+1, []byte{0}); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("I2C invalid write register: %v", err)
	}
	if err := transport.WriteRegister(0, nil); !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("I2C invalid write length: %v", err)
	}
	if len(fake.i2cCommand) != 0 || len(fake.i2cWrite) != 0 {
		t.Fatalf("invalid I2C requests were sent: cmd=%v write=%v", fake.i2cCommand, fake.i2cWrite)
	}

	fake.i2cError = unix.EIO
	if _, err := transport.ReadRegister(0, 1); !errors.Is(err, unix.EIO) {
		t.Fatalf("I2C read ioctl failure: %v", err)
	}
	fake.i2cError = nil
	fake.i2cResult = 2 // single write needs exactly one completed message
	if err := transport.WriteRegister(0x2D, []byte{0x01}); !errors.Is(err, ErrShortTransfer) {
		t.Fatalf("I2C incorrect write message count: %v", err)
	}
	fake.i2cResult = 0
	fake.i2cError = unix.EACCES
	if err := transport.WriteRegister(0x2D, []byte{0x01}); !errors.Is(err, unix.EACCES) {
		t.Fatalf("I2C write ioctl failure: %v", err)
	}
	transport.DelayMs(0)
	if err := transport.Close(); err != nil {
		t.Fatal(err)
	}
	if err := transport.WriteRegister(0x2D, []byte{0x01}); !errors.Is(err, ErrClosed) {
		t.Fatalf("I2C write after close: %v", err)
	}
}
