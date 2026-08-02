//go:build linux && (amd64 || arm64)

package linuxio

import (
	"fmt"
	"runtime"
	"sync"
	"time"
	"unsafe"

	"github.com/oaslananka/adxl355/go/adxl355"
	"golang.org/x/sys/unix"
)

const (
	spiIOC_MAGIC = uintptr('k')

	iocNRBits    = 8
	iocTypeBits  = 8
	iocSizeBits  = 14
	iocNRShift   = 0
	iocTypeShift = iocNRShift + iocNRBits
	iocSizeShift = iocTypeShift + iocTypeBits
	iocDirShift  = iocSizeShift + iocSizeBits
	iocWrite     = 1

	spiIOCWRMode        = (iocWrite << iocDirShift) | (spiIOC_MAGIC << iocTypeShift) | (1 << iocNRShift) | (1 << iocSizeShift)
	spiIOCWRBitsPerWord = (iocWrite << iocDirShift) | (spiIOC_MAGIC << iocTypeShift) | (3 << iocNRShift) | (1 << iocSizeShift)
	spiIOCWRMaxSpeedHz  = (iocWrite << iocDirShift) | (spiIOC_MAGIC << iocTypeShift) | (4 << iocNRShift) | (4 << iocSizeShift)

	i2cSlave   = uintptr(0x0703)
	i2cFuncs   = uintptr(0x0705)
	i2cRDWR    = uintptr(0x0707)
	i2cMRD     = uint16(0x0001)
	i2cFuncI2C = uintptr(0x00000001)
)

type spiIOCTransfer struct {
	TXBuffer         uint64
	RXBuffer         uint64
	Length           uint32
	SpeedHz          uint32
	DelayUsecs       uint16
	BitsPerWord      uint8
	ChipSelectChange uint8
	TXNBits          uint8
	RXNBits          uint8
	WordDelayUsecs   uint8
	Padding          uint8
}

type i2cMessage struct {
	Address uint16
	Flags   uint16
	Length  uint16
	Padding uint16
	Buffer  uintptr
}

type i2cRDWRData struct {
	Messages uintptr
	Count    uint32
}

type i2cOperation struct {
	address uint16
	read    bool
	data    []byte
}

type system interface {
	open(path string, flags int, mode uint32) (int, error)
	close(fd int) error
	configureSPI(fd int, mode uint8, bits uint8, speedHz uint32) error
	transferSPI(fd int, tx []byte, rx []byte, speedHz uint32) (int, error)
	i2cFunctions(fd int) (uintptr, error)
	selectI2CAddress(fd int, address uint16) error
	transferI2C(fd int, operations []i2cOperation) (int, error)
}

type unixSystem struct{}

func (unixSystem) open(path string, flags int, mode uint32) (int, error) {
	return unix.Open(path, flags, mode)
}

func (unixSystem) close(fd int) error { return unix.Close(fd) }

func ioctlValue(fd int, request uintptr, value uintptr) (int, error) {
	result, _, errno := unix.Syscall(unix.SYS_IOCTL, uintptr(fd), request, value)
	if errno != 0 {
		return 0, errno
	}
	return int(result), nil
}

func ioctlPointer(fd int, request uintptr, pointer unsafe.Pointer) (int, error) {
	result, _, errno := unix.Syscall(
		unix.SYS_IOCTL,
		uintptr(fd),
		request,
		uintptr(pointer),
	)
	runtime.KeepAlive(pointer)
	if errno != 0 {
		return 0, errno
	}
	return int(result), nil
}

func (unixSystem) configureSPI(fd int, mode uint8, bits uint8, speedHz uint32) error {
	if _, err := ioctlPointer(fd, spiIOCWRMode, unsafe.Pointer(&mode)); err != nil {
		return fmt.Errorf("set mode: %w", err)
	}
	if _, err := ioctlPointer(fd, spiIOCWRBitsPerWord, unsafe.Pointer(&bits)); err != nil {
		return fmt.Errorf("set bits per word: %w", err)
	}
	if _, err := ioctlPointer(fd, spiIOCWRMaxSpeedHz, unsafe.Pointer(&speedHz)); err != nil {
		return fmt.Errorf("set maximum speed: %w", err)
	}
	return nil
}

func spiIOCMessage(count uintptr) uintptr {
	size := count * unsafe.Sizeof(spiIOCTransfer{})
	return (iocWrite << iocDirShift) |
		(spiIOC_MAGIC << iocTypeShift) |
		(0 << iocNRShift) |
		(size << iocSizeShift)
}

func (unixSystem) transferSPI(
	fd int,
	tx []byte,
	rx []byte,
	speedHz uint32,
) (int, error) {
	transfer := spiIOCTransfer{
		TXBuffer:    uint64(uintptr(unsafe.Pointer(&tx[0]))),
		Length:      uint32(len(tx)),
		SpeedHz:     speedHz,
		BitsPerWord: 8,
	}
	if len(rx) > 0 {
		transfer.RXBuffer = uint64(uintptr(unsafe.Pointer(&rx[0])))
	}
	result, err := ioctlPointer(fd, spiIOCMessage(1), unsafe.Pointer(&transfer))
	runtime.KeepAlive(tx)
	runtime.KeepAlive(rx)
	return result, err
}

func (unixSystem) i2cFunctions(fd int) (uintptr, error) {
	functions := uintptr(0)
	_, err := ioctlPointer(fd, i2cFuncs, unsafe.Pointer(&functions))
	return functions, err
}

func (unixSystem) selectI2CAddress(fd int, address uint16) error {
	_, err := ioctlValue(fd, i2cSlave, uintptr(address))
	return err
}

func (unixSystem) transferI2C(fd int, operations []i2cOperation) (int, error) {
	messages := make([]i2cMessage, len(operations))
	for index := range operations {
		operation := &operations[index]
		messages[index] = i2cMessage{
			Address: operation.address,
			Length:  uint16(len(operation.data)),
			Buffer:  uintptr(unsafe.Pointer(&operation.data[0])),
		}
		if operation.read {
			messages[index].Flags = i2cMRD
		}
	}
	request := i2cRDWRData{
		Messages: uintptr(unsafe.Pointer(&messages[0])),
		Count:    uint32(len(messages)),
	}
	result, err := ioctlPointer(fd, i2cRDWR, unsafe.Pointer(&request))
	runtime.KeepAlive(operations)
	runtime.KeepAlive(messages)
	return result, err
}

// SPITransport owns one opened /dev/spidevB.D file descriptor.
type SPITransport struct {
	mu      sync.Mutex
	system  system
	fd      int
	path    string
	speedHz uint32
	closed  bool
}

var _ adxl355.Transport = (*SPITransport)(nil)

// OpenSPI validates and opens one spidev node. The returned transport owns the
// descriptor until Close is called.
func OpenSPI(config SPIConfig) (*SPITransport, error) {
	return openSPI(config, unixSystem{})
}

func openSPI(config SPIConfig, sys system) (*SPITransport, error) {
	path := fmt.Sprintf("/dev/spidev%d.%d", config.Bus, config.Device)
	if err := validateSPIConfig(config); err != nil {
		return nil, &OpError{Transport: "spi", Operation: "validate", Path: path, Err: err}
	}
	fd, err := sys.open(path, unix.O_RDWR|unix.O_CLOEXEC, 0)
	if err != nil {
		return nil, &OpError{Transport: "spi", Operation: "open", Path: path, Err: err}
	}
	if err := sys.configureSPI(fd, config.Mode, 8, config.SpeedHz); err != nil {
		_ = sys.close(fd)
		return nil, &OpError{Transport: "spi", Operation: "configure", Path: path, Err: err}
	}
	return &SPITransport{
		system:  sys,
		fd:      fd,
		path:    path,
		speedHz: config.SpeedHz,
	}, nil
}

// Close releases the owned spidev descriptor. Repeated calls are safe.
func (t *SPITransport) Close() error {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.closed {
		return nil
	}
	t.closed = true
	if err := t.system.close(t.fd); err != nil {
		return &OpError{Transport: "spi", Operation: "close", Path: t.path, Err: err}
	}
	return nil
}

func (t *SPITransport) transfer(tx []byte, receive bool) ([]byte, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.closed {
		return nil, &OpError{Transport: "spi", Operation: "transfer", Path: t.path, Err: ErrClosed}
	}
	var rx []byte
	if receive {
		rx = make([]byte, len(tx))
	}
	transferred, err := t.system.transferSPI(t.fd, tx, rx, t.speedHz)
	if err != nil {
		return nil, &OpError{Transport: "spi", Operation: "transfer", Path: t.path, Err: err}
	}
	if transferred != len(tx) {
		return nil, &OpError{
			Transport: "spi",
			Operation: "transfer",
			Path:      t.path,
			Err:       fmt.Errorf("%w: got %d, want %d bytes", ErrShortTransfer, transferred, len(tx)),
		}
	}
	return rx, nil
}

// ReadRegister performs one full-duplex command plus payload transaction.
func (t *SPITransport) ReadRegister(reg byte, length int) ([]byte, error) {
	if err := validateRegister(reg); err != nil {
		return nil, &OpError{Transport: "spi", Operation: "read", Path: t.path, Err: err}
	}
	if err := validateLength(length); err != nil {
		return nil, &OpError{Transport: "spi", Operation: "read", Path: t.path, Err: err}
	}
	tx := make([]byte, length+1)
	tx[0] = adxl355.SPIReadCmd(reg)
	rx, err := t.transfer(tx, true)
	if err != nil {
		return nil, err
	}
	return append([]byte(nil), rx[1:]...), nil
}

// WriteRegister performs one command plus complete payload transaction.
func (t *SPITransport) WriteRegister(reg byte, data []byte) error {
	if err := validateRegister(reg); err != nil {
		return &OpError{Transport: "spi", Operation: "write", Path: t.path, Err: err}
	}
	if err := validateLength(len(data)); err != nil {
		return &OpError{Transport: "spi", Operation: "write", Path: t.path, Err: err}
	}
	tx := make([]byte, len(data)+1)
	tx[0] = adxl355.SPIWriteCmd(reg)
	copy(tx[1:], data)
	_, err := t.transfer(tx, false)
	return err
}

// DelayMs implements the portable transport delay contract synchronously.
func (t *SPITransport) DelayMs(milliseconds uint32) {
	time.Sleep(time.Duration(milliseconds) * time.Millisecond)
}

// I2CTransport owns one opened /dev/i2c-N file descriptor and selected address.
type I2CTransport struct {
	mu      sync.Mutex
	system  system
	fd      int
	path    string
	address uint16
	busHz   uint32
	closed  bool
}

var _ adxl355.Transport = (*I2CTransport)(nil)

// OpenI2C validates and opens one i2c-dev adapter. BusHz is validated and
// recorded, but adapter speed must be configured by the Linux platform/driver.
func OpenI2C(config I2CConfig) (*I2CTransport, error) {
	return openI2C(config, unixSystem{})
}

func openI2C(config I2CConfig, sys system) (*I2CTransport, error) {
	path := fmt.Sprintf("/dev/i2c-%d", config.Bus)
	if err := validateI2CConfig(config); err != nil {
		return nil, &OpError{Transport: "i2c", Operation: "validate", Path: path, Err: err}
	}
	fd, err := sys.open(path, unix.O_RDWR|unix.O_CLOEXEC, 0)
	if err != nil {
		return nil, &OpError{Transport: "i2c", Operation: "open", Path: path, Err: err}
	}
	cleanup := func(operation string, cause error) (*I2CTransport, error) {
		_ = sys.close(fd)
		return nil, &OpError{Transport: "i2c", Operation: operation, Path: path, Err: cause}
	}
	functions, err := sys.i2cFunctions(fd)
	if err != nil {
		return cleanup("query-functions", err)
	}
	if functions&i2cFuncI2C == 0 {
		return cleanup("query-functions", ErrUnsupported)
	}
	if err := sys.selectI2CAddress(fd, config.Address); err != nil {
		return cleanup("select-address", err)
	}
	return &I2CTransport{
		system:  sys,
		fd:      fd,
		path:    path,
		address: config.Address,
		busHz:   config.BusHz,
	}, nil
}

// Close releases the owned i2c-dev descriptor. Repeated calls are safe.
func (t *I2CTransport) Close() error {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.closed {
		return nil
	}
	t.closed = true
	if err := t.system.close(t.fd); err != nil {
		return &OpError{Transport: "i2c", Operation: "close", Path: t.path, Err: err}
	}
	return nil
}

func (t *I2CTransport) transaction(
	operations []i2cOperation,
	expected int,
	operation string,
) error {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.closed {
		return &OpError{Transport: "i2c", Operation: operation, Path: t.path, Err: ErrClosed}
	}
	completed, err := t.system.transferI2C(t.fd, operations)
	if err != nil {
		return &OpError{Transport: "i2c", Operation: operation, Path: t.path, Err: err}
	}
	if completed != expected {
		return &OpError{
			Transport: "i2c",
			Operation: operation,
			Path:      t.path,
			Err:       fmt.Errorf("%w: got %d, want %d messages", ErrShortTransfer, completed, expected),
		}
	}
	return nil
}

// ReadRegister uses I2C_RDWR for one combined register-pointer write and read.
func (t *I2CTransport) ReadRegister(reg byte, length int) ([]byte, error) {
	if err := validateRegister(reg); err != nil {
		return nil, &OpError{Transport: "i2c", Operation: "read", Path: t.path, Err: err}
	}
	if err := validateLength(length); err != nil {
		return nil, &OpError{Transport: "i2c", Operation: "read", Path: t.path, Err: err}
	}
	command := []byte{reg}
	result := make([]byte, length)
	operations := []i2cOperation{
		{address: t.address, data: command},
		{address: t.address, read: true, data: result},
	}
	if err := t.transaction(operations, 2, "read"); err != nil {
		return nil, err
	}
	return result, nil
}

// WriteRegister uses I2C_RDWR for one register-plus-payload message.
func (t *I2CTransport) WriteRegister(reg byte, data []byte) error {
	if err := validateRegister(reg); err != nil {
		return &OpError{Transport: "i2c", Operation: "write", Path: t.path, Err: err}
	}
	if err := validateLength(len(data)); err != nil {
		return &OpError{Transport: "i2c", Operation: "write", Path: t.path, Err: err}
	}
	payload := make([]byte, len(data)+1)
	payload[0] = reg
	copy(payload[1:], data)
	return t.transaction(
		[]i2cOperation{{address: t.address, data: payload}},
		1,
		"write",
	)
}

// DelayMs implements the portable transport delay contract synchronously.
func (t *I2CTransport) DelayMs(milliseconds uint32) {
	time.Sleep(time.Duration(milliseconds) * time.Millisecond)
}

// DeclaredBusHz returns the externally configured I2C adapter rate recorded at open.
func (t *I2CTransport) DeclaredBusHz() uint32 { return t.busHz }
