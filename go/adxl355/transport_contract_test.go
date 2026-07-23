package adxl355

import (
	"errors"
	"testing"
)

type contractTransport struct {
	regs         [128]byte
	shortReg     int
	shortLength  int
	failReadReg  int
	failWriteReg int
}

func newContractTransport() *contractTransport {
	transport := &contractTransport{shortReg: -1, failReadReg: -1, failWriteReg: -1}
	transport.regs[RegDEVID_AD] = DEVID_AD_VALUE
	transport.regs[RegDEVID_MST] = DEVID_MST_VALUE
	transport.regs[RegPARTID] = PARTID_VALUE
	transport.regs[RegRANGE] = byte(Range2G)
	transport.regs[RegPOWER_CTL] = byte(PowerStandby)
	return transport
}

func (t *contractTransport) ReadRegister(reg byte, length int) ([]byte, error) {
	if t.failReadReg == int(reg) {
		return nil, errors.New("native read failure")
	}
	returned := length
	if t.shortReg == int(reg) {
		returned = t.shortLength
	}
	return t.regs[int(reg) : int(reg)+returned], nil
}

func (t *contractTransport) WriteRegister(reg byte, data []byte) error {
	if t.failWriteReg == int(reg) {
		return errors.New("native write failure")
	}
	copy(t.regs[reg:], data)
	return nil
}

func (t *contractTransport) DelayMs(_ uint32) {}

func probedContractDevice(t *testing.T, transport *contractTransport) *Device {
	t.Helper()
	device := New(transport)
	if _, err := device.Probe(); err != nil {
		t.Fatalf("Probe failed: %v", err)
	}
	return device
}

func TestTransportContractSingleRegisterExactLength(t *testing.T) {
	for _, returned := range []int{0, 2} {
		transport := newContractTransport()
		transport.shortReg = RegDEVID_AD
		transport.shortLength = returned
		if _, err := New(transport).Probe(); err != ErrBus {
			t.Fatalf("returned=%d error=%v, want ErrBus", returned, err)
		}
	}
}

func TestTransportContractTemperatureExactLength(t *testing.T) {
	for _, returned := range []int{0, 1} {
		transport := newContractTransport()
		device := probedContractDevice(t, transport)
		transport.shortReg = RegTEMP2
		transport.shortLength = returned
		if _, err := device.ReadTemperatureRaw(); err != ErrBus {
			t.Fatalf("returned=%d error=%v, want ErrBus", returned, err)
		}
	}
}

func TestTransportContractXYZExactLength(t *testing.T) {
	for _, returned := range []int{0, 8} {
		transport := newContractTransport()
		device := probedContractDevice(t, transport)
		transport.shortReg = RegXDATA3
		transport.shortLength = returned
		if _, err := device.ReadRaw(); err != ErrBus {
			t.Fatalf("returned=%d error=%v, want ErrBus", returned, err)
		}
	}
}

func TestTransportErrorsNormalizeToBus(t *testing.T) {
	transport := newContractTransport()
	transport.failReadReg = RegDEVID_AD
	if _, err := New(transport).Probe(); err != ErrBus {
		t.Fatalf("read error=%v, want ErrBus", err)
	}

	transport = newContractTransport()
	device := probedContractDevice(t, transport)
	transport.failWriteReg = RegRANGE
	if err := device.SetRange(Range4G); err != ErrBus {
		t.Fatalf("write error=%v, want ErrBus", err)
	}
}
