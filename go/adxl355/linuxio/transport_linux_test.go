//go:build linux && (amd64 || arm64)

package linuxio

import (
	"errors"
	"syscall"
	"testing"
	"unsafe"

	"golang.org/x/sys/unix"
)

type fakeSystem struct {
	openPath       string
	openFlags      int
	openError      error
	closeError     error
	closeCount     int
	configureError error
	mode           uint8
	bits           uint8
	speed          uint32
	address        uint16
	functions      uintptr
	spiResponse    []byte
	spiTX          []byte
	spiResult      int
	spiError       error
	i2cReadData    []byte
	i2cCommand     []byte
	i2cWrite       []byte
	i2cResult      int
	i2cError       error
	functionsError error
	selectError    error
}

func (f *fakeSystem) open(path string, flags int, mode uint32) (int, error) {
	f.openPath = path
	f.openFlags = flags
	if f.openError != nil {
		return 0, f.openError
	}
	return 42, nil
}

func (f *fakeSystem) close(fd int) error {
	f.closeCount++
	return f.closeError
}

func (f *fakeSystem) configureSPI(fd int, mode uint8, bits uint8, speedHz uint32) error {
	f.mode = mode
	f.bits = bits
	f.speed = speedHz
	return f.configureError
}

func (f *fakeSystem) transferSPI(
	fd int,
	tx []byte,
	rx []byte,
	speedHz uint32,
) (int, error) {
	f.spiTX = append([]byte(nil), tx...)
	copy(rx, f.spiResponse)
	if f.spiError != nil {
		return 0, f.spiError
	}
	if f.spiResult != 0 {
		return f.spiResult, nil
	}
	return len(tx), nil
}

func (f *fakeSystem) i2cFunctions(fd int) (uintptr, error) {
	return f.functions, f.functionsError
}

func (f *fakeSystem) selectI2CAddress(fd int, address uint16) error {
	f.address = address
	return f.selectError
}

func (f *fakeSystem) transferI2C(fd int, operations []i2cOperation) (int, error) {
	if len(operations) == 2 {
		f.i2cCommand = append([]byte(nil), operations[0].data...)
		copy(operations[1].data, f.i2cReadData)
	} else if len(operations) == 1 {
		f.i2cWrite = append([]byte(nil), operations[0].data...)
	}
	if f.i2cError != nil {
		return 0, f.i2cError
	}
	if f.i2cResult != 0 {
		return f.i2cResult, nil
	}
	return len(operations), nil
}

func TestOpenSPIConfiguresNodeAndCloseOwnership(t *testing.T) {
	fake := &fakeSystem{}
	transport, err := openSPI(SPIConfig{Bus: 2, Device: 1, Mode: 0, SpeedHz: 2_000_000}, fake)
	if err != nil {
		t.Fatalf("openSPI failed: %v", err)
	}
	if fake.openPath != "/dev/spidev2.1" {
		t.Fatalf("path = %q", fake.openPath)
	}
	if fake.openFlags != unix.O_RDWR|unix.O_CLOEXEC {
		t.Fatalf("flags = %#x", fake.openFlags)
	}
	if fake.mode != 0 || fake.bits != 8 || fake.speed != 2_000_000 {
		t.Fatalf("configured mode/bits/speed = %d/%d/%d", fake.mode, fake.bits, fake.speed)
	}
	if err := transport.Close(); err != nil {
		t.Fatalf("Close failed: %v", err)
	}
	if err := transport.Close(); err != nil {
		t.Fatalf("second Close failed: %v", err)
	}
	if fake.closeCount != 1 {
		t.Fatalf("close count = %d, want 1", fake.closeCount)
	}
	if _, err := transport.ReadRegister(0, 1); !errors.Is(err, ErrClosed) {
		t.Fatalf("read after close = %v, want ErrClosed", err)
	}
}

func TestOpenSPIClosesOnConfigurationFailure(t *testing.T) {
	fake := &fakeSystem{configureError: syscall.EIO}
	_, err := openSPI(DefaultSPIConfig(), fake)
	if !errors.Is(err, syscall.EIO) {
		t.Fatalf("error = %v, want EIO", err)
	}
	if fake.closeCount != 1 {
		t.Fatalf("close count = %d, want 1", fake.closeCount)
	}
}

func TestSPIReadAndWriteFraming(t *testing.T) {
	fake := &fakeSystem{spiResponse: []byte{0x00, 0xAD, 0x1D, 0xED}}
	transport, err := openSPI(DefaultSPIConfig(), fake)
	if err != nil {
		t.Fatalf("openSPI failed: %v", err)
	}
	defer transport.Close()

	data, err := transport.ReadRegister(0x00, 3)
	if err != nil {
		t.Fatalf("ReadRegister failed: %v", err)
	}
	if want := []byte{0xAD, 0x1D, 0xED}; !equalBytes(data, want) {
		t.Fatalf("read = %v, want %v", data, want)
	}
	if want := []byte{0x01, 0x00, 0x00, 0x00}; !equalBytes(fake.spiTX, want) {
		t.Fatalf("read TX = %v, want %v", fake.spiTX, want)
	}

	fake.spiResponse = nil
	if err := transport.WriteRegister(0x2D, []byte{0x01}); err != nil {
		t.Fatalf("WriteRegister failed: %v", err)
	}
	if want := []byte{0x5A, 0x01}; !equalBytes(fake.spiTX, want) {
		t.Fatalf("write TX = %v, want %v", fake.spiTX, want)
	}
}

func TestSPIExactTransferAndErrnoWrapping(t *testing.T) {
	fake := &fakeSystem{spiResult: 1}
	transport, err := openSPI(DefaultSPIConfig(), fake)
	if err != nil {
		t.Fatalf("openSPI failed: %v", err)
	}
	defer transport.Close()
	if _, err := transport.ReadRegister(0, 1); !errors.Is(err, ErrShortTransfer) {
		t.Fatalf("short transfer = %v, want ErrShortTransfer", err)
	}
	fake.spiResult = 0
	fake.spiError = syscall.EIO
	if _, err := transport.ReadRegister(0, 1); !errors.Is(err, syscall.EIO) {
		t.Fatalf("ioctl error = %v, want EIO", err)
	}
}

func TestOpenI2CQueriesCapabilitiesAndSelectsAddress(t *testing.T) {
	fake := &fakeSystem{functions: i2cFuncI2C}
	transport, err := openI2C(I2CConfig{Bus: 3, Address: 0x53, BusHz: 1_000_000}, fake)
	if err != nil {
		t.Fatalf("openI2C failed: %v", err)
	}
	defer transport.Close()
	if fake.openPath != "/dev/i2c-3" || fake.address != 0x53 {
		t.Fatalf("path/address = %q/%#x", fake.openPath, fake.address)
	}
	if transport.DeclaredBusHz() != 1_000_000 {
		t.Fatalf("declared bus Hz = %d", transport.DeclaredBusHz())
	}
}

func TestOpenI2CRejectsAdapterWithoutCombinedI2C(t *testing.T) {
	fake := &fakeSystem{}
	_, err := openI2C(DefaultI2CConfig(), fake)
	if !errors.Is(err, ErrUnsupported) {
		t.Fatalf("error = %v, want ErrUnsupported", err)
	}
	if fake.closeCount != 1 {
		t.Fatalf("close count = %d, want 1", fake.closeCount)
	}
}

func TestI2CCombinedReadAndWriteFraming(t *testing.T) {
	fake := &fakeSystem{functions: i2cFuncI2C, i2cReadData: []byte{0xAD, 0x1D, 0xED}}
	transport, err := openI2C(DefaultI2CConfig(), fake)
	if err != nil {
		t.Fatalf("openI2C failed: %v", err)
	}
	defer transport.Close()
	data, err := transport.ReadRegister(0x00, 3)
	if err != nil {
		t.Fatalf("ReadRegister failed: %v", err)
	}
	if !equalBytes(fake.i2cCommand, []byte{0x00}) || !equalBytes(data, []byte{0xAD, 0x1D, 0xED}) {
		t.Fatalf("command/data = %v/%v", fake.i2cCommand, data)
	}
	if err := transport.WriteRegister(0x2D, []byte{0x01}); err != nil {
		t.Fatalf("WriteRegister failed: %v", err)
	}
	if !equalBytes(fake.i2cWrite, []byte{0x2D, 0x01}) {
		t.Fatalf("write payload = %v", fake.i2cWrite)
	}
}

func TestI2CExactMessageCountAndCloseError(t *testing.T) {
	fake := &fakeSystem{functions: i2cFuncI2C, i2cResult: 1, closeError: syscall.EBADF}
	transport, err := openI2C(DefaultI2CConfig(), fake)
	if err != nil {
		t.Fatalf("openI2C failed: %v", err)
	}
	if _, err := transport.ReadRegister(0, 1); !errors.Is(err, ErrShortTransfer) {
		t.Fatalf("message count error = %v", err)
	}
	if err := transport.Close(); !errors.Is(err, syscall.EBADF) {
		t.Fatalf("close error = %v, want EBADF", err)
	}
	if err := transport.Close(); err != nil {
		t.Fatalf("second close = %v", err)
	}
}

func equalBytes(left, right []byte) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func TestKernelIOCTLStructLayouts(t *testing.T) {
	if got := unsafe.Sizeof(spiIOCTransfer{}); got != 32 {
		t.Fatalf("spi_ioc_transfer size = %d, want 32", got)
	}
	if got := unsafe.Sizeof(i2cMessage{}); got != 16 {
		t.Fatalf("i2c_msg size = %d, want 16", got)
	}
	if got := unsafe.Sizeof(i2cRDWRData{}); got != 16 {
		t.Fatalf("i2c_rdwr_ioctl_data size = %d, want 16", got)
	}
	if got := spiIOCMessage(1); got != 0x40206B00 {
		t.Fatalf("SPI_IOC_MESSAGE(1) = %#x, want 0x40206b00", got)
	}
}
